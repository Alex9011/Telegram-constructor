import asyncio
import threading
import time
from typing import Any, Dict, Optional

from aiogram import Bot

from ..telegram_bot_runner import build_dispatcher, load_active_bot

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "thread": None,
    "loop": None,
    "dispatcher": None,
    "stop_event": None,
    "project_id": None,
    "bot_id": None,
    "bot_username": None,
    "last_error": None,
    "started_at": None,
}


def _set_error(message: str) -> None:
    with _lock:
        _state["last_error"] = message


def _cleanup_after_stop() -> None:
    with _lock:
        _state["thread"] = None
        _state["loop"] = None
        _state["dispatcher"] = None
        _state["stop_event"] = None
        _state["project_id"] = None
        _state["bot_id"] = None
        _state["bot_username"] = None
        _state["started_at"] = None


async def _polling_loop(project_id: int, stop_event: threading.Event) -> None:
    bot_config = load_active_bot(project_id)
    bot = Bot(token=bot_config.token)
    dispatcher = build_dispatcher(telegram_bot_id=bot_config.id)

    me = await bot.get_me()
    with _lock:
        _state["dispatcher"] = dispatcher
        _state["bot_id"] = bot_config.id
        _state["bot_username"] = me.username
        _state["last_error"] = None

    async def watch_stop_signal() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(0.3)
        dispatcher.stop_polling()

    stopper_task = asyncio.create_task(watch_stop_signal())
    try:
        await dispatcher.start_polling(bot)
    finally:
        stopper_task.cancel()
        try:
            await stopper_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()


def _worker(project_id: int, stop_event: threading.Event) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    with _lock:
        _state["loop"] = loop

    try:
        loop.run_until_complete(_polling_loop(project_id, stop_event))
    except Exception as exc:
        _set_error(str(exc))
    finally:
        try:
            loop.close()
        finally:
            _cleanup_after_stop()


def get_polling_status() -> Dict[str, Any]:
    with _lock:
        thread = _state.get("thread")
        running = bool(thread and thread.is_alive())
        return {
            "running": running,
            "project_id": _state.get("project_id"),
            "bot_id": _state.get("bot_id"),
            "bot_username": _state.get("bot_username"),
            "started_at": _state.get("started_at"),
            "last_error": _state.get("last_error"),
        }


def start_polling(project_id: int) -> tuple[bool, str]:
    with _lock:
        existing_thread = _state.get("thread")
        if existing_thread and existing_thread.is_alive():
            active_project_id = _state.get("project_id")
            if active_project_id == project_id:
                return False, "Polling вже запущено для цього проєкту"
            return False, "Вже запущено polling для іншого проєкту"

        stop_event = threading.Event()
        thread = threading.Thread(
            target=_worker,
            args=(project_id, stop_event),
            daemon=True,
            name="telegram-polling-worker",
        )

        _state["thread"] = thread
        _state["stop_event"] = stop_event
        _state["project_id"] = project_id
        _state["bot_id"] = None
        _state["bot_username"] = None
        _state["started_at"] = time.time()
        _state["last_error"] = None

        thread.start()

    return True, "Polling запускається"


def stop_polling(project_id: Optional[int] = None) -> tuple[bool, str]:
    with _lock:
        thread = _state.get("thread")
        if not thread or not thread.is_alive():
            return False, "Polling не запущено"

        active_project_id = _state.get("project_id")
        if project_id is not None and active_project_id != project_id:
            return False, "Для цього проєкту polling не запущено"

        stop_event = _state.get("stop_event")
        loop = _state.get("loop")
        dispatcher = _state.get("dispatcher")

    if stop_event:
        stop_event.set()

    if loop and dispatcher:
        try:
            loop.call_soon_threadsafe(dispatcher.stop_polling)
        except Exception:
            pass

    thread.join(timeout=8)
    if thread.is_alive():
        return False, "Зупинка запущена, зачекайте кілька секунд"

    return True, "Polling зупинено"
