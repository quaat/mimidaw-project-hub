"""MimiDaw Project Hub: single-node, LAN-first API and catalog."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

DATA_DIR = Path(os.environ.get("HUB_DATA_DIR", "./data")).resolve()
DB_PATH = DATA_DIR / "hub.sqlite3"
ASSET_DIR = DATA_DIR / "assets"
ADMIN_PASSWORD = os.environ.get("HUB_ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("HUB_SESSION_SECRET", "")
MAX_UPLOAD = int(os.environ.get("HUB_MAX_UPLOAD_MB", "100")) * 1024 * 1024
SESSION_TTL = 7 * 24 * 3600
STATIC = Path(__file__).parent / "static"

if not ADMIN_PASSWORD or ADMIN_PASSWORD in {"changeme", "password", "admin"}:
    raise RuntimeError("Set a non-default HUB_ADMIN_PASSWORD in .env")
if len(SESSION_SECRET) < 32:
    raise RuntimeError("Set HUB_SESSION_SECRET to at least 32 random characters")

DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="MimiDaw Project Hub", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
failed_logins: dict[str, list[float]] = {}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db(write: bool = False):
    conn = sqlite3.connect(str(DB_PATH), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except Exception:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL DEFAULT '',
          album TEXT NOT NULL DEFAULT '', release_year INTEGER, genre TEXT NOT NULL DEFAULT '',
          subgenre TEXT NOT NULL DEFAULT '', bpm INTEGER NOT NULL DEFAULT 120,
          musical_key TEXT NOT NULL DEFAULT 'C major', time_signature TEXT NOT NULL DEFAULT '4/4',
          musical_version TEXT NOT NULL DEFAULT 'Demo', description TEXT NOT NULL DEFAULT '',
          manifest TEXT NOT NULL, cover_asset_id TEXT, revision INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
          filename TEXT NOT NULL, kind TEXT NOT NULL, content_type TEXT NOT NULL,
          size INTEGER NOT NULL, sha256 TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, active);
        CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_projects_artist ON projects(artist COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_projects_bpm ON projects(bpm);
        CREATE TABLE IF NOT EXISTS revisions (
          project_id TEXT NOT NULL REFERENCES projects(id), number INTEGER NOT NULL,
          snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(project_id, number)
        );
        """)


init_db()


class Metadata(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    artist: str = Field(default="", max_length=200)
    album: str = Field(default="", max_length=200)
    release_year: int | None = Field(default=None, ge=1800, le=2200)
    genre: str = Field(default="", max_length=100)
    subgenre: str = Field(default="", max_length=100)
    bpm: int = Field(default=120, ge=20, le=400)
    musical_key: str = Field(default="C major", max_length=60)
    time_signature: str = Field(default="4/4", max_length=16)
    musical_version: str = Field(default="Demo", max_length=100)
    description: str = Field(default="", max_length=4000)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title cannot be blank")
        return value.strip()

    @field_validator("time_signature")
    @classmethod
    def valid_signature(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9]\d?/(2|4|8|16|32)", value):
            raise ValueError("time signature must resemble 4/4 or 6/8")
        return value


class CreateProject(Metadata):
    pass


class UpdateMetadata(BaseModel):
    expected_revision: int = Field(ge=1)
    metadata: Metadata


class SaveDocument(BaseModel):
    expected_revision: int = Field(ge=1)
    manifest: dict[str, Any]


class ExpectedRevision(BaseModel):
    expected_revision: int = Field(ge=1)


class Login(BaseModel):
    password: str


def signature(value: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    value = f"{int(time.time()) + SESSION_TTL}.{secrets.token_hex(16)}"
    return f"{value}.{signature(value)}"


def check_session(request: Request) -> str | None:
    token = request.cookies.get("hub_session", "")
    try:
        expiry, nonce, mac = token.split(".")
        value = f"{expiry}.{nonce}"
        if len(nonce) != 32 or int(expiry) < time.time() or not hmac.compare_digest(mac, signature(value)):
            return None
        return token
    except (ValueError, TypeError):
        return None


def require_session(request: Request) -> str:
    token = check_session(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        provided = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(provided, signature("csrf:" + token)):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return token


@app.get("/api/v1/health")
def health():
    return {"ok": True, "version": "0.1.0"}


@app.get("/api/v1/session")
def session(request: Request):
    token = check_session(request)
    return {"authenticated": bool(token), "csrf_token": signature("csrf:" + token) if token else None}


@app.post("/api/v1/session/login")
def login(payload: Login, request: Request, response: Response):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Origin mismatch")
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = [t for t in failed_logins.get(ip, []) if now - t < 60]
    if len(attempts) >= 5:
        raise HTTPException(429, "Too many attempts; retry in a minute")
    if not hmac.compare_digest(payload.password.encode(), ADMIN_PASSWORD.encode()):
        failed_logins[ip] = (attempts + [now])[-10:]
        raise HTTPException(401, "Invalid password")
    failed_logins.pop(ip, None)
    token = make_token()
    # For HTTP on a trusted LAN. Behind HTTPS, set HUB_COOKIE_SECURE=1.
    response.set_cookie("hub_session", token, httponly=True, samesite="strict",
                        secure=os.environ.get("HUB_COOKIE_SECURE") == "1", max_age=SESSION_TTL, path="/")
    return {"authenticated": True, "csrf_token": signature("csrf:" + token)}


@app.post("/api/v1/session/logout")
def logout(response: Response, _: Annotated[str, Depends(require_session)]):
    response.delete_cookie("hub_session", path="/")
    return {"ok": True}


META_FIELDS = tuple(Metadata.model_fields)


def get_project(conn: sqlite3.Connection, project_id: str, include_deleted: bool = False):
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row or (row["deleted_at"] and not include_deleted):
        raise HTTPException(404, "Project not found")
    return row


def project_assets(conn, project_id: str, active_only: bool = True):
    clause = " AND active=1" if active_only else ""
    return [dict(r) for r in conn.execute("SELECT * FROM assets WHERE project_id=?" + clause + " ORDER BY created_at,id", (project_id,))]


def snapshot(conn, project_id: str):
    row = get_project(conn, project_id, include_deleted=True)
    return {
        "metadata": {name: row[name] for name in META_FIELDS},
        "manifest": json.loads(row["manifest"]),
        "asset_ids": [a["id"] for a in project_assets(conn, project_id)],
        "cover_asset_id": row["cover_asset_id"],
    }


def record_revision(conn, project_id: str, number: int):
    now = timestamp()
    conn.execute("INSERT INTO revisions(project_id,number,snapshot,created_at) VALUES(?,?,?,?)",
                 (project_id, number, json.dumps(snapshot(conn, project_id), separators=(",", ":")), now))


def bump_revision(conn, project_id: str):
    row = get_project(conn, project_id)
    number = row["revision"] + 1
    conn.execute("UPDATE projects SET revision=?,updated_at=? WHERE id=?", (number, timestamp(), project_id))
    record_revision(conn, project_id, number)
    return number


def check_revision(row, expected: int):
    if row["revision"] != expected:
        raise HTTPException(409, f"Revision conflict: current revision is {row['revision']}")


def serialize_project(conn, row, details: bool = False):
    result = {key: row[key] for key in (
        "id", *META_FIELDS, "revision", "cover_asset_id", "created_at", "updated_at", "deleted_at")}
    if details:
        result["assets"] = project_assets(conn, row["id"])
        result["manifest"] = json.loads(row["manifest"])
    return result


def check_manifest(value: dict[str, Any]):
    if value.get("schema_version") != "1.0" or not isinstance(value.get("tracks"), list) or not isinstance(value.get("settings"), dict):
        raise HTTPException(422, "Manifest must contain schema_version='1.0', settings object and tracks array")
    if len(json.dumps(value)) > 512_000:
        raise HTTPException(413, "Manifest exceeds 512 KB")
    if len(value["tracks"]) > 256:
        raise HTTPException(422, "Too many tracks")


@app.post("/api/v1/projects", status_code=201)
def create_project(data: CreateProject, _: Annotated[str, Depends(require_session)]):
    project_id = str(uuid.uuid4())
    now = timestamp()
    manifest = {"schema_version": "1.0", "settings": {"bpm": data.bpm, "key": data.musical_key, "time_signature": data.time_signature}, "tracks": []}
    values = data.model_dump()
    with db(write=True) as conn:
        cols = ("id", *META_FIELDS, "manifest", "created_at", "updated_at")
        args = (project_id, *(values[k] for k in META_FIELDS), json.dumps(manifest), now, now)
        conn.execute(f"INSERT INTO projects({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", args)
        record_revision(conn, project_id, 1)
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.get("/api/v1/projects")
def list_projects(_: Annotated[str, Depends(require_session)], q: str = "", artist: str = "", album: str = "", genre: str = "", musical_key: str = "", bpm: int | None = None, bpm_min: int | None = None, bpm_max: int | None = None, has_midi: bool | None = None, has_audio: bool | None = None, trash: bool = False, limit: int = 30, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "limit must be 1..100 and offset nonnegative")
    if bpm_min is not None and bpm_max is not None and bpm_min > bpm_max:
        raise HTTPException(422, "Invalid BPM range")
    conditions = ["p.deleted_at IS NOT NULL" if trash else "p.deleted_at IS NULL"]
    args: list[Any] = []
    for col, val in (("artist", artist), ("album", album), ("genre", genre), ("musical_key", musical_key)):
        if val.strip():
            conditions.append(f"LOWER(p.{col})=LOWER(?)")
            args.append(val.strip())
    if q.strip():
        conditions.append("(p.title LIKE ? OR p.artist LIKE ? OR p.album LIKE ? OR p.description LIKE ?)")
        args.extend(["%" + q.strip() + "%"] * 4)
    for operator, val in (("=", bpm), (">=", bpm_min), ("<=", bpm_max)):
        if val is not None:
            conditions.append(f"p.bpm {operator} ?")
            args.append(val)
    for kind, enabled in (("midi", has_midi), ("wav", has_audio)):
        if enabled is not None:
            exists = "EXISTS" if enabled else "NOT EXISTS"
            conditions.append(f"{exists} (SELECT 1 FROM assets a WHERE a.project_id=p.id AND a.active=1 AND a.kind=?)")
            args.append(kind)
    where = " AND ".join(conditions)
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM projects p WHERE {where}", args).fetchone()[0]
        rows = conn.execute(f"SELECT p.* FROM projects p WHERE {where} ORDER BY p.updated_at DESC,p.id DESC LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return {"items": [serialize_project(conn, r) for r in rows], "total": total, "limit": limit, "offset": offset}


@app.get("/api/v1/projects/{project_id}")
def read_project(project_id: str, _: Annotated[str, Depends(require_session)]):
    with db() as conn:
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.patch("/api/v1/projects/{project_id}/metadata")
def update_metadata(project_id: str, data: UpdateMetadata, _: Annotated[str, Depends(require_session)]):
    with db(write=True) as conn:
        check_revision(get_project(conn, project_id), data.expected_revision)
        meta = data.metadata.model_dump()
        conn.execute("UPDATE projects SET " + ",".join(f"{k}=?" for k in META_FIELDS) + " WHERE id=?", (*[meta[k] for k in META_FIELDS], project_id))
        bump_revision(conn, project_id)
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.put("/api/v1/projects/{project_id}/document")
def save_document(project_id: str, data: SaveDocument, _: Annotated[str, Depends(require_session)]):
    check_manifest(data.manifest)
    with db(write=True) as conn:
        check_revision(get_project(conn, project_id), data.expected_revision)
        conn.execute("UPDATE projects SET manifest=? WHERE id=?", (json.dumps(data.manifest), project_id))
        bump_revision(conn, project_id)
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.get("/api/v1/projects/{project_id}/revisions")
def revisions(project_id: str, _: Annotated[str, Depends(require_session)]):
    with db() as conn:
        get_project(conn, project_id)
        return {"items": [dict(r) for r in conn.execute("SELECT number,created_at FROM revisions WHERE project_id=? ORDER BY number DESC", (project_id,))]}


@app.get("/api/v1/projects/{project_id}/revisions/{number}")
def read_revision(project_id: str, number: int, _: Annotated[str, Depends(require_session)]):
    with db() as conn:
        get_project(conn, project_id)
        row = conn.execute("SELECT * FROM revisions WHERE project_id=? AND number=?", (project_id, number)).fetchone()
        if not row:
            raise HTTPException(404, "Revision not found")
        return {"number": number, "created_at": row["created_at"], "snapshot": json.loads(row["snapshot"])}


@app.post("/api/v1/projects/{project_id}/revisions/{number}/restore")
def restore_revision(project_id: str, number: int, data: ExpectedRevision, _: Annotated[str, Depends(require_session)]):
    with db(write=True) as conn:
        check_revision(get_project(conn, project_id), data.expected_revision)
        rev = conn.execute("SELECT snapshot FROM revisions WHERE project_id=? AND number=?", (project_id, number)).fetchone()
        if not rev:
            raise HTTPException(404, "Revision not found")
        snap = json.loads(rev["snapshot"])
        metadata = Metadata.model_validate(snap["metadata"]).model_dump()
        check_manifest(snap["manifest"])
        ids = set(snap["asset_ids"])
        known = {r["id"] for r in project_assets(conn, project_id, active_only=False)}
        if not ids.issubset(known):
            raise HTTPException(409, "Revision contains unavailable assets")
        cover = snap.get("cover_asset_id")
        if cover and cover not in ids:
            raise HTTPException(409, "Revision cover is not an active asset")
        conn.execute("UPDATE projects SET " + ",".join(f"{k}=?" for k in META_FIELDS) + ",manifest=?,cover_asset_id=? WHERE id=?", (*[metadata[k] for k in META_FIELDS], json.dumps(snap["manifest"]), cover, project_id))
        conn.execute("UPDATE assets SET active=0 WHERE project_id=?", (project_id,))
        for asset_id in ids:
            conn.execute("UPDATE assets SET active=1 WHERE project_id=? AND id=?", (project_id, asset_id))
        bump_revision(conn, project_id)
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.delete("/api/v1/projects/{project_id}")
def trash_project(project_id: str, data: ExpectedRevision, _: Annotated[str, Depends(require_session)]):
    with db(write=True) as conn:
        check_revision(get_project(conn, project_id), data.expected_revision)
        conn.execute("UPDATE projects SET deleted_at=? WHERE id=?", (timestamp(), project_id))
        return {"ok": True}


@app.post("/api/v1/projects/{project_id}/restore")
def restore_project(project_id: str, _: Annotated[str, Depends(require_session)]):
    with db(write=True) as conn:
        row = get_project(conn, project_id, include_deleted=True)
        if row["deleted_at"] is None:
            raise HTTPException(409, "Project is not in trash")
        conn.execute("UPDATE projects SET deleted_at=NULL,updated_at=? WHERE id=?", (timestamp(), project_id))
        return serialize_project(conn, get_project(conn, project_id))


ALLOWED = {
    "wav": ("audio/wav", (".wav",)),
    "midi": ("audio/midi", (".mid", ".midi")),
    "cover": ("image/", (".png", ".jpg", ".jpeg", ".webp")),
}


def media_type(kind: str, filename: str, header: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if kind not in ALLOWED or ext not in ALLOWED[kind][1]:
        raise HTTPException(415, "Only WAV, MIDI and PNG/JPEG/WebP cover art are supported")
    if kind == "wav" and not (header.startswith(b"RIFF") and header[8:12] == b"WAVE"):
        raise HTTPException(415, "Not a valid WAV header")
    if kind == "midi" and not header.startswith(b"MThd"):
        raise HTTPException(415, "Not a valid MIDI header")
    if kind == "cover":
        if ext == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if ext in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if ext == ".webp" and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "image/webp"
        raise HTTPException(415, "Invalid cover art header")
    return ALLOWED[kind][0]


@app.post("/api/v1/projects/{project_id}/assets", status_code=201)
async def upload_asset(project_id: str, _: Annotated[str, Depends(require_session)], file: UploadFile = File(...), kind: Literal["wav", "midi", "cover"] = Form(...), expected_revision: int = Form(...)):
    # Preflight revision, and repeat it when committing to prevent lost updates.
    with db() as conn:
        check_revision(get_project(conn, project_id), expected_revision)
    filename = Path(file.filename or "").name
    if not filename or len(filename) > 240:
        raise HTTPException(422, "Invalid file name")
    header = await file.read(16)
    content_type = media_type(kind, filename, header)
    asset_id = str(uuid.uuid4())
    fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=ASSET_DIR)
    size, digest = 0, hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as output:
            for chunk in [header]:
                size += len(chunk); digest.update(chunk); output.write(chunk)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Upload exceeds configured limit")
                digest.update(chunk)
                output.write(chunk)
        final_path = ASSET_DIR / asset_id
        os.replace(temp_name, final_path)
        try:
            with db(write=True) as conn:
                check_revision(get_project(conn, project_id), expected_revision)
                conn.execute("INSERT INTO assets(id,project_id,filename,kind,content_type,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?)", (asset_id, project_id, filename, kind, content_type, size, digest.hexdigest(), timestamp()))
                if kind == "cover":
                    conn.execute("UPDATE projects SET cover_asset_id=? WHERE id=?", (asset_id, project_id))
                bump_revision(conn, project_id)
                return serialize_project(conn, get_project(conn, project_id), details=True)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
    finally:
        Path(temp_name).unlink(missing_ok=True)
        await file.close()


@app.get("/api/v1/projects/{project_id}/assets/{asset_id}/content")
def download_asset(project_id: str, asset_id: str, _: Annotated[str, Depends(require_session)]):
    with db() as conn:
        get_project(conn, project_id)
        row = conn.execute("SELECT * FROM assets WHERE id=? AND project_id=?", (asset_id, project_id)).fetchone()
        if not row:
            raise HTTPException(404, "Asset not found")
        path = ASSET_DIR / row["id"]
        if not path.is_file():
            raise HTTPException(503, "Asset data unavailable")
        return FileResponse(path, media_type=row["content_type"], filename=row["filename"], content_disposition_type="inline" if row["kind"] == "cover" else "attachment", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@app.delete("/api/v1/projects/{project_id}/assets/{asset_id}")
def remove_asset(project_id: str, asset_id: str, data: ExpectedRevision, _: Annotated[str, Depends(require_session)]):
    with db(write=True) as conn:
        check_revision(get_project(conn, project_id), data.expected_revision)
        row = conn.execute("SELECT id FROM assets WHERE id=? AND project_id=? AND active=1", (asset_id, project_id)).fetchone()
        if not row:
            raise HTTPException(404, "Active asset not found")
        conn.execute("UPDATE assets SET active=0 WHERE id=?", (asset_id,))
        conn.execute("UPDATE projects SET cover_asset_id=NULL WHERE id=? AND cover_asset_id=?", (project_id, asset_id))
        bump_revision(conn, project_id)
        return serialize_project(conn, get_project(conn, project_id), details=True)


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})
