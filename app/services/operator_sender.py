from aiogram import Bot
from sqlalchemy.orm import Session

from ..models import Chat
from .chat_service import save_outgoing_message


async def send_operator_message(db: Session, chat: Chat, text: str):
    if not chat.telegram_bot:
        raise ValueError("Для цього чату не знайдено Telegram-бота")

    message_text = (text or "").strip()
    if not message_text:
        raise ValueError("Повідомлення не може бути порожнім")

    bot = Bot(token=chat.telegram_bot.token)
    try:
        sent = await bot.send_message(chat_id=int(chat.chat_id), text=message_text)
    finally:
        await bot.session.close()

    return save_outgoing_message(
        db=db,
        chat=chat,
        text=message_text,
        telegram_message_id=sent.message_id,
    )
