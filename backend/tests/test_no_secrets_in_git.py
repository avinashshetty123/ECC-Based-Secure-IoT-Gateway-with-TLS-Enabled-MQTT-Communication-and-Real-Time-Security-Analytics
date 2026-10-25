"""Security test 10: private keys and secrets are never committed.

Checks the files Git TRACKS (git ls-files), not just .gitignore, and scans their
contents for private-key blocks and the generated passwords.
"""
import json
import re
import subprocess

import pytest

from app.config import ROOT, SECRETS_FILE

PEM_KEY = re.compile(r"-----BEGIN (?:EC |RSA |ENCRYPTED )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{40,}")
FORBIDDEN_SUFFIXES =(".key", ".pem", ".p12", ".pfx", ".csr", ".db", ".sqlite", ".env")
FORBIDDEN_PATHS = ("config/secrets/", "certificates/ca/", "certificates/server/", "certificates/clients/",
                   "certificates/negative/", "data/")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git repository / git not available")
    return [line for line in out.splitlines() if line]


def test_no_secret_files_tracked():
    bad = [f for f in _tracked() if f.endswith(FORBIDDEN_SUFFIXES) or f.startswith(FORBIDDEN_PATHS)
           or f in ("config/passwd",)]
    assert not bad, f"secret material tracked by git: {bad}"


def test_no_private_key_or_password_in_tracked_content():
    secrets = []
    if SECRETS_FILE.exists():
        secrets = [s for s in json.loads(SECRETS_FILE.read_text(encoding="utf-8")).values() if len(s) >= 8]
    offenders = []
    for f in _tracked():
        path = ROOT / f
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PEM_KEY.search(text):  # a real key block: header followed by base64 data
            offenders.append(f"{f}: private key block")
        for s in secrets:
            if s in text:
                offenders.append(f"{f}: contains a generated password")
    assert not offenders, offenders


def test_gitignore_covers_secret_locations():
    rules = (ROOT.parent / ".gitignore").read_text(encoding="utf-8")  # repository root (ROOT is backend/)
    for needed in ("*.key", "config/secrets/", "certificates/**", ".env", "*.db"):
        assert needed in rules, f".gitignore is missing {needed}"
