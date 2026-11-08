# MimiDaw Project Hub

A **self-hosted, LAN-first catalog and API for editable music projects**. Browse projects like a music library; store metadata, WAV, MIDI, cover art, an editable JSON arrangement manifest, and immutable project revisions. This is a first usable **single-user** release, not a complete DAW.

## Start on a home network

Requirements: Docker Engine with Docker Compose v2, a Linux/macOS machine or NAS accessible on the same private LAN, and an available port (default **8090**).

```bash
git clone https://github.com/quaat/mimidaw-project-hub.git
cd mimidaw-project-hub
./scripts/init-env.sh  # Prints a randomly generated password; save it securely
docker compose up --build -d
docker compose ps
```

From another device on the LAN, open `http://<SERVER_LAN_IP>:8090` and sign in with the password printed by `init-env.sh`. Do **not** use `localhost` from another device. The server exposes `/api/docs` (OpenAPI Swagger UI) at the same host, and `/api/v1/health` is a public health check.

To verify the running instance:

```bash
python3 scripts/smoke.py http://127.0.0.1:8090
# On the same server; enter the password when prompted.
```

To inspect logs or stop the stack: `docker compose logs -f hub` / `docker compose down`. The named Docker volume `hub_data` preserves SQLite and binary assets across restarts; `docker compose down -v` **deletes that volume**. Back up the complete volume consistently (stop writes before copying). `./scripts/init-env.sh` refuses to overwrite an existing `.env`.

**Security:** This release uses one password and a signed, HttpOnly, SameSite cookie with CSRF protection. **HTTP sends the password and session traffic unencrypted.** It is intended solely for a trusted, isolated home LAN. Do not expose port 8090 on the public Internet or set up router port-forwarding. Prefer a TLS reverse proxy and access controls before use on shared/untrusted networks; set `HUB_COOKIE_SECURE=1` only when the browser connects over HTTPS. The generated `.env` contains a privileged password and signing secret; keep it private. Files are never uploaded to an external service.

To restrict access to the server itself, set `HUB_BIND_IP=127.0.0.1` in `.env` and use an appropriate private reverse proxy. `HUB_PORT` changes the published port. For changing the password, update `.env` and recreate the container. The signing secret must be preserved to retain session validity.

## What works in v0.1

- Create/edit projects: title, musical version, artist, album, year, genre/subgenre, BPM, key, signature and notes.
- Search by title/artist/album/notes, exact artist/album/genre/key/BPM, BPM ranges, MIDI/audio presence.
- Upload/download verified WAV, standard MIDI, and PNG/JPEG/WebP cover-art files (default max 100 MB each).
- Edit a versioned JSON musical arrangement manifest through the API or advanced JSON editor.
- Automatic immutable project revisions for metadata, manifest, and file changes. Restore an earlier revision as a new revision; restore projects from trash.
- Responsive dark-mode web catalog; documented OpenAPI interface; same-origin cookie auth.

**Boundaries:** It is a *project repository*, not a music sequencer/player. It doesn't synthesize MIDI or render audio, parse MIDI into notes, export a portable bundle, have separate user accounts, stream media, or share publicly. Artist is one searchable display field in this release (multi-artist credits are deferred). Revisions contain JSON snapshots with asset references, not file copies. Objects referenced by historical revisions remain available; automated asset garbage collection is intentionally not included.

## Develop without Docker

Python **3.13** is the supported local/runtime version.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
./scripts/init-env.sh  # If .env does not exist; otherwise reuse the existing file
set -a; source .env; set +a
make run             # server on http://127.0.0.1:8090
# In another terminal:
python -m pytest -q
```

If you are not on a POSIX shell, export `HUB_ADMIN_PASSWORD` and `HUB_SESSION_SECRET` from `.env` manually. `HUB_DATA_DIR` defaults to `./data`; this is ignored by Git. Run `node --check hub/static/app.js` if Node is available, and `make check` for Python compilation and tests.

## API highlights

All endpoints except `/api/v1/health`, `/api/v1/session`, login, and static assets require the signed session. Mutations also require `X-CSRF-Token` returned from login/session. For a full parameter list, use `/api/docs`.

| Method | Path | Meaning |
| --- | --- | --- |
| `POST` | `/api/v1/session/login` | Password login, set cookie, return CSRF |
| `GET` | `/api/v1/projects?artist=...&bpm=92` | Search/filter projects |
| `POST` | `/api/v1/projects` | Create with metadata |
| `PATCH` | `/api/v1/projects/{id}/metadata` | Replace metadata, `expected_revision` required |
| `PUT` | `/api/v1/projects/{id}/document` | Save manifest, `expected_revision` required |
| `POST` | `/api/v1/projects/{id}/assets` | Multipart upload: `file`, `kind`, `expected_revision` |
| `GET` | `/api/v1/projects/{id}/assets/{asset_id}/content` | Authorized binary download |
| `GET` | `/api/v1/projects/{id}/revisions` | Revision history |
| `POST` | `/api/v1/projects/{id}/revisions/{n}/restore` | Restore as a new revision |
| `DELETE` | `/api/v1/projects/{id}` | Move to trash |
| `POST` | `/api/v1/projects/{id}/restore` | Restore from trash |

A stale `expected_revision` returns `409 Conflict`; the client should reload and explicitly reconcile changes. No silent overwrites. The native project JSON has `schema_version: "1.0"`, `settings: { ... }` and `tracks: [ ... ]`. It deliberately has only minimal structural validation in v0.1; richer semantics are a subsequent task.

## Architecture and continued development

See [`docs/architecture/README.md`](docs/architecture/README.md) for the 4+1 view and ADRs. For Codex, start at [`AGENTS.md`](AGENTS.md); repo skills live in [`.agents/skills/`](.agents/skills/), and the local project configuration is in [`.codex/config.toml`](.codex/config.toml). GitHub Actions runs tests and source checks for PRs.

This initial, deliberate single-node design uses **FastAPI + SQLite + filesystem** to avoid the operations cost of Postgres/S3 at home. Storage/query boundaries are encapsulated so the next stage can use PostgreSQL and S3/MinIO, as originally envisioned. LAN deployment with a shared password is a test profile, not the final identity architecture.
