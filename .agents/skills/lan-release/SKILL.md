---
name: lan-release
description: Use when preparing, deploying or validating a MimiDaw Project Hub release on a private home network.
---

1. Verify `.env` is present, protected and untracked; never print a secret to logs or comments.
2. Run `make check`, JS syntax check and `docker compose config` (do not paste expanded secrets).
3. Back up the data volume before any migration. Do not run `docker compose down -v`.
4. Build/recreate containers, ensure `/api/v1/health` succeeds, then run `scripts/smoke.py` against host LAN address.
5. Manually verify create/search/upload/download/revision restore/trash restore from a second LAN device.
6. Record exact commands, test results and limitations in a PR comment. No router port forwarding or public exposure; this HTTP profile is unencrypted.
7. Roll back the application image without altering the volume; database migration changes require an explicit tested rollback plan.
