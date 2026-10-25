"""Generate random per-identity MQTT passwords and the Mosquitto password file.

Outputs (both git-ignored):
  config/secrets/credentials.json  - {username: password} for the Python apps
  config/secrets/passwd            - hashed password file read by Mosquitto

Usage (from project root):
  .venv\\Scripts\\python scripts\\setup_credentials.py [--devices 20] [--force]
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import MOSQUITTO_DIR, SECRETS_FILE, device_ids  # noqa: E402

SERVICE_USERS = ["gateway", "collector", "benchmark"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--devices", type=int, default=20, help="number of device identities (default 20)")
    parser.add_argument("--force", action="store_true", help="regenerate even if credentials exist")
    args = parser.parse_args()

    passwd_file = SECRETS_FILE.parent / "passwd"
    if SECRETS_FILE.exists() and passwd_file.exists() and not args.force:
        print(f"Credentials already exist at {SECRETS_FILE} (use --force to regenerate).")
        return 0

    tool = MOSQUITTO_DIR / "mosquitto_passwd.exe"
    if not tool.exists():
        print(f"ERROR: {tool} not found. Install Mosquitto or set MOSQUITTO_DIR.", file=sys.stderr)
        return 1

    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    users = SERVICE_USERS + device_ids(args.devices)
    creds = {u: secrets.token_urlsafe(18) for u in users}

    passwd_file.unlink(missing_ok=True)
    passwd_file.touch()
    for user, pw in creds.items():
        # -b = batch mode (password on the command line). Acceptable here: local,
        # single-user machine, and the password never appears in our logs.
        result = subprocess.run([str(tool), "-b", str(passwd_file), user, pw], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR adding {user}: {result.stderr.strip()}", file=sys.stderr)
            return 1

    SECRETS_FILE.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    print(f"Created {len(creds)} identities: {', '.join(SERVICE_USERS)}, {users[len(SERVICE_USERS)]}..{users[-1]}")
    print(f"  {SECRETS_FILE.relative_to(SECRETS_FILE.parents[2])}")
    print(f"  {passwd_file.relative_to(passwd_file.parents[2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
