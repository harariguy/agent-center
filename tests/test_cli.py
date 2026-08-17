"""CLI: the serve preflight — a taken port must fail loudly, not print a
banner pointing at someone else's server."""

from __future__ import annotations

import socket

from agent_center.cli import main


def test_serve_refuses_taken_port(capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen(1)
        port = squatter.getsockname()[1]

        assert main(["serve", "--port", str(port)]) == 1

    captured = capsys.readouterr()
    assert "cannot listen" in captured.err
    assert "--port" in captured.err
    # The friendly banner must not print for a server that never came up.
    assert "Agent Center →" not in captured.out
