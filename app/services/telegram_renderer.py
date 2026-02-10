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


async def send_flow_events(bot: Bot, chat_id: int, events: List[Dict[str, Any]]) -> None:
    for event in events or []:
        event_type = event.get("type")

        if event_type == "message":
            await bot.send_message(
                chat_id=chat_id,
                text=_safe_text(event.get("text"), "..."),
            )
            continue

        if event_type == "buttons":
            await bot.send_message(
                chat_id=chat_id,
                text=_safe_text(event.get("text"), "Оберіть кнопку"),
                reply_markup=build_buttons_markup(event.get("buttons") or []),
            )
            continue

        if event_type == "input":
            await bot.send_message(
                chat_id=chat_id,
                text=_safe_text(event.get("question"), "Введіть текст"),
            )
            continue

        if event_type == "end":
            # Do not send a final "scenario finished" message to Telegram chat.
            continue

        if event_type == "error":
            await bot.send_message(
                chat_id=chat_id,
                text="Помилка: " + _safe_text(event.get("text"), "невідома помилка"),
            )
