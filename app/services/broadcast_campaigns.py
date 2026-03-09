from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from ..models import BroadcastCampaign

VALID_SCHEDULE_TYPES = {"daily", "weekly", "monthly", "interval"}


def _safe_timezone(name: Optional[str]) -> ZoneInfo:
    tz_name = (name or "").strip() or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _as_utc_aware(now_utc: datetime):
    if now_utc.tzinfo is not None:
        return now_utc.astimezone(ZoneInfo("UTC"))
    return now_utc.replace(tzinfo=ZoneInfo("UTC"))


def create_campaign(
    db: Session,
    project_id: int,
    title: str,
    message_text: str,
    schedule_type: str,
    day_of_week: Optional[int],
    day_of_month: Optional[int],
    hour: int,
    minute: int,
    interval_days: Optional[int],
    timezone: str,
    is_active: bool,
) -> BroadcastCampaign:
    campaign = BroadcastCampaign(
        project_id=project_id,
        title=title,
        message_text=message_text,
        schedule_type=schedule_type,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        hour=hour,
        minute=minute,
        interval_days=interval_days,
        timezone=timezone,
        is_active=is_active,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def update_campaign(
    db: Session,
    campaign: BroadcastCampaign,
    title: str,
    message_text: str,
    schedule_type: str,
    day_of_week: Optional[int],
    day_of_month: Optional[int],
    hour: int,
    minute: int,
    interval_days: Optional[int],
    timezone: str,
    is_active: bool,
) -> BroadcastCampaign:
    campaign.title = title
    campaign.message_text = message_text
    campaign.schedule_type = schedule_type
    campaign.day_of_week = day_of_week
    campaign.day_of_month = day_of_month
    campaign.hour = hour
    campaign.minute = minute
    campaign.interval_days = interval_days
    campaign.timezone = timezone
    campaign.is_active = is_active

    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def delete_campaign(db: Session, campaign: BroadcastCampaign) -> None:
    db.delete(campaign)
    db.commit()


def list_campaigns_for_project(db: Session, project_id: int) -> List[BroadcastCampaign]:
    return (
        db.query(BroadcastCampaign)
        .filter(BroadcastCampaign.project_id == project_id)
        .order_by(BroadcastCampaign.created_at.desc(), BroadcastCampaign.id.desc())
        .all()
    )


def get_campaign_by_id(db: Session, campaign_id: int) -> Optional[BroadcastCampaign]:
    return (
        db.query(BroadcastCampaign)
        .options(joinedload(BroadcastCampaign.project))
        .filter(BroadcastCampaign.id == campaign_id)
        .first()
    )


def should_run_campaign(campaign: BroadcastCampaign, now_utc: Optional[datetime] = None) -> bool:
    if not campaign.is_active:
        return False

    now_utc = now_utc or datetime.utcnow()
    current_slot_utc = now_utc.replace(second=0, microsecond=0)

    if campaign.last_run_at:
        last_slot = campaign.last_run_at.replace(second=0, microsecond=0)
        if last_slot >= current_slot_utc:
            return False

    tz = _safe_timezone(campaign.timezone)
    local_now = _as_utc_aware(now_utc).astimezone(tz)

    if local_now.hour != int(campaign.hour or 0) or local_now.minute != int(campaign.minute or 0):
        return False

    schedule = (campaign.schedule_type or "daily").strip().lower()
    if schedule == "daily":
        return True

    if schedule == "weekly":
        if campaign.day_of_week is None:
            return False
        return int(campaign.day_of_week) == local_now.weekday()

    if schedule == "monthly":
        if campaign.day_of_month is None:
            return False
        return int(campaign.day_of_month) == local_now.day

    if schedule == "interval":
        days = int(campaign.interval_days or 0)
        if days <= 0:
            return False
        if not campaign.last_run_at:
            return True
        return (current_slot_utc.date() - campaign.last_run_at.date()).days >= days

    return False


def get_due_campaigns(db: Session, now_utc: Optional[datetime] = None) -> List[BroadcastCampaign]:
    now_utc = now_utc or datetime.utcnow()
    campaigns = db.query(BroadcastCampaign).filter(BroadcastCampaign.is_active.is_(True)).all()
    return [campaign for campaign in campaigns if should_run_campaign(campaign, now_utc=now_utc)]


def mark_campaign_sent(db: Session, campaign: BroadcastCampaign, now_utc: Optional[datetime] = None) -> BroadcastCampaign:
    campaign.last_run_at = (now_utc or datetime.utcnow()).replace(second=0, microsecond=0)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def as_form_defaults(campaign: Optional[BroadcastCampaign] = None) -> Dict[str, Any]:
    if not campaign:
        return {
            "title": "",
            "message_text": "",
            "schedule_type": "daily",
            "day_of_week": "",
            "day_of_month": "",
            "hour": 10,
            "minute": 0,
            "interval_days": "",
            "timezone": "Europe/Kiev",
            "is_active": True,
        }

    return {
        "title": campaign.title,
        "message_text": campaign.message_text,
        "schedule_type": campaign.schedule_type,
        "day_of_week": "" if campaign.day_of_week is None else str(campaign.day_of_week),
        "day_of_month": "" if campaign.day_of_month is None else str(campaign.day_of_month),
        "hour": campaign.hour,
        "minute": campaign.minute,
        "interval_days": "" if campaign.interval_days is None else str(campaign.interval_days),
        "timezone": campaign.timezone or "Europe/Kiev",
        "is_active": bool(campaign.is_active),
    }
