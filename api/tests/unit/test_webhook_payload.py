import pytest
from pydantic import ValidationError

from parcelpulse_api.domain.status import EventType
from parcelpulse_api.schemas import CarrierEventPayload
from tests.helpers import carrier_event


def test_valid_payload_is_parsed_and_normalized() -> None:
    payload = CarrierEventPayload.model_validate(
        carrier_event(
            "OUT_FOR_DELIVERY",
            tracking_number=" sc4f-7k2m-9q1x ",
            provider="SimCarrier",
            location={"city": "Leeds", "country": "GB", "unexpected": "ignored"},
        )
    )

    assert payload.tracking_number == "SC4F7K2M9Q1X"
    assert payload.provider == "simcarrier"
    assert payload.event_type is EventType.OUT_FOR_DELIVERY
    assert payload.occurred_at.tzinfo is not None
    assert payload.location is not None
    assert payload.location.model_dump(exclude_none=True) == {"city": "Leeds", "country": "GB"}


def test_unknown_top_level_fields_are_accepted() -> None:
    payload = CarrierEventPayload.model_validate(carrier_event(carrier_service_level="express"))
    assert payload.model_extra == {"carrier_service_level": "express"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("occurred_at", "2026-09-01T08:00:00"),  # no UTC offset
        ("occurred_at", "yesterday"),
        ("event_type", "TELEPORTED"),
        ("event_id", ""),
        ("event_id", "has spaces"),
        ("event_id", "x" * 129),
        ("tracking_number", "short"),
        ("tracking_number", "DROP TABLE;--"),
        ("provider", "Not A Carrier!"),
        ("description", "x" * 501),
        ("estimated_delivery_at", "2026-09-03T18:00:00"),
    ],
)
def test_invalid_field_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        CarrierEventPayload.model_validate(carrier_event(**{field: value}))
    assert excinfo.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    "missing", ["provider", "event_id", "tracking_number", "event_type", "occurred_at"]
)
def test_required_field_missing_is_rejected(missing: str) -> None:
    data = carrier_event()
    del data[missing]
    with pytest.raises(ValidationError):
        CarrierEventPayload.model_validate(data)
