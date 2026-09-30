"""The carrier's side of the webhook signature scheme.

    X-Carrier-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">

Implemented here independently of the receiver, from the documented contract,
so that the simulator behaves like a third party would.
"""

import hashlib
import hmac

SIGNATURE_HEADER = "X-Carrier-Signature"


def sign(secret: str, body: bytes, timestamp: int) -> str:
    signed = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"
