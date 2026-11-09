# Codex operating contract · MimiDaw Project Hub

## Mission and scope

Deliver a reliable, locally deployable music project API and browser catalog. Keep a clean migration path to a multiuser service and a separate MimiDaw editor. Read `README.md` and `docs/architecture/README.md` before making changes. Work on issues/PR branches; do not push directly to `main` and do not auto-merge.

## Non-negotiable invariants

- No project state mutation without authentication and CSRF checks, except explicitly documented login/health flows.
- Never bypass revision checking on a write. Concurrent stale writes must return `409 Conflict`, not lose data.
- A committed revision must not reference a new, missing, partially written, or different-project asset.
- Binary paths must be server generated; never construct a filesystem path from user-supplied filenames.
- Historic revisions and required assets must remain restorable. Do not delete referenced blobs as a side effect of a UI remove/trash operation.
- Keep the API contract under `/api/v1`; changes must include tests and README/API updates.
- Secret values belong in `.env`, not the repository, logs, PRs, or test fixtures. Never enable Internet exposure by default.

## Workflow (every code task)

1. Read task issue and acceptance criteria; inspect affected code before editing. If scope is unclear, make the smallest safe assumption and record it in the issue.
2. State plan and affected contracts in the issue or PR; work in a feature branch.
3. Implement with regression tests (prefer a failing test first for bug fixes). Keep migrations and rollback implications explicit.
4. Run `make check` and `node --check hub/static/app.js` where Node is available. For deployment-affecting changes, validate `docker compose config` and run `scripts/smoke.py` against a disposable instance.
5. Self-review the diff for auth, CSRF, path traversal, XSS, transactionality, stale versions, upload cleanup and secrets. Use `$review-change` and Codex `/review` when available.
6. Open a PR with issue link, risk notes, tests/actual results, manual home-LAN verification steps, and any limitations. Post evidence and reviewer responses in the issue/PR comments rather than only local scratch files.
7. Do not mark done or merge until CI is green, findings are resolved, and any required human review has approved it. A failed gate sends the task back for correction; do not hide failures.

## Review rules

Reviewers must flag: unauthenticated data access; write operations bypassing CSRF; revision races; object deletion breaking historical restore; plaintext secrets; escaping/security regressions in UI; and documentation advertising features the code does not implement. Require proof via relevant tests. Separate release blockers from minor style suggestions.

## Project layout and useful commands

- Backend: `hub/app.py`; static UI: `hub/static/`; regression tests: `tests/`.
- `python -m pip install -r requirements-dev.txt` then `make check`.
- Local run: source `.env` and `make run`; container: `docker compose up --build -d`.
- Network smoke: `python3 scripts/smoke.py http://<LAN_HOST>:8090` (prompts for hub password).
- Project skills: `$implement-issue`, `$review-change`, `$lan-release` under `.agents/skills/`.

## Engineering posture

Prefer thin vertical slices with verifiable behavior. Avoid premature microservices and unrelated rewrites. Favor simple standard-library code where it reduces dependencies without harming safety. Keep metadata and asset transport independent of browser implementation. When a feature does not yet exist, state that directly rather than inventing validation evidence.
