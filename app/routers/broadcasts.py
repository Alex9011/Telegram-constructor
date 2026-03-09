from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BroadcastCampaign, Project
from ..services.broadcast_campaigns import (
    VALID_SCHEDULE_TYPES,
    as_form_defaults,
    create_campaign,
    delete_campaign,
    get_campaign_by_id,
    list_campaigns_for_project,
    update_campaign,
)

router = APIRouter()

DAY_NAMES = {
    0: "Понеділок",
    1: "Вівторок",
    2: "Середа",
    3: "Четвер",
    4: "П'ятниця",
    5: "Субота",
    6: "Неділя",
}

SCHEDULE_OPTIONS = [
    {"value": "daily", "label": "Щодня"},
    {"value": "weekly", "label": "Щотижня"},
    {"value": "monthly", "label": "Щомісяця"},
    {"value": "interval", "label": "Кожні N днів"},
]


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Проєкт не знайдено")
    return project


def get_campaign_or_404(db: Session, campaign_id: int) -> BroadcastCampaign:
    campaign = get_campaign_by_id(db, campaign_id)
    if not campaign:
        raise ValueError("Розсилку не знайдено")
    return campaign


def _redirect_to_project_broadcasts(project_id: int, notice: Optional[str] = None, error: Optional[str] = None):
    params = []
    if notice:
        params.append(f"notice={quote_plus(notice)}")
    if error:
        params.append(f"error={quote_plus(error)}")

    suffix = ""
    if params:
        suffix = "?" + "&".join(params)

    return RedirectResponse(url=f"/projects/{project_id}/broadcasts{suffix}", status_code=303)


def _parse_int(raw: Any, field_name: str) -> Tuple[Optional[int], Optional[str]]:
    text = str(raw or "").strip()
    if not text:
        return None, None
    try:
        return int(text), None
    except ValueError:
        return None, f"Поле {field_name} має бути цілим числом"


def _build_form_values(form_data: Dict[str, Any]) -> Dict[str, Any]:
    defaults = as_form_defaults()
    defaults.update(
        {
            "title": str(form_data.get("title") or "").strip(),
            "message_text": str(form_data.get("message_text") or "").strip(),
            "schedule_type": str(form_data.get("schedule_type") or "daily").strip().lower() or "daily",
            "day_of_week": str(form_data.get("day_of_week") or "").strip(),
            "day_of_month": str(form_data.get("day_of_month") or "").strip(),
            "hour": str(form_data.get("hour") or "").strip(),
            "minute": str(form_data.get("minute") or "").strip(),
            "interval_days": str(form_data.get("interval_days") or "").strip(),
            "timezone": str(form_data.get("timezone") or "").strip() or "Europe/Kiev",
            "is_active": bool(form_data.get("is_active")),
        }
    )
    return defaults


def _parse_campaign_form(form_values: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    title = str(form_values.get("title") or "").strip()
    if not title:
        return None, "Вкажіть назву розсилки"

    message_text = str(form_values.get("message_text") or "").strip()
    if not message_text:
        return None, "Текст повідомлення не може бути порожнім"

    schedule_type = str(form_values.get("schedule_type") or "daily").strip().lower()
    if schedule_type not in VALID_SCHEDULE_TYPES:
        return None, "Некоректний тип розкладу"

    hour, error = _parse_int(form_values.get("hour"), "hour")
    if error:
        return None, error
    minute, error = _parse_int(form_values.get("minute"), "minute")
    if error:
        return None, error

    if hour is None or hour < 0 or hour > 23:
        return None, "Година має бути в діапазоні 0-23"
    if minute is None or minute < 0 or minute > 59:
        return None, "Хвилини мають бути в діапазоні 0-59"

    day_of_week, error = _parse_int(form_values.get("day_of_week"), "day_of_week")
    if error:
        return None, error
    day_of_month, error = _parse_int(form_values.get("day_of_month"), "day_of_month")
    if error:
        return None, error
    interval_days, error = _parse_int(form_values.get("interval_days"), "interval_days")
    if error:
        return None, error

    if schedule_type == "weekly":
        if day_of_week is None or day_of_week < 0 or day_of_week > 6:
            return None, "Для weekly оберіть день тижня (0-6)"
    else:
        day_of_week = None

    if schedule_type == "monthly":
        if day_of_month is None or day_of_month < 1 or day_of_month > 31:
            return None, "Для monthly вкажіть день місяця (1-31)"
    else:
        day_of_month = None

    if schedule_type == "interval":
        if interval_days is None or interval_days < 1:
            return None, "Для interval вкажіть interval_days >= 1"
    else:
        interval_days = None

    timezone = str(form_values.get("timezone") or "").strip() or "Europe/Kiev"

    return (
        {
            "title": title,
            "message_text": message_text,
            "schedule_type": schedule_type,
            "day_of_week": day_of_week,
            "day_of_month": day_of_month,
            "hour": hour,
            "minute": minute,
            "interval_days": interval_days,
            "timezone": timezone,
            "is_active": bool(form_values.get("is_active")),
        },
        None,
    )


def _human_schedule(campaign: BroadcastCampaign) -> str:
    time_text = f"{int(campaign.hour or 0):02d}:{int(campaign.minute or 0):02d}"
    tz_text = (campaign.timezone or "UTC").strip() or "UTC"

    schedule_type = (campaign.schedule_type or "daily").strip().lower()
    if schedule_type == "daily":
        return f"Щодня о {time_text} ({tz_text})"
    if schedule_type == "weekly":
        day_name = DAY_NAMES.get(int(campaign.day_of_week or -1), "день не задано")
        return f"Щотижня: {day_name}, {time_text} ({tz_text})"
    if schedule_type == "monthly":
        return f"Щомісяця: {campaign.day_of_month or '-'} числа, {time_text} ({tz_text})"
    if schedule_type == "interval":
        return f"Кожні {campaign.interval_days or '-'} днів о {time_text} ({tz_text})"
    return f"Невідомий тип ({schedule_type})"


def _render_form(
    request: Request,
    project: Project,
    action_url: str,
    form_values: Dict[str, Any],
    title: str,
    error: Optional[str] = None,
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "broadcast_form.html",
        {
            "request": request,
            "project": project,
            "action_url": action_url,
            "page_title": title,
            "form_values": form_values,
            "schedule_options": SCHEDULE_OPTIONS,
            "day_names": DAY_NAMES,
            "error": error,
        },
    )


@router.get("/projects/{project_id}/broadcasts", response_class=HTMLResponse)
def broadcasts_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    campaigns = list_campaigns_for_project(db, project_id=project_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "broadcasts.html",
        {
            "request": request,
            "project": project,
            "campaigns": campaigns,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
            "schedule_text": {campaign.id: _human_schedule(campaign) for campaign in campaigns},
        },
    )


@router.get("/projects/{project_id}/broadcasts/new", response_class=HTMLResponse)
def broadcast_new_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    return _render_form(
        request=request,
        project=project,
        action_url=f"/projects/{project_id}/broadcasts",
        form_values=as_form_defaults(),
        title="Нова розсилка",
    )


@router.post("/projects/{project_id}/broadcasts", response_class=HTMLResponse)
async def broadcast_create(project_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    form_data = dict(await request.form())
    form_values = _build_form_values(form_data)
    payload, error = _parse_campaign_form(form_values)
    if error:
        return _render_form(
            request=request,
            project=project,
            action_url=f"/projects/{project_id}/broadcasts",
            form_values=form_values,
            title="Нова розсилка",
            error=error,
        )

    create_campaign(db=db, project_id=project_id, **payload)
    return _redirect_to_project_broadcasts(project_id, notice="Розсилку створено")


@router.get("/broadcasts/{broadcast_id}/edit", response_class=HTMLResponse)
def broadcast_edit_page(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign_or_404(db, broadcast_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    project = campaign.project
    return _render_form(
        request=request,
        project=project,
        action_url=f"/broadcasts/{broadcast_id}/edit",
        form_values=as_form_defaults(campaign),
        title="Редагування розсилки",
    )


@router.post("/broadcasts/{broadcast_id}/edit", response_class=HTMLResponse)
async def broadcast_edit(broadcast_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign_or_404(db, broadcast_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    project = campaign.project
    form_data = dict(await request.form())
    form_values = _build_form_values(form_data)
    payload, error = _parse_campaign_form(form_values)
    if error:
        return _render_form(
            request=request,
            project=project,
            action_url=f"/broadcasts/{broadcast_id}/edit",
            form_values=form_values,
            title="Редагування розсилки",
            error=error,
        )

    update_campaign(db=db, campaign=campaign, **payload)
    return _redirect_to_project_broadcasts(project.id, notice="Розсилку оновлено")


@router.post("/broadcasts/{broadcast_id}/toggle")
def broadcast_toggle(broadcast_id: int, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign_or_404(db, broadcast_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    campaign.is_active = not bool(campaign.is_active)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    state_label = "увімкнено" if campaign.is_active else "вимкнено"
    return _redirect_to_project_broadcasts(campaign.project_id, notice=f"Розсилку {state_label}")


@router.post("/broadcasts/{broadcast_id}/delete")
def broadcast_delete(broadcast_id: int, db: Session = Depends(get_db)):
    try:
        campaign = get_campaign_or_404(db, broadcast_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    project_id = campaign.project_id
    delete_campaign(db, campaign)
    return _redirect_to_project_broadcasts(project_id, notice="Розсилку видалено")
