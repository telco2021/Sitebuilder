"""The rewrite must not carry legacy binaries, scripts, or callback code."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TEXT = (
    "ATSSecurePost",
    "ATS.securepost",
    "transact.dll",
    "HitDummyPage",
    "DownloadData(",
    "liquidsolution.net",
    "Server.CreateObject",
    "CreateObject(",
    "xp_cmdshell",
    "cmd.exe",
    "powershell",
)

FORBIDDEN_SUFFIXES = {".dll", ".aspx", ".vb", ".asax", ".pdb", ".mdf", ".ldf", ".suo", ".swf"}


def test_legacy_payloads_are_not_in_the_tree():
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".pytest_cache" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "test_quarantine.py":
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            offenders.append(str(path.relative_to(ROOT)))
            continue
        if path.suffix.lower() not in {".py", ".html", ".css", ".txt", ".md", ".toml", ".example"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_TEXT:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle}")
    assert offenders == []


def test_application_code_does_not_open_outbound_http():
    liquid = ROOT / "liquid"
    for path in liquid.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "urllib.request" not in text
        assert "import socket" not in text
        assert "import requests" not in text
        assert "httpx" not in text
