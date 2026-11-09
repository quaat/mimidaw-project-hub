import importlib
import os
import secrets
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HUB_ADMIN_PASSWORD", "test-password-never-production")
    monkeypatch.setenv("HUB_SESSION_SECRET", secrets.token_hex(32))
    sys.modules.pop("hub.app", None)
    module = importlib.import_module("hub.app")
    with TestClient(module.app) as c:
        yield c
    sys.modules.pop("hub.app", None)


@pytest.fixture()
def auth(client):
    response = client.post("/api/v1/session/login", json={"password": "test-password-never-production"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture()
def project(client, auth):
    response = client.post("/api/v1/projects", json={"title": "Blue Morning", "artist": "Test Artist", "bpm": 92, "genre": "Jazz"}, headers=auth)
    assert response.status_code == 201
    return response.json()
