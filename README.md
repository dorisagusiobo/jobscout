# JobScout

An AI job-lead agent that runs on a schedule on AWS. It scans public job boards, filters
out roles I can't take, scores the rest against my profile with Claude on Amazon Bedrock,
and emails me only the strong matches. Each digest includes a pitch line I can reuse in a
cover letter.

```
EventBridge Scheduler ──► Lambda (Python 3.12)
                            │
                            ├─ 1. Scan     Greenhouse / Lever / Ashby public APIs (43 boards)
                            ├─ 2. Filter   title, US/remote location, clearance/citizenship rules
                            ├─ 3. Recall   DynamoDB: skip postings already scored (90-day TTL)
                            ├─ 4. Score    Claude on Bedrock → Pydantic FitAssessment
                            ├─ 5. Remember write score + verdict to DynamoDB
                            └─ 6. Alert    SNS email digest of leads ≥ 70 with no eligibility flags
```

## Design choices

- **Rules before the model.** Cheap regex filters drop most postings before any model call.
  The eligibility filter drops roles that need a security clearance or US citizenship. It
  keeps ITAR "U.S. person" roles, because asylees qualify as U.S. persons.
- **Structured output, not string parsing.** `client.messages.parse(output_format=FitAssessment)`
  returns a validated Pydantic object with score, verdict, strengths, gaps, eligibility
  concerns and pitch.
- **Grounded scoring.** The system prompt allows only facts from `profile/candidate_profile.md`
  and treats course projects as projects, not work experience.
- **Bounded cost.** At most `max_scores_per_run` model calls per run, and only one run at a
  time. Postings over the cap stay unseen and get scored on the next run; a failed score is
  retried next run too. AWS Budgets emails at 80% forecast and 100% actual spend, and at 100%
  a budget action attaches a deny policy so the Lambda can no longer call Bedrock. Cost
  Anomaly Detection emails a daily summary of unusual spend.
- **Testable seams.** The scorer, memory, notifier and fetcher are injected, so the whole
  loop runs in tests with fakes and makes no network or AWS calls.

## Claude Code guardrails

I build JobScout with Claude Code, so the repo carries the rules the coding agent has to follow.

- **Skill: [`safe-change`](.claude/skills/safe-change/SKILL.md).** Before and after any change,
  the agent runs the tests and, for edits in `infra/`, reads the full `terraform plan`. It
  stops and asks me before a plan would destroy or replace a resource, before any change to
  IAM, the AWS Budgets action or alerts, before touching the 15-scores-per-run cap or the $10
  monthly budget, and before any `terraform apply`. It may not delete or weaken tests to get a
  pass.
- **Hook: [`run-tests.sh`](.claude/hooks/run-tests.sh).** A `PostToolUse` hook in
  [`.claude/settings.json`](.claude/settings.json) runs the test suite after every edit to a
  Python file. If the tests fail it exits with code 2, so Claude Code sends the failure back to
  the agent. The skill is guidance; the hook is enforced.

Both were tested live: the agent stopped when asked to raise the per-run cap, and the hook
caught a deliberately failing test.

## Run locally

```bash
uv sync
uv run pytest                      # all tests, offline
uv run jobscout                    # live job boards, offline keyword scoring, nothing saved
uv run jobscout --live --max 5     # score 5 postings with Claude on Bedrock (needs AWS creds)
```

Live mode remembers seen postings in `.jobscout/seen.json`.

## Deploy to AWS

Prerequisites:
1. AWS credentials configured (`aws sts get-caller-identity` works).
2. In the Bedrock console (us-east-1), the Anthropic use-case form is submitted and Claude
   model access is granted. Until then calls fail with "not available for this account" or
   "use case details have not been submitted".

```bash
./build.sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # set alert_email
terraform init
terraform apply
```

Then click the SNS confirmation link AWS emails you. To trigger a run by hand:

```bash
aws lambda invoke --function-name jobscout /dev/stdout
```

## Configuration

| Setting | Where | Default |
|---|---|---|
| Boards and title keywords | `config/companies.json` | 43 AI-heavy companies |
| Candidate profile | `profile/candidate_profile.md` | — |
| Model | `JOBSCOUT_MODEL` / `var.model` | `global.anthropic.claude-sonnet-4-6` (use `anthropic.claude-opus-5-5` once your account has access) |
| Effort | `JOBSCOUT_EFFORT` | `low` (set empty for models without effort, e.g. Haiku 4.5) |
| Alert threshold | `JOBSCOUT_MIN_SCORE` | 70 |
| Model calls per run | `JOBSCOUT_MAX_SCORES` | 15 |
| Schedule | `var.schedule` | 8 AM ET, weekdays |

## Model IDs and Bedrock APIs

The scorer picks the Bedrock API from the model ID:

- `anthropic.claude-opus-5-5` (no region prefix) uses the Messages API endpoint
  (`bedrock-mantle`) through `AnthropicBedrockMantle`.
- `global.anthropic.claude-sonnet-4-6` or `us.anthropic.claude-haiku-4-5-20251001-v1:0`
  (inference profiles) use InvokeModel through `AnthropicBedrock`.

## Credits

The planner → scanner → scorer → messenger structure follows the multi-agent "Price is Right"
project from Week 8 of Ed Donner's *LLM Engineering* course. JobScout applies that pattern to
a different problem with its own sources, filters, scoring and AWS deployment.
