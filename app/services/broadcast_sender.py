import asyncio
from typing import Any, Dict, List

from aiogram import Bot
from sqlalchemy.orm import Session, joinedload

from ..models import BroadcastCampaign, Chat, TelegramBot
from .chat_service import save_outgoing_message


async def _send_campaign_async(
    db: Session,
    campaign: BroadcastCampaign,
    chats: List[Chat],
    token: str,
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "sent": 0,
        "errors": 0,
        "total": len(chats),
        "error_details": [],
    }

    bot = Bot(token=token)
    try:
        for chat in chats:
            try:
                sent = await bot.send_message(chat_id=int(chat.chat_id), text=campaign.message_text)
                save_outgoing_message(
                    db=db,
                    chat=chat,
                    text=campaign.message_text,
                    telegram_message_id=sent.message_id,
                )
                stats["sent"] += 1
            except Exception as exc:
                stats["errors"] += 1
                if len(stats["error_details"]) < 20:
                    stats["error_details"].append(f"chat_id={chat.chat_id}: {exc}")
    finally:
        await bot.session.close()

    return stats


def send_campaign(db: Session, campaign: BroadcastCampaign) -> Dict[str, Any]:
    bot_config = db.query(TelegramBot).filter(TelegramBot.project_id == campaign.project_id).first()
    if not bot_config or not (bot_config.token or "").strip():
        return {
            "sent": 0,
            "errors": 0,
            "total": 0,
            "error_details": ["Для проєкту не налаштовано Telegram-бота"],
        }

    if not bot_config.is_active:
        return {
            "sent": 0,
            "errors": 0,
            "total": 0,
            "error_details": ["Telegram-бот вимкнено"],
        }

    chats = (
        db.query(Chat)
        .options(joinedload(Chat.telegram_bot))
        .filter(Chat.telegram_bot_id == bot_config.id)
        .order_by(Chat.id.asc())
        .all()
    )

    if not chats:
        return {
            "sent": 0,
            "errors": 0,
            "total": 0,
            "error_details": [],
        }

    return asyncio.run(
        _send_campaign_async(
            db=db,
            campaign=campaign,
            chats=chats,
            token=bot_config.token,
        )
    )
