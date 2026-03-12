"""Tests for the piscal-processor-check-format CLI entrypoint."""

from __future__ import annotations

from pathlib import Path

import pytest

from piscal_processor import cli


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> Path:
    return FIXTURES / name


def test_check_format_main_ok(monkeypatch, capsys):
    path = _fixture("sampleinput.csv")
    monkeypatch.setenv("PYTHONWARNINGS", "ignore")  # keep output clean
    monkeypatch.setattr(
        cli,
        "_parse_check_format_args",
        lambda: type("Args", (), {"files": [str(path)], "strict": False})(),
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.check_format_main()

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_check_format_main_failure(monkeypatch, capsys, tmp_path: Path):
    bad = tmp_path / "not_piscal.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "_parse_check_format_args",
        lambda: type("Args", (), {"files": [str(bad)], "strict": False})(),
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.check_format_main()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "NOT PISCAL" in out

