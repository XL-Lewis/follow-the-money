from pathlib import Path

import pytest

from ftm import cli


def test_cli_fetch_calls_run_fetch(monkeypatch, tmp_path: Path):
    called = {}

    def fake_run_fetch(cfg):
        called["cfg"] = cfg

    monkeypatch.setattr(cli, "run_fetch", fake_run_fetch)
    cli.main(["fetch", "--data-dir", str(tmp_path)])
    assert called["cfg"].data_dir == tmp_path


def test_cli_parse_calls_run_parse(monkeypatch, tmp_path: Path):
    called = {}

    def fake_run_parse(cfg):
        called["cfg"] = cfg

    monkeypatch.setattr(cli, "run_parse", fake_run_parse)
    cli.main(["parse", "--data-dir", str(tmp_path)])
    assert called["cfg"].data_dir == tmp_path


def test_cli_serve_invokes_web_run(monkeypatch, tmp_path: Path):
    called = {}

    def fake_run(cfg, *, host, port):
        called["cfg"] = cfg
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(cli.web_app, "run", fake_run)
    cli.main([
        "serve",
        "--data-dir",
        str(tmp_path),
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ])
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 8080


def test_cli_unknown_command_errors(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        cli.main(["frobnicate"])
