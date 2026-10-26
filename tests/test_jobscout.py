import json
from types import SimpleNamespace

import httpx
import pytest

from jobscout.config import Settings
from jobscout.filters import eligibility_problem, location_ok, prefilter, title_matches
from jobscout.memory import DynamoMemory, JsonMemory
from jobscout.models import FitAssessment, Job
from jobscout.notifier import SnsNotifier, format_digest
from jobscout.planner import Planner
from jobscout.scorer import ClaudeScorer, KeywordScorer, bedrock_api
from jobscout.sources import fetch_all, html_to_text, parse_ashby, parse_greenhouse, parse_lever

INCLUDE = ["ai engineer", "llm", "machine learning engineer"]
EXCLUDE = ["staff", "manager", "intern"]


def job(i="1", title="AI Engineer", location="Remote - US", description="Python LLM RAG on AWS"):
    return Job(id=f"greenhouse:acme:{i}", source="greenhouse", company="Acme", title=title,
               location=location, url=f"https://example.com/{i}", description=description)


def assessment(score=85, concerns=()):
    return FitAssessment(fit_score=score, verdict="strong" if score >= 80 else "weak",
                         matching_strengths=["RAG"], gaps=[], eligibility_concerns=list(concerns),
                         pitch="I ship grounded LLM features.")


# ---- sources ----

def test_html_to_text_handles_greenhouse_double_escaping():
    assert html_to_text("&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;&lt;li&gt;RAG&lt;/li&gt;") == "Build & ship\nRAG"


def test_parsers_normalize_each_source():
    gh = parse_greenhouse("Acme", "acme", {"jobs": [{"id": 7, "title": " AI Engineer ",
        "location": {"name": "Remote"}, "absolute_url": "u", "content": "&lt;p&gt;x&lt;/p&gt;"}]})
    lv = parse_lever("Acme", "acme", [{"id": "a", "text": "LLM Engineer", "categories": {"location": "NYC"},
        "hostedUrl": "u", "descriptionPlain": "desc", "lists": [{"text": "Must", "content": "<li>Python</li>"}],
        "createdAt": 1_700_000_000_000}])
    ab = parse_ashby("Acme", "acme", {"jobs": [{"id": "b", "title": "AI Engineer", "location": "US",
        "isRemote": True, "jobUrl": "u", "descriptionPlain": "d"}]})
    assert gh[0].id == "greenhouse:acme:7" and gh[0].title == "AI Engineer" and gh[0].description == "x"
    assert lv[0].location == "NYC" and "Python" in lv[0].description and lv[0].posted_at.startswith("2023")
    assert ab[0].location == "US (Remote)"


def test_fetch_all_skips_broken_boards():
    def handler(request):
        if "broken" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, json={"jobs": [{"id": 1, "title": "AI Engineer", "absolute_url": "u"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    boards = [{"company": "Ok", "source": "greenhouse", "token": "ok"},
              {"company": "Bad", "source": "greenhouse", "token": "broken"}]
    jobs = fetch_all(boards, client=client)
    assert [j.company for j in jobs] == ["Ok"]


# ---- filters ----

@pytest.mark.parametrize("title,ok", [
    ("Senior AI Engineer", True), ("LLM Platform Engineer", True),
    ("Staff Machine Learning Engineer", False), ("Engineering Manager, AI", False), ("Account Executive", False),
])
def test_title_matches(title, ok):
    assert title_matches(title, INCLUDE, EXCLUDE) is ok


@pytest.mark.parametrize("loc,ok", [
    ("Remote - US", True), ("Baltimore, MD", True), ("Washington, D.C.", True), ("", True),
    ("San Francisco (Remote)", True), ("United States", True), ("West Coast - United States", True),
    ("Arlington, VA", True), ("Hybrid - Bethesda", True),
    ("San Francisco, CA", False), ("Seattle, Washington", False), ("New York, NY; London, UK", False),
    ("San Francisco, California, United States", False),
    ("London, UK", False), ("Remote - Canada", False), ("Bengaluru, India", False),
])
def test_location_ok(loc, ok):
    assert location_ok(loc) is ok


@pytest.mark.parametrize("text,blocked", [
    ("Candidates must hold an active Secret clearance.", True),
    ("TS/SCI with polygraph required", True),
    ("Applicants must be a U.S. citizen.", True),
    ("US citizenship is required for this role", True),
    ("Must be a U.S. person under ITAR.", False),  # asylees are U.S. persons
    ("We do not offer visa sponsorship.", False),  # no sponsorship needed
    ("Build RAG pipelines in Python.", False),
])
def test_eligibility(text, blocked):
    assert (eligibility_problem(text) is not None) is blocked


def test_prefilter_counts_reasons():
    jobs = [job("1"), job("2", title="Recruiter"), job("3", location="Paris, France"),
            job("4", description="Requires an active security clearance")]
    kept, dropped = prefilter(jobs, INCLUDE, EXCLUDE)
    assert [j.id for j in kept] == ["greenhouse:acme:1"]
    assert dropped == {"title": 1, "location": 1, "eligibility": 1}


# ---- scorer ----

def test_claude_scorer_calls_parse_with_structured_output():
    calls = {}

    def parse(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(parsed_output=assessment(90), stop_reason="end_turn")

    fake = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    scorer = ClaudeScorer("PROFILE", "anthropic.claude-opus-5-5", "us-east-1", client=fake)
    result = scorer.score(job())
    assert result.fit_score == 90
    assert calls["output_format"] is FitAssessment
    assert calls["model"] == "anthropic.claude-opus-5-5"
    assert "PROFILE" in calls["system"] and "Acme" in calls["messages"][0]["content"]


def test_effort_is_optional():
    calls = {}
    fake = SimpleNamespace(messages=SimpleNamespace(
        parse=lambda **kw: calls.update(kw) or SimpleNamespace(parsed_output=assessment(), stop_reason="end_turn")))
    ClaudeScorer("p", "us.anthropic.claude-haiku-4-5-20251001-v1:0", "us-east-1", effort="", client=fake).score(job())
    assert "output_config" not in calls
    assert calls["extra_body"] == {"anthropic_version": "bedrock-2023-05-31"}  # InvokeModel path


@pytest.mark.parametrize("model,api", [
    ("anthropic.claude-opus-5-5", "mantle"),
    ("global.anthropic.claude-sonnet-4-6", "invoke"),
    ("us.anthropic.claude-haiku-4-5-20251001-v1:0", "invoke"),
])
def test_bedrock_api_selection(model, api):
    assert bedrock_api(model) == api


def test_claude_scorer_raises_without_parsed_output():
    fake = SimpleNamespace(messages=SimpleNamespace(
        parse=lambda **_: SimpleNamespace(parsed_output=None, stop_reason="max_tokens")))
    with pytest.raises(RuntimeError, match="max_tokens"):
        ClaudeScorer("p", "m", "us-east-1", client=fake).score(job())


def test_keyword_scorer_is_deterministic():
    assert KeywordScorer().score(job()).fit_score == KeywordScorer().score(job()).fit_score


# ---- memory ----

def test_json_memory_round_trip(tmp_path):
    path = tmp_path / "seen.json"
    JsonMemory(path).remember("a", 80, "strong")
    assert JsonMemory(path).unseen(["a", "b"]) == ["b"]


class FakeDynamo:
    def __init__(self):
        self.items = {}

    def Table(self, name):
        outer = self
        return SimpleNamespace(put_item=lambda Item: outer.items.__setitem__(Item["job_id"], Item))

    def batch_get_item(self, RequestItems):
        (name, req), = RequestItems.items()
        found = [{"job_id": k["job_id"]} for k in req["Keys"] if k["job_id"] in self.items]
        return {"Responses": {name: found}, "UnprocessedKeys": {}}


def test_dynamo_memory_batches_and_sets_ttl():
    db = FakeDynamo()
    mem = DynamoMemory("seen", resource=db)
    mem.remember("job-5", 70, "possible")
    ids = [f"job-{i}" for i in range(250)]
    unseen = mem.unseen(ids)
    assert len(unseen) == 249 and "job-5" not in unseen
    assert db.items["job-5"]["expires_at"] > db.items["job-5"]["seen_at"]


# ---- notifier ----

def test_digest_and_sns():
    from jobscout.models import Lead

    leads = [Lead(job=job("1"), assessment=assessment(82)), Lead(job=job("2"), assessment=assessment(95))]
    text = format_digest(leads)
    assert text.index("95/100") < text.index("82/100")
    sent = {}
    SnsNotifier("arn:topic", client=SimpleNamespace(publish=lambda **kw: sent.update(kw))).send(leads)
    assert sent["TopicArn"] == "arn:topic" and len(sent["Subject"]) <= 100
    SnsNotifier("arn", client=SimpleNamespace(publish=lambda **kw: pytest.fail("sent empty"))).send([])


# ---- planner ----

class ScriptedScorer:
    def __init__(self, results):
        self.results = results
        self.seen = []

    def score(self, j):
        self.seen.append(j.id)
        r = self.results[j.id]
        if isinstance(r, Exception):
            raise r
        return r


def settings(max_scores=10):
    s = Settings()
    s.companies = {"boards": [], "title_include": INCLUDE, "title_exclude": EXCLUDE}
    s.max_scores_per_run = max_scores
    s.min_score = 75
    return s


def test_planner_end_to_end(tmp_path):
    jobs = [job("1"), job("2"), job("3"), job("4"), job("5", title="Recruiter")]
    results = {
        "greenhouse:acme:1": assessment(90),
        "greenhouse:acme:2": assessment(50),
        "greenhouse:acme:3": assessment(88, concerns=["on-site in Austin 5 days"]),
        "greenhouse:acme:4": ValueError("boom"),
    }
    memory = JsonMemory(tmp_path / "seen.json")
    memory.remember("greenhouse:acme:2", 50, "weak")  # seen last run
    sent = []
    notifier = SimpleNamespace(send=sent.append)
    scorer = ScriptedScorer(results)

    report = Planner(settings(), scorer, memory, notifier, fetch=lambda boards: jobs).run()

    assert scorer.seen == ["greenhouse:acme:1", "greenhouse:acme:3", "greenhouse:acme:4"]
    assert [l.job.id for l in sent[0]] == ["greenhouse:acme:1"]  # concern + low score excluded
    assert report.summary() == {"fetched": 5, "dropped": {"title": 1, "location": 0, "eligibility": 0},
                                "already_seen": 1, "scored": 2, "deferred_to_next_run": 0,
                                "errors": 1, "leads": 1}
    assert memory.unseen(["greenhouse:acme:4"]) == ["greenhouse:acme:4"]  # failed one retried next run


def test_planner_caps_model_calls(tmp_path):
    jobs = [job(str(i)) for i in range(5)]
    scorer = ScriptedScorer({j.id: assessment(60) for j in jobs})
    report = Planner(settings(max_scores=2), scorer, JsonMemory(tmp_path / "s.json"),
                     SimpleNamespace(send=lambda leads: None), fetch=lambda b: jobs).run()
    assert report.scored == 2 and report.deferred == 3


def test_shipped_config_is_valid():
    cfg = json.loads(Settings().companies_file.read_text())
    assert {b["source"] for b in cfg["boards"]} <= {"greenhouse", "lever", "ashby"}
    assert Settings().profile_file.read_text().strip()
