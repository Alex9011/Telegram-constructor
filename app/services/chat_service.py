from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from ..models import Chat, Message, TelegramBot


def _normalize_text(value: Optional[str]) -> str:
    text = (value or "").strip()
    return text


def _compose_full_name(first_name: Optional[str], last_name: Optional[str]) -> str:
    parts = [part.strip() for part in [first_name or "", last_name or ""] if part and part.strip()]
    return " ".join(parts)


def list_chats(db: Session, project_id: Optional[int] = None, limit: int = 200) -> List[Chat]:
    query = db.query(Chat).join(TelegramBot, Chat.telegram_bot_id == TelegramBot.id)
    if project_id is not None:
        query = query.filter(TelegramBot.project_id == project_id)

    return (
        query.options(joinedload(Chat.telegram_bot))
        .order_by(Chat.last_message_at.is_(None), Chat.last_message_at.desc(), Chat.id.desc())
        .limit(limit)
        .all()
    )


def get_chat_by_db_id(db: Session, chat_db_id: int) -> Optional[Chat]:
    return (
        db.query(Chat)
        .options(joinedload(Chat.telegram_bot))
        .filter(Chat.id == chat_db_id)
        .first()
    )


def get_chat_with_messages(db: Session, chat_db_id: int, limit: int = 400) -> Optional[Dict[str, Any]]:
    chat = get_chat_by_db_id(db, chat_db_id)
    if not chat:
        return None

    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_db_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
        .all()
    )

    return {
        "chat": chat,
        "messages": messages,
    }


def find_or_create_chat(
    db: Session,
    telegram_bot_id: int,
    telegram_user_id: int,
    telegram_chat_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> Chat:
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id)

    chat = (
        db.query(Chat)
        .filter(
            Chat.telegram_bot_id == telegram_bot_id,
            Chat.chat_id == telegram_chat_id_str,
        )
        .first()
    )

    full_name = _compose_full_name(first_name, last_name)

    if not chat:
        chat = Chat(
            telegram_bot_id=telegram_bot_id,
            telegram_user_id=telegram_user_id_str,
            chat_id=telegram_chat_id_str,
            username=(username or "").strip() or None,
            full_name=full_name or None,
            status="open",
            is_human_mode=False,
            unread_count=0,
        )
        db.add(chat)
        db.flush()
        return chat

    chat.telegram_user_id = telegram_user_id_str
    if username is not None:
        chat.username = (username or "").strip() or None
    if full_name:
        chat.full_name = full_name
    db.add(chat)
    db.flush()
    return chat


def save_incoming_message(
    db: Session,
    chat: Chat,
    text: str,
    telegram_message_id: Optional[int] = None,
) -> Message:
    normalized_text = _normalize_text(text)

    message = Message(
        chat_id=chat.id,
        direction="in",
        text=normalized_text,
        telegram_message_id=str(telegram_message_id) if telegram_message_id is not None else None,
    )
    db.add(message)

    chat.last_message_text = normalized_text
    chat.last_message_at = datetime.utcnow()
    chat.unread_count = (chat.unread_count or 0) + 1
    db.add(chat)

    db.commit()
    db.refresh(chat)
    db.refresh(message)
    return message


def save_outgoing_message(
    db: Session,
    chat: Chat,
    text: str,
    telegram_message_id: Optional[int] = None,
) -> Message:
    normalized_text = _normalize_text(text)

    message = Message(
        chat_id=chat.id,
        direction="out",
        text=normalized_text,
        telegram_message_id=str(telegram_message_id) if telegram_message_id is not None else None,
    )
    db.add(message)

    chat.last_message_text = normalized_text
    chat.last_message_at = datetime.utcnow()
    db.add(chat)

    db.commit()
    db.refresh(chat)
    db.refresh(message)
    return message


def save_outgoing_events(db: Session, chat: Chat, sent_items: List[Dict[str, Any]]) -> None:
    for item in sent_items or []:
        text = _normalize_text(str(item.get("text") or ""))
        if not text:
            continue
        save_outgoing_message(
            db=db,
            chat=chat,
            text=text,
            telegram_message_id=item.get("telegram_message_id"),
        )


def switch_human_mode(db: Session, chat: Chat, enabled: bool) -> Chat:
    chat.is_human_mode = enabled
    chat.status = "human" if enabled else "bot"
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def mark_chat_read(db: Session, chat: Chat) -> Chat:
    chat.unread_count = 0
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat
