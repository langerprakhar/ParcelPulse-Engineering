"""Shipment registration and lookup."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from parcelpulse_api.domain.status import ShipmentStatus
from parcelpulse_api.errors import AppError, ConflictError, NotFoundError
from parcelpulse_api.models import Shipment


class ShipmentNotFoundError(NotFoundError):
    code = "shipment_not_found"


class ShipmentAlreadyExistsError(ConflictError):
    code = "shipment_already_exists"


class AmbiguousTrackingNumberError(ConflictError):
    code = "ambiguous_tracking_number"


class UnsupportedCarrierError(AppError):
    status_code = 422
    code = "unsupported_carrier"


def create_shipment(
    session: Session, *, tracking_number: str, carrier: str, supported_carriers: Sequence[str]
) -> Shipment:
    if carrier not in supported_carriers:
        raise UnsupportedCarrierError(
            f"Carrier '{carrier}' is not supported",
            details={"supported_carriers": sorted(supported_carriers)},
        )

    # ON CONFLICT keeps concurrent registrations of the same parcel from racing
    # each other into an IntegrityError: exactly one insert wins.
    inserted_id = session.execute(
        pg_insert(Shipment)
        .values(id=uuid.uuid4(), tracking_number=tracking_number, carrier=carrier)
        .on_conflict_do_nothing(constraint="uq_shipments_carrier_tracking_number")
        .returning(Shipment.id)
    ).scalar_one_or_none()

    if inserted_id is None:
        existing = session.execute(
            select(Shipment).where(
                Shipment.carrier == carrier, Shipment.tracking_number == tracking_number
            )
        ).scalar_one()
        raise ShipmentAlreadyExistsError(
            f"Shipment {tracking_number} is already tracked for carrier '{carrier}'",
            details={"shipment_id": str(existing.id)},
        )

    return session.execute(select(Shipment).where(Shipment.id == inserted_id)).scalar_one()


def get_shipment(session: Session, shipment_id: uuid.UUID) -> Shipment:
    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise ShipmentNotFoundError(f"Shipment {shipment_id} not found")
    return shipment


def get_shipment_by_tracking_number(
    session: Session, tracking_number: str, carrier: str | None = None
) -> Shipment:
    query = select(Shipment).where(Shipment.tracking_number == tracking_number)
    if carrier is not None:
        query = query.where(Shipment.carrier == carrier)
    matches = session.execute(query.order_by(Shipment.carrier)).scalars().all()

    if not matches:
        raise ShipmentNotFoundError(f"No shipment with tracking number {tracking_number}")
    if len(matches) > 1:
        raise AmbiguousTrackingNumberError(
            f"Tracking number {tracking_number} exists for more than one carrier",
            details={"carriers": [match.carrier for match in matches]},
        )
    return matches[0]


def list_shipments(
    session: Session, *, limit: int, offset: int, status: ShipmentStatus | None = None
) -> tuple[list[Shipment], int]:
    query = select(Shipment)
    count_query = select(func.count()).select_from(Shipment)
    if status is not None:
        query = query.where(Shipment.current_status == status)
        count_query = count_query.where(Shipment.current_status == status)

    total = session.execute(count_query).scalar_one()
    items = (
        session.execute(
            query.order_by(Shipment.created_at.desc(), Shipment.id).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(items), total
