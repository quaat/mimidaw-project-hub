---
name: implement-issue
description: Use when implementing a GitHub issue in MimiDaw Project Hub; plan, edit, test, document and open a reviewable PR.
---

1. Read `AGENTS.md`, relevant code/tests, architecture docs and issue acceptance criteria.
2. Identify the smallest vertical slice and document plan/risks on the issue.
3. Add a regression test (red first for bug fixes), implement, and run `make check` plus JS syntax check.
4. For schema/API modifications, update README and acceptance fixtures; inspect backwards compatibility.
5. Self-review for cookie/CSRF, authorization, version checking, asset integrity, XSS, and local network safety.
6. Open a PR and post commands, outputs, constraints and manual LAN test plan. Ask for Codex review if enabled.
7. Leave main untouched. Never declare complete on red or unreviewed CI.
