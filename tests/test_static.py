"""Static UI serving — a build that lands after startup must serve without a
restart (the / route and the /assets mount must agree on when the UI exists)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_center import main as main_module
from agent_center.config import Settings
from agent_center.main import create_app


def make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(main_module, "STATIC_DIR", tmp_path)
    settings = Settings.from_env(database_url="sqlite://", admin_password="")
    return TestClient(create_app(settings), client=("127.0.0.1", 50000))


def test_ui_built_after_startup_serves_without_restart(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    # Before the build: the friendly hint, and a plain 404 for assets.
    assert "UI not built" in client.get("/").json()["detail"]
    assert client.get("/assets/index-abc123.js").status_code == 404

    # "pnpm build" runs while the server is up.
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('hi')")
    (tmp_path / "index.html").write_text("<!doctype html><div id='root'></div>")

    # Both halves appear immediately — no restart.
    assert client.get("/").status_code == 200
    r = client.get("/assets/index-abc123.js")
    assert r.status_code == 200
    assert "hi" in r.text
