import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from parcelpulse_api.errors import AppError
from parcelpulse_api.models import Shipment
from parcelpulse_api.services import shipments as shipment_service


def register(client: TestClient, tracking_number: str, carrier: str = "simcarrier") -> dict:
    response = client.post(
        "/shipments", json={"tracking_number": tracking_number, "carrier": carrier}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_shipment_persists_and_returns_created_state(
    client: TestClient, db: Session
) -> None:
    response = client.post(
        "/shipments", json={"tracking_number": "SC4F7K2M9Q1X", "carrier": "simcarrier"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["tracking_number"] == "SC4F7K2M9Q1X"
    assert body["carrier"] == "simcarrier"
    assert body["current_status"] == "CREATED"
    assert body["estimated_delivery_at"] is None
    assert body["last_event_at"] is None
    assert response.headers["Location"] == f"/shipments/{body['id']}"

    stored = db.get(Shipment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.tracking_number == "SC4F7K2M9Q1X"
    assert stored.created_at.tzinfo is not None


def test_tracking_number_is_normalized(client: TestClient) -> None:
    body = register(client, "  sc4f-7k2m 9q1x ")
    assert body["tracking_number"] == "SC4F7K2M9Q1X"


def test_registering_the_same_shipment_twice_conflicts(client: TestClient, db: Session) -> None:
    first = register(client, "SC4F7K2M9Q1X")

    response = client.post(
        "/shipments", json={"tracking_number": "sc4f7k2m9q1x", "carrier": "simcarrier"}
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "shipment_already_exists"
    assert error["details"] == {"shipment_id": first["id"]}
    assert db.execute(select(func.count()).select_from(Shipment)).scalar_one() == 1


def test_concurrent_registration_creates_exactly_one_shipment(
    session_factory: sessionmaker[Session], db: Session
) -> None:
    def attempt(_: int) -> str:
        with session_factory() as session:
            try:
                with session.begin():
                    shipment_service.create_shipment(
                        session,
                        tracking_number="SCRACE000001",
                        carrier="simcarrier",
                        supported_carriers=["simcarrier"],
                    )
                return "created"
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))

    assert outcomes.count("created") == 1
    assert outcomes.count("shipment_already_exists") == 7
    assert db.execute(select(func.count()).select_from(Shipment)).scalar_one() == 1


def test_unsupported_carrier_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/shipments", json={"tracking_number": "SC4F7K2M9Q1X", "carrier": "pigeonpost"}
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unsupported_carrier"
    assert error["details"] == {"supported_carriers": ["simcarrier"]}


def test_invalid_tracking_number_is_rejected_with_field_location(client: TestClient) -> None:
    response = client.post("/shipments", json={"tracking_number": "bad!", "carrier": "simcarrier"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "tracking_number"]
    assert "bad!" not in response.text


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/shipments",
        json={"tracking_number": "SC4F7K2M9Q1X", "carrier": "simcarrier", "current_status": "X"},
    )
    assert response.status_code == 422


def test_get_shipment_by_id(client: TestClient) -> None:
    created = register(client, "SC4F7K2M9Q1X")

    response = client.get(f"/shipments/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_shipment_returns_404(client: TestClient) -> None:
    response = client.get(f"/shipments/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "shipment_not_found"


def test_get_shipment_with_malformed_id_returns_422(client: TestClient) -> None:
    response = client.get("/shipments/not-a-uuid")
    assert response.status_code == 422


def test_lookup_by_tracking_number_normalizes_input(client: TestClient) -> None:
    created = register(client, "SC4F7K2M9Q1X")

    response = client.get("/shipments/by-tracking/sc4f7k2m9q1x")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_lookup_by_unknown_tracking_number_returns_404(client: TestClient) -> None:
    response = client.get("/shipments/by-tracking/SC0000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "shipment_not_found"


def test_lookup_by_tracking_number_shared_by_two_carriers_is_ambiguous(
    client: TestClient, db: Session
) -> None:
    # Only one carrier is supported through the API today, so arrange the
    # second row directly.
    created = register(client, "SC4F7K2M9Q1X")
    db.add(Shipment(tracking_number="SC4F7K2M9Q1X", carrier="othercarrier"))
    db.commit()

    ambiguous = client.get("/shipments/by-tracking/SC4F7K2M9Q1X")
    assert ambiguous.status_code == 409
    error = ambiguous.json()["error"]
    assert error["code"] == "ambiguous_tracking_number"
    assert error["details"] == {"carriers": ["othercarrier", "simcarrier"]}

    disambiguated = client.get("/shipments/by-tracking/SC4F7K2M9Q1X?carrier=simcarrier")
    assert disambiguated.status_code == 200
    assert disambiguated.json()["id"] == created["id"]


def test_list_shipments_is_paginated_newest_first(client: TestClient) -> None:
    created = [register(client, f"SCLIST00000{index}") for index in range(5)]

    first_page = client.get("/shipments?limit=2&offset=0").json()
    second_page = client.get("/shipments?limit=2&offset=2").json()
    last_page = client.get("/shipments?limit=2&offset=4").json()

    assert first_page["total"] == 5
    assert first_page["limit"] == 2
    assert first_page["offset"] == 0
    newest_first = [shipment["id"] for shipment in reversed(created)]
    listed = [item["id"] for page in (first_page, second_page, last_page) for item in page["items"]]
    assert listed == newest_first


def test_list_shipments_filters_by_status(client: TestClient, db: Session) -> None:
    register(client, "SCLIST000001")
    delivered = register(client, "SCLIST000002")
    db.get(Shipment, uuid.UUID(delivered["id"])).current_status = "DELIVERED"  # type: ignore[union-attr]
    db.commit()

    page = client.get("/shipments?status=DELIVERED").json()

    assert page["total"] == 1
    assert [item["id"] for item in page["items"]] == [delivered["id"]]


def test_list_rejects_out_of_range_pagination(client: TestClient) -> None:
    assert client.get("/shipments?limit=0").status_code == 422
    assert client.get("/shipments?limit=101").status_code == 422
    assert client.get("/shipments?offset=-1").status_code == 422


def test_carriers_endpoint_lists_supported_carriers(client: TestClient) -> None:
    response = client.get("/carriers")
    assert response.status_code == 200
    assert response.json() == {"items": [{"code": "simcarrier"}]}
