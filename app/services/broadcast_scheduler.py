from datetime import datetime
from importlib import import_module
from threading import Lock
from typing import Any, Dict, Optional

from ..database import SessionLocal
from .broadcast_campaigns import get_due_campaigns, mark_campaign_sent
from .broadcast_sender import send_campaign

_lock = Lock()
_scheduler: Optional[Any] = None
_last_error: Optional[str] = None
_last_tick_at: Optional[datetime] = None


def _create_scheduler() -> Any:
    module = import_module("apscheduler.schedulers.background")
    return module.BackgroundScheduler()


def _set_error(message: str) -> None:
    global _last_error
    _last_error = message


def _run_broadcast_cycle() -> None:
    global _last_tick_at
    _last_tick_at = datetime.utcnow()

    db = SessionLocal()
    try:
        due_campaigns = get_due_campaigns(db)
        for campaign in due_campaigns:
            try:
                stats = send_campaign(db, campaign)
                mark_campaign_sent(db, campaign)
                print(
                    "[broadcast] campaign_id=",
                    campaign.id,
                    "sent=",
                    stats.get("sent", 0),
                    "errors=",
                    stats.get("errors", 0),
                )
            except Exception as exc:
                _set_error(f"campaign_id={campaign.id}: {exc}")
    except Exception as exc:
        _set_error(str(exc))
    finally:
        db.close()


def start_broadcast_scheduler() -> None:
    global _scheduler

    with _lock:
        if _scheduler and _scheduler.running:
            return

        scheduler = _create_scheduler()
        scheduler.add_job(
            _run_broadcast_cycle,
            trigger="interval",
            minutes=1,
            id="broadcast-cycle",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        scheduler.start()
        _scheduler = scheduler


def stop_broadcast_scheduler() -> None:
    global _scheduler

    with _lock:
        if not _scheduler:
            return
        try:
            _scheduler.shutdown(wait=False)
        finally:
            _scheduler = None


def get_broadcast_scheduler_status() -> Dict[str, Any]:
    with _lock:
        running = bool(_scheduler and _scheduler.running)

    return {
        "running": running,
        "last_error": _last_error,
        "last_tick_at": _last_tick_at,
    }
