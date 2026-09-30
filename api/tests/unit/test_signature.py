import pytest

from parcelpulse_api.security import (
    InvalidSignatureError,
    build_signature_header,
    compute_signature,
    hash_payload,
    verify_signature,
)

SECRET = "unit-test-secret-0123456789"
BODY = b'{"event_id":"evt_1"}'
NOW = 1_790_000_000


def verify(
    header: str | None, *, body: bytes = BODY, secret: str = SECRET, now: float = NOW
) -> None:
    verify_signature(secret=secret, body=body, header=header, now=now, tolerance_seconds=300)


def test_valid_signature_is_accepted() -> None:
    verify(build_signature_header(SECRET, BODY, NOW))


def test_signature_within_tolerance_is_accepted() -> None:
    verify(build_signature_header(SECRET, BODY, NOW - 299))
    verify(build_signature_header(SECRET, BODY, NOW + 299))


@pytest.mark.parametrize("header", [None, "", "garbage", "t=abc,v1=00", "v1=00", f"t={NOW}"])
def test_missing_or_malformed_header_is_rejected(header: str | None) -> None:
    with pytest.raises(InvalidSignatureError):
        verify(header)


def test_wrong_secret_is_rejected() -> None:
    with pytest.raises(InvalidSignatureError, match="mismatch"):
        verify(build_signature_header("another-secret-0123456789", BODY, NOW))


def test_tampered_body_is_rejected() -> None:
    header = build_signature_header(SECRET, BODY, NOW)
    with pytest.raises(InvalidSignatureError, match="mismatch"):
        verify(header, body=b'{"event_id":"evt_2"}')


def test_stale_timestamp_is_rejected_even_with_valid_mac() -> None:
    header = build_signature_header(SECRET, BODY, NOW - 301)
    with pytest.raises(InvalidSignatureError, match="tolerance"):
        verify(header)


def test_timestamp_cannot_be_swapped_without_invalidating_the_mac() -> None:
    old_mac = compute_signature(SECRET, BODY, NOW - 10_000)
    with pytest.raises(InvalidSignatureError, match="mismatch"):
        verify(f"t={NOW},v1={old_mac}")


def test_any_matching_v1_value_is_accepted_during_secret_rotation() -> None:
    valid = compute_signature(SECRET, BODY, NOW)
    verify(f"t={NOW},v1={'0' * 64},v1={valid}")


def test_payload_hash_ignores_key_order_and_whitespace() -> None:
    first = {"event_id": "evt_1", "location": {"city": "Leeds", "country": "GB"}}
    second = {"location": {"country": "GB", "city": "Leeds"}, "event_id": "evt_1"}
    assert hash_payload(first) == hash_payload(second)


def test_payload_hash_changes_with_content() -> None:
    assert hash_payload({"event_id": "evt_1", "event_type": "DELIVERED"}) != hash_payload(
        {"event_id": "evt_1", "event_type": "IN_TRANSIT"}
    )
