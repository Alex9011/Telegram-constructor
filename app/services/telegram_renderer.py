from typing import Any, Dict, List

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _safe_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def build_buttons_markup(buttons: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for index, button in enumerate(buttons or []):
        label = _safe_text((button or {}).get("label"), f"Кнопка {index + 1}")
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"choose:{index}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_flow_events(bot: Bot, chat_id: int, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sent_items: List[Dict[str, Any]] = []

    for event in events or []:
        event_type = event.get("type")

        if event_type == "message":
            text = _safe_text(event.get("text"), "...")
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
            )
            sent_items.append(
                {
                    "text": text,
                    "telegram_message_id": sent.message_id,
                }
            )
            continue

        if event_type == "buttons":
            text = _safe_text(event.get("text"), "Оберіть кнопку")
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=build_buttons_markup(event.get("buttons") or []),
            )
            sent_items.append(
                {
                    "text": text,
                    "telegram_message_id": sent.message_id,
                }
            )
            continue

        if event_type == "input":
            text = _safe_text(event.get("question"), "Введіть текст")
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
            )
            sent_items.append(
                {
                    "text": text,
                    "telegram_message_id": sent.message_id,
                }
            )
            continue

        if event_type == "end":
            # Do not send a final "scenario finished" message to Telegram chat.
            continue

        if event_type == "error":
            text = "Помилка: " + _safe_text(event.get("text"), "невідома помилка")
            sent = await bot.send_message(
                chat_id=chat_id,
                text=text,
            )
            sent_items.append(
                {
                    "text": text,
                    "telegram_message_id": sent.message_id,
                }
            )

    return sent_items
