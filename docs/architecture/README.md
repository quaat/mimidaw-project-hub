# MimiDaw Project Hub · 4+1 architecture (v0.1)

## Logical view

`Project` owns metadata, a versioned `manifest` (native JSON musical structure), `Asset` references, and an append-only sequence of `Revision` snapshots. `Asset` data is immutable once uploaded; removing an asset from the current project marks it inactive, keeping older revisions recoverable. `Project.deleted_at` implements soft deletion. BPM and musical key in metadata are catalog/search descriptors; the manifest is the future DAW-editing contract.

Invariant: the current state and latest `Revision.snapshot` describe the same metadata, manifest, and active asset set. Restoration appends a new revision, never rewrites an old snapshot. Every state-changing operation checks the caller's expected revision within SQLite's `BEGIN IMMEDIATE` transaction.

## Development view

- `hub/app.py`: FastAPI, models, SQLite repository, local file storage, session and CSRF checks.
- `hub/static/`: browser catalog, metadata form, file and revision management.
- `tests/`: TestClient-level CRUD, search, conflicts, auth, files, and restore behavior.
- `scripts/`: first-time credential initialization and network smoke test.
- `.agents/skills/`, `.codex/`, `AGENTS.md`: Codex harness and review/playbook context.

The single backend is intentional. Split services only when concrete deployment or load data demonstrates the need.

## Process view

1. **Create project:** validate metadata → insert `projects` → record revision 1 atomically.
2. **Upload asset:** authenticate/CSRF → preflight revision → stream and hash into a temporary file → verify header/limit → atomic rename → recheck revision inside a write transaction → insert asset → record next revision. On transaction failure the new file is removed.
3. **Save document:** validate minimal manifest shape/size → `BEGIN IMMEDIATE` → check revision → update manifest → append revision.
4. **Restore:** load immutable snapshot → validate referenced assets → apply metadata, manifest, active asset set → append current revision + 1.
5. **Browse:** authenticated SQL filters/pagination return metadata only; asset downloads require an authorized per-project route.

## Physical view

One Docker Compose `hub` container on port 8090 and one durable Docker named volume mounted at `/data`. SQLite uses WAL and stores the catalog and revision snapshots; `/data/assets/<uuid>` stores binary media. Static UI is served by FastAPI, requiring no separate build tool. Health check uses `/api/v1/health`. Avoid public network exposure: the LAN HTTP test profile is not TLS-secured.

## +1: acceptance scenarios

- UC1: Enter an artist and BPM and find only matching projects.
- UC2: Create a new project, upload a MIDI and a WAV, view/download both after a restart.
- UC3: Two clients edit the same revision: one succeeds and the other receives `409`, without data loss.
- UC4: Remove a MIDI, restore an earlier revision, verify the file reappears.
- UC5: Move a project to trash and restore it without losing assets.

## Architecture decisions / next milestones

- **ADR-001:** SQLite + local immutable blob files for an initial single-node LAN test. Future: repository/storage adapter to PostgreSQL and S3. Do not claim transparent scale-out while SQLite and filesystem are coupled.
- **ADR-002:** Opaque UUID asset names and server-mediated downloads, no direct paths or anonymous downloads.
- **ADR-003:** Signed session cookie and CSRF protection. Single-password authentication is only an MVP LAN compromise; replace with OIDC/workspaces before multi-user or Internet exposure.
- **ADR-004:** JSON snapshot per revision. Full-project file export and rigorous MIDI document schema come later.
- **ADR-005:** No auto garbage collection: old revisions remain recoverable by retaining referenced media.

Priorities for subsequent issues: P0 TLS and multiuser auth; P1 secure native bundle import/export + manifest schema validation; P1 audio preview and track metadata; P2 collections/album entities and advanced faceted search; P2 PostgreSQL/S3 adapters.
