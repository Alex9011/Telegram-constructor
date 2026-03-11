import asyncio
import threading
import time
from typing import Any, Dict, Optional

from aiogram import Bot

from ..telegram_bot_runner import build_dispatcher, load_active_bot

STOP_JOIN_TIMEOUT_SECONDS = 20
STOP_GRACEFUL_STOP_SECONDS = 6

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "thread": None,
    "loop": None,
    "dispatcher": None,
    "bot": None,
    "stop_event": None,
    "project_id": None,
    "bot_id": None,
    "bot_username": None,
    "last_error": None,
    "started_at": None,
    "stop_requested": False,
    "status": "stopped",
    "status_message": "polling already stopped",
    "status_updated_at": None,
}


def _set_error(message: str) -> None:
    with _lock:
        _state["last_error"] = message


def _set_status(status: str, message: str) -> None:
    with _lock:
        _state["status"] = status
        _state["status_message"] = message
        _state["status_updated_at"] = time.time()


def _set_status_unlocked(status: str, message: str) -> None:
    _state["status"] = status
    _state["status_message"] = message
    _state["status_updated_at"] = time.time()


def _cleanup_after_stop(status: str = "stopped", message: str = "polling stopped; polling restart available") -> None:
    with _lock:
        _state["thread"] = None
        _state["loop"] = None
        _state["dispatcher"] = None
        _state["bot"] = None
        _state["stop_event"] = None
        _state["project_id"] = None
        _state["bot_id"] = None
        _state["bot_username"] = None
        _state["started_at"] = None
        _state["stop_requested"] = False
        _set_status_unlocked(status, message)


def _request_dispatcher_stop(dispatcher: Any) -> None:
    if dispatcher is None:
        return
    try:
        dispatcher.stop_polling()
    except Exception:
        # stop_polling can fail when dispatcher is not yet in polling state.
        pass


def _shutdown_loop(loop: asyncio.AbstractEventLoop) -> None:
    try:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    except Exception:
        pending = []

    for task in pending:
        task.cancel()

    if pending:
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass

    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    except Exception:
        pass


def _force_cancel_loop_tasks() -> None:
    try:
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is current_task or task.done():
                continue
            task.cancel()
    except Exception:
        pass


async def _wait_for_stop_event(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(0.1)


async def _polling_loop(project_id: int, stop_event: threading.Event) -> None:
    bot: Optional[Bot] = None
    stop_wait_task: Optional[asyncio.Task] = None
    polling_task: Optional[asyncio.Task] = None
    dispatcher = None

    try:
        bot_config = load_active_bot(project_id)
        bot = Bot(token=bot_config.token)
        dispatcher = build_dispatcher(telegram_bot_id=bot_config.id)

        with _lock:
            _state["dispatcher"] = dispatcher
            _state["bot"] = bot
            _state["bot_id"] = bot_config.id
            _state["bot_username"] = getattr(bot_config, "bot_username", None)
            _state["last_error"] = None
            _set_status_unlocked("running", "polling started")

        if stop_event.is_set():
            return

        polling_task = asyncio.create_task(
            dispatcher.start_polling(bot, polling_timeout=1, handle_signals=False),
            name="telegram-polling-main",
        )
        stop_wait_task = asyncio.create_task(_wait_for_stop_event(stop_event), name="telegram-polling-stop-wait")

        done, _pending = await asyncio.wait(
            {polling_task, stop_wait_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_wait_task in done and polling_task and not polling_task.done():
            _request_dispatcher_stop(dispatcher)
            try:
                await asyncio.wait_for(polling_task, timeout=STOP_GRACEFUL_STOP_SECONDS)
            except asyncio.TimeoutError:
                polling_task.cancel()
                await asyncio.gather(polling_task, return_exceptions=True)

        if polling_task and polling_task.done():
            await polling_task
    finally:
        if stop_wait_task:
            stop_wait_task.cancel()
            try:
                await stop_wait_task
            except asyncio.CancelledError:
                pass

        if polling_task:
            polling_task.cancel()
            await asyncio.gather(polling_task, return_exceptions=True)

        if bot is not None:
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
        _set_status("error", "polling stopped")
    finally:
        try:
            _shutdown_loop(loop)
            loop.close()
        finally:
            asyncio.set_event_loop(None)
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
            "stop_requested": _state.get("stop_requested"),
            "status": _state.get("status"),
            "status_message": _state.get("status_message"),
            "status_updated_at": _state.get("status_updated_at"),
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
        _state["stop_requested"] = False
        _set_status_unlocked("starting", "polling started")

        thread.start()

    return True, "polling started"


def stop_polling(project_id: Optional[int] = None) -> tuple[bool, str]:
    with _lock:
        thread = _state.get("thread")
        if not thread or not thread.is_alive():
            _set_status_unlocked("stopped", "polling already stopped; polling restart available")
            return True, "polling already stopped; polling restart available"

        active_project_id = _state.get("project_id")
        if project_id is not None and active_project_id != project_id:
            return False, "Для цього проєкту polling не запущено"

        stop_event = _state.get("stop_event")
        loop = _state.get("loop")
        dispatcher = _state.get("dispatcher")
        bot = _state.get("bot")
        if not _state.get("stop_requested"):
            _state["stop_requested"] = True
            _set_status_unlocked("stopping", "stop requested")

    if stop_event:
        stop_event.set()

    if loop and dispatcher:
        try:
            loop.call_soon_threadsafe(_request_dispatcher_stop, dispatcher)
        except Exception:
            pass

    if loop and bot:
        try:
            loop.call_soon_threadsafe(asyncio.create_task, bot.session.close())
        except Exception:
            pass

    thread.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)
    if thread.is_alive():
        if loop:
            try:
                loop.call_soon_threadsafe(_force_cancel_loop_tasks)
            except Exception:
                pass
        thread.join(timeout=5)

    if thread.is_alive():
        _set_status("stop-timeout", "stop timeout")
        return False, "stop timeout"

    _set_status("stopped", "polling stopped; polling restart available")
    return True, "polling stopped; polling restart available"
