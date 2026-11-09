## Linked issue / goal

## Scope / contract changes

## Tests run (commands + actual results)

- [ ] `make check`
- [ ] `node --check hub/static/app.js`
- [ ] `docker compose config` if deployment changed
- [ ] LAN smoke/interactive checks if deployment changed (or reason not run)

## Safety checklist

- [ ] Authentication + CSRF enforced on writes
- [ ] Revision conflicts / transactional correctness covered
- [ ] Asset integrity, no path traversal / breaking history
- [ ] XSS, file validation, secrets and LAN exposure reviewed
- [ ] Docs and limitations updated
- [ ] Codex self-review (`/review` or `$review-change`) performed

## Risks / rollback plan

## Human review gate

Do not merge until CI and review gates are complete. Log findings and follow-up decisions in this PR.
