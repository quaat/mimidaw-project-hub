---
name: review-change
description: Use when reviewing PRs or code changes to MimiDaw Project Hub, especially security, revision consistency and test quality.
---

Read changed files and `AGENTS.md`. Independently inspect each mutation for auth, CSRF, optimistic concurrency and atomicity; each binary route for ID/path isolation, file checks and data retention; each HTML rendering path for escaping; each deployment change for credentials, network exposure and volume durability. Run or inspect `make check`, JS syntax check, and relevant smoke evidence. Report findings with severity, affected path/behavior, reproducible steps, and missing regression test. A reviewer must not silently fix and approve their own changes.
