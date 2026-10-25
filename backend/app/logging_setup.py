"""Logging for every component, with secret redaction.

Every log record passes through RedactSecrets, which masks:
  * any password from config/secrets/credentials.json that appears verbatim
  * "password=..." / "password": "..." style fragments
  * PEM private-key blocks
so a careless log call can never leak a credential into logs/*.log.
"""
from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler

from app.config import LOG_DIR, SECRETS_FILE

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(password\"?\s*[:=]\s*\"?)([^\"\s,}]+)"),
]


class RedactSecrets(logging.Filter):
    def __init__(self):
        super().__init__()
        try:
            self._secrets = [s for s in json.loads(SECRETS_FILE.read_text(encoding="utf-8")).values() if len(s) >= 8]
        except (OSError, ValueError):
            self._secrets = []

    def redact(self, text: str) -> str:
        for s in self._secrets:
            if s in text:
                text = text.replace(s, "***")
        text = _PATTERNS[0].sub("[REDACTED PRIVATE KEY]", text)
        return _PATTERNS[1].sub(r"\1***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


def configure(name: str, level: int = logging.INFO, console: bool = True) -> logging.Logger:
    """Root logging -> logs/<name>.log (rotating, 1 MB x 3) + optional console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(name)-10s %(levelname)-7s %(message)s")
    redact = RedactSecrets()
    handlers: list[logging.Handler] = [RotatingFileHandler(LOG_DIR / f"{name}.log", maxBytes=1_000_000, backupCount=3,
                                                           encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler())
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(redact)
        root.addHandler(h)
    logging.getLogger("paho").setLevel(logging.WARNING)
    return logging.getLogger(name)
