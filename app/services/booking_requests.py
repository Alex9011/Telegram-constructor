from typing import Any, Dict

from sqlalchemy.orm import Session

from ..models import BookingRequest, Chat


def _value_as_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def create_booking_request_from_chat(
    db: Session,
    chat: Chat,
    variables: Dict[str, Any],
) -> BookingRequest:
    if not chat.telegram_bot:
        raise ValueError("Для чату не знайдено Telegram-бота")

    payload = variables or {}

    booking = BookingRequest(
        project_id=chat.telegram_bot.project_id,
        telegram_user_id=_value_as_text(chat.telegram_user_id),
        client_name=_value_as_text(payload.get("client_name"), "Невідомо"),
        client_phone=_value_as_text(payload.get("client_phone"), "Невідомо"),
        selected_service=_value_as_text(payload.get("selected_service"), "Не обрано"),
        selected_barber=_value_as_text(payload.get("selected_barber"), "Не обрано"),
        booking_date=_value_as_text(payload.get("booking_date"), "Не вказано"),
        booking_time=_value_as_text(payload.get("booking_time"), "Не вказано"),
        comment=_value_as_text(payload.get("comment"), "без коментаря"),
        status="new",
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking
