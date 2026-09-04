"""Fixed renderer constants and context-specific escaping."""

from __future__ import annotations

import hashlib
import html
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..contracts import canonical_json


RENDERER_VERSION = "1"
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'none'; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
FORBIDDEN_QUERY_KEYS = frozenset(("key", "api_key", "apikey", "token", "access_token", "secret", "password", "authorization"))


@lru_cache(maxsize=1)
def renderer_css() -> str:
    path = Path(__file__).resolve().parents[3] / "assets" / "renderer.css"
    return path.read_text(encoding="utf-8").strip()


def text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def safe_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("renderer link must be credential-free HTTPS")
    keys = [part.split("=", 1)[0].lower() for part in parsed.query.split("&") if part]
    if any(key in FORBIDDEN_QUERY_KEYS for key in keys):
        raise ValueError("renderer link contains a forbidden credential query key")
    return value


def external_link(url: str, label: str) -> str:
    safe = safe_https_url(url)
    return '<a href="%s" rel="noopener noreferrer">%s</a>' % (attr(safe), text(label))


def dom_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return "%s-%s" % (prefix, digest)


def embedded_json(value: Any) -> str:
    encoded = canonical_json(value)
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

