---
name: safe-change
description: Use before editing, fixing, refactoring or adding features to JobScout code, tests or Terraform in infra/. Runs the tests and reviews the Terraform plan.
---

# Safe change checklist for JobScout

## Before making a change

Run `uv run pytest -q` to establish whether the existing tests pass before editing code or infrastructure. Record any failures so they are not confused with failures introduced by the change.

## After making a change

Run `uv run pytest -q` again. If any file under `infra/` changed, run `terraform -chdir=infra plan`. Read the entire plan, checking especially for resources marked for destruction or replacement, because replacement also destroys the existing resource. Report the test results and the proposed infrastructure changes.

If tests fail before or after the change, investigate and try to fix them within the requested scope, then rerun `uv run pytest -q`. Do not delete or weaken tests just to get a passing result. If resolving a failure requires unrelated changes, a decision from me, or permission covered below, stop and explain the failure and what is needed. Do not apply infrastructure changes while tests are failing or the Terraform plan has failed.

## Stop and ask me if

- Test failures cannot be resolved within the requested scope, or fixing them requires a decision or permission from me.
- The Terraform plan would destroy or replace any resource.
- A change would edit IAM roles or policies, the AWS Budgets action, or the alert settings.
- A proposed change would alter the 15-items-per-run limit or the $10 monthly budget. Get explicit permission before editing either limit, including configuration or environment overrides that change its effective value.
- You are ready to run `terraform apply`. Present the specific plan and wait for my explicit approval of that plan. General permission to work on infrastructure is not approval to apply it. If the proposed changes differ from the approved plan, obtain approval again before applying.

## Working practices

1. Read the applicable project instructions, `README.md`, and the code and tests related to the request. Check `git status --short` before editing so you can preserve existing work.
2. Identify the requested behavior and the smallest change that achieves it. Follow the existing Python and Terraform patterns; avoid unrelated refactors and dependency changes.
3. Preserve the pipeline's safeguards unless I explicitly request a change: eligibility filters run before scoring; assessments stay grounded in `profile/candidate_profile.md`; previously scored postings are skipped; failed scores and postings beyond the run cap remain eligible for retry; alerts respect the score threshold and eligibility flags. Keep model-call limits and infrastructure cost controls intact.
4. Keep credentials and private profile content out of logs, test fixtures, and the final response. Use the injected fetcher, scorer, memory, and notifier seams for offline tests instead of contacting live services.
5. Implement the change and add or adjust regression tests when behavior changes. Run the relevant offline tests with `uv run pytest`, narrowing to the affected tests while iterating. If dependencies are already installed, `.venv/bin/python -m pytest` is an alternative. Report any checks you could not run.
6. For infrastructure edits, review the Terraform diff and run formatting and validation checks when the tools are available. Treat deployment, live Bedrock scoring, Lambda invocation, and email delivery as separate actions requiring authorization within my request; ordinary verification should stay offline.
7. Review the final diff for unintended changes and exposed secrets. Summarize what changed, the checks and their results, and any remaining limitations. Leave committing and deployment to my request.
