"""Carrier webhook signatures.

A carrier signs each delivery with a shared secret::

    X-Carrier-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">

The timestamp is part of the signed material, so a captured request cannot be
replayed once it is older than the configured tolerance. Several ``v1`` values
may be sent during a secret rotation; one valid value is enough.
"""

import hashlib
import hmac
import json
from typing import Any

SIGNATURE_HEADER = "X-Carrier-Signature"
_SCHEME = "v1"


class InvalidSignatureError(Exception):
    """The signature header is missing, malformed, stale or does not match."""


def compute_signature(secret: str, body: bytes, timestamp: int) -> str:
    signed = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def build_signature_header(secret: str, body: bytes, timestamp: int) -> str:
    return f"t={timestamp},{_SCHEME}={compute_signature(secret, body, timestamp)}"


def verify_signature(
    *, secret: str, body: bytes, header: str | None, now: float, tolerance_seconds: int
) -> None:
    if not header:
        raise InvalidSignatureError("missing signature header")

    timestamp: int | None = None
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise InvalidSignatureError("malformed signature timestamp") from None
        elif key == _SCHEME:
            candidates.append(value)

    if timestamp is None or not candidates:
        raise InvalidSignatureError("malformed signature header")
    if abs(now - timestamp) > tolerance_seconds:
        raise InvalidSignatureError("signature timestamp outside tolerance")

    expected = compute_signature(secret, body, timestamp)
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise InvalidSignatureError("signature mismatch")


def hash_payload(payload: dict[str, Any]) -> str:
    """Stable fingerprint of a JSON payload, independent of key order and whitespace."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
