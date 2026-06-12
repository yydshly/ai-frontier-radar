"""Shared helpers for validating externally fetched URLs."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def is_safe_external_url(url: str | None) -> bool:
    """Allow HTTP(S) URLs while rejecting local and private literal hosts."""
    if not url:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        return False

    value = url.strip(" ")
    if not value:
        return False

    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").strip().lower()
        _ = parsed.port
    except (TypeError, ValueError):
        return False

    if parsed.scheme.lower() not in {"http", "https"} or not host:
        return False
    if parsed.username or parsed.password:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return bool(address.is_global)
