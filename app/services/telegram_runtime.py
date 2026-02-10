import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models import Block, BotSession, Project, TelegramBot
from .flow_engine import (
    advance_with_action,
    build_block_map,
    find_start_block_id,
    run_automatic_steps,
    validate_blocks,
)


def parse_block_data(data_json: str) -> Dict[str, Any]:
    try:
        value = json.loads(data_json or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_project_bot(db: Session, project_id: int) -> Optional[TelegramBot]:
    return db.query(TelegramBot).filter(TelegramBot.project_id == project_id).first()


def upsert_project_bot(
    db: Session,
    project_id: int,
    token: str,
    is_active: bool,
    bot_username: Optional[str],
) -> TelegramBot:
    bot = get_project_bot(db, project_id)
    if not bot:
        bot = TelegramBot(
            project_id=project_id,
            token=token,
            is_active=is_active,
            bot_username=bot_username,
        )
    else:
        bot.token = token
        bot.is_active = is_active
        bot.bot_username = bot_username

    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def set_project_bot_active(db: Session, project_id: int, is_active: bool) -> Optional[TelegramBot]:
    bot = get_project_bot(db, project_id)
    if not bot:
        return None

    bot.is_active = is_active
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def get_active_telegram_bot(db: Session, project_id: Optional[int] = None) -> Optional[TelegramBot]:
    query = db.query(TelegramBot).filter(TelegramBot.is_active.is_(True))
    if project_id is not None:
        query = query.filter(TelegramBot.project_id == project_id)
    return query.order_by(TelegramBot.id.asc()).first()


def _get_telegram_bot_or_error(db: Session, telegram_bot_id: int) -> TelegramBot:
    bot = db.query(TelegramBot).filter(TelegramBot.id == telegram_bot_id).first()
    if not bot:
        raise ValueError("Telegram-бот не знайдено")
    if not bot.is_active:
        raise ValueError("Telegram-бот вимкнено в налаштуваннях проєкту")
    return bot


def _load_project_blocks(project: Project) -> List[Dict[str, Any]]:
    ordered_blocks = sorted(project.blocks, key=lambda item: item.id)
    return [
        {
            "uid": block.uid,
            "type": block.block_type,
            "data": parse_block_data(block.data_json),
        }
        for block in ordered_blocks
    ]


def _load_runtime_context(
    db: Session,
    telegram_bot_id: int,
) -> Tuple[TelegramBot, List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    bot = _get_telegram_bot_or_error(db, telegram_bot_id)
    project = db.query(Project).filter(Project.id == bot.project_id).first()
    if not project:
        raise ValueError("Проєкт для Telegram-бота не знайдено")

    blocks = _load_project_blocks(project)
    errors = validate_blocks(blocks)
    if errors:
        raise ValueError("Схема невалідна: " + errors[0])

    block_map = build_block_map(blocks)
    return bot, blocks, block_map


def _get_or_create_session(
    db: Session,
    telegram_bot_id: int,
    telegram_user_id: int,
    chat_id: int,
) -> BotSession:
    user_id_str = str(telegram_user_id)
    chat_id_str = str(chat_id)

    session = (
        db.query(BotSession)
        .filter(
            BotSession.telegram_bot_id == telegram_bot_id,
            BotSession.telegram_user_id == user_id_str,
            BotSession.chat_id == chat_id_str,
        )
        .first()
    )
    if session:
        return session

    session = BotSession(
        telegram_bot_id=telegram_bot_id,
        telegram_user_id=user_id_str,
        chat_id=chat_id_str,
        current_block_id=None,
        waiting=None,
        variables_json="{}",
    )
    db.add(session)
    db.flush()
    return session


def _session_to_state(session: BotSession) -> Dict[str, Any]:
    try:
        variables = json.loads(session.variables_json or "{}")
        if not isinstance(variables, dict):
            variables = {}
    except json.JSONDecodeError:
        variables = {}

    return {
        "current_block_id": session.current_block_id,
        "waiting": session.waiting,
        "variables": variables,
    }


def _save_state(db: Session, session: BotSession, state: Dict[str, Any]) -> None:
    session.current_block_id = state.get("current_block_id")
    session.waiting = state.get("waiting")
    session.variables_json = json.dumps(state.get("variables", {}), ensure_ascii=False)
    db.add(session)
    db.commit()


def start_for_user(
    db: Session,
    telegram_bot_id: int,
    telegram_user_id: int,
    chat_id: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    _, blocks, block_map = _load_runtime_context(db, telegram_bot_id)

    start_block_id = find_start_block_id(blocks)
    if not start_block_id:
        raise ValueError("У схемі не знайдено блок start")

    session = _get_or_create_session(db, telegram_bot_id, telegram_user_id, chat_id)
    state = {
        "current_block_id": start_block_id,
        "waiting": None,
        "variables": {},
    }

    events, finished = run_automatic_steps(blocks, state, block_map=block_map)
    _save_state(db, session, state)
    return events, finished


def continue_with_text(
    db: Session,
    telegram_bot_id: int,
    telegram_user_id: int,
    chat_id: int,
    text: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    _, blocks, block_map = _load_runtime_context(db, telegram_bot_id)
    session = _get_or_create_session(db, telegram_bot_id, telegram_user_id, chat_id)
    state = _session_to_state(session)

    if not state.get("current_block_id") and not state.get("waiting"):
        events = [
            {
                "type": "message",
                "text": "Сценарій завершено. Надішліть /start, щоб почати знову.",
            }
        ]
        _save_state(db, session, state)
        return events, True

    waiting = state.get("waiting")
    if waiting == "buttons":
        events = [
            {
                "type": "message",
                "text": "Оберіть кнопку під попереднім повідомленням.",
            }
        ]
        finished = False
    elif waiting == "input":
        events, finished = advance_with_action(
            blocks,
            state,
            action="input",
            input_text=text,
            block_map=block_map,
        )
    else:
        events, finished = run_automatic_steps(blocks, state, block_map=block_map)

    _save_state(db, session, state)
    return events, finished


def continue_with_button(
    db: Session,
    telegram_bot_id: int,
    telegram_user_id: int,
    chat_id: int,
    button_index: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    _, blocks, block_map = _load_runtime_context(db, telegram_bot_id)
    session = _get_or_create_session(db, telegram_bot_id, telegram_user_id, chat_id)
    state = _session_to_state(session)

    if not state.get("current_block_id") and not state.get("waiting"):
        events = [
            {
                "type": "message",
                "text": "Сценарій завершено. Надішліть /start, щоб почати знову.",
            }
        ]
        _save_state(db, session, state)
        return events, True

    if state.get("waiting") != "buttons":
        events = [{"type": "message", "text": "Зараз не очікується натискання кнопки."}]
        _save_state(db, session, state)
        return events, False

    events, finished = advance_with_action(
        blocks,
        state,
        action="choose",
        button_index=button_index,
        block_map=block_map,
    )

    _save_state(db, session, state)
    return events, finished
