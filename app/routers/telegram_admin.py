from urllib.parse import quote_plus
from typing import Optional

from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project
from ..services.telegram_polling_manager import get_polling_status, start_polling, stop_polling
from ..services.telegram_runtime import get_project_bot, set_project_bot_active, upsert_project_bot

router = APIRouter()


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Проєкт не знайдено")
    return project


async def resolve_bot_username(token: str) -> Optional[str]:
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return me.username
    finally:
        await bot.session.close()


def render_settings_page(
    request: Request,
    project: Project,
    bot_config,
    polling_status,
    error: Optional[str] = None,
    success: Optional[str] = None,
):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "telegram_admin.html",
        {
            "request": request,
            "project": project,
            "bot_config": bot_config,
            "polling_status": polling_status,
            "error": error,
            "success": success,
        },
    )


def redirect_with_message(project_id: int, key: str, message: str) -> RedirectResponse:
    encoded_message = quote_plus(message)
    return RedirectResponse(
        url=f"/projects/{project_id}/telegram?{key}={encoded_message}",
        status_code=303,
    )


@router.get("/projects/{project_id}/telegram", response_class=HTMLResponse)
def telegram_settings_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    bot_config = get_project_bot(db, project_id)
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    if request.query_params.get("saved") == "1" and not success:
        success = "Налаштування збережено"

    polling_status = get_polling_status()
    return render_settings_page(
        request=request,
        project=project,
        bot_config=bot_config,
        polling_status=polling_status,
        error=error,
        success=success,
    )


@router.post("/projects/{project_id}/telegram/save", response_class=HTMLResponse)
async def telegram_settings_save(
    project_id: int,
    request: Request,
    token: str = Form(...),
    is_active: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        project = get_project_or_404(db, project_id)
    except ValueError:
        return RedirectResponse(url="/", status_code=303)

    token_value = (token or "").strip()
    if not token_value:
        return render_settings_page(
            request=request,
            project=project,
            bot_config=get_project_bot(db, project_id),
            polling_status=get_polling_status(),
            error="Токен не може бути порожнім",
        )

    try:
        username = await resolve_bot_username(token_value)
    except Exception:
        return render_settings_page(
            request=request,
            project=project,
            bot_config=get_project_bot(db, project_id),
            polling_status=get_polling_status(),
            error="Не вдалося перевірити токен через Telegram API",
        )

    upsert_project_bot(
        db=db,
        project_id=project_id,
        token=token_value,
        is_active=is_active == "on",
        bot_username=username,
    )
    return RedirectResponse(url=f"/projects/{project_id}/telegram?saved=1", status_code=303)


@router.post("/projects/{project_id}/telegram/toggle")
def telegram_settings_toggle(
    project_id: int,
    enabled: int = Form(...),
    db: Session = Depends(get_db),
):
    bot = set_project_bot_active(db, project_id=project_id, is_active=bool(enabled))
    if not bot:
        return redirect_with_message(project_id, "error", "Спочатку збережіть токен")

    if not bool(enabled):
        stop_polling(project_id=project_id)

    return RedirectResponse(url=f"/projects/{project_id}/telegram?saved=1", status_code=303)


@router.post("/projects/{project_id}/telegram/polling/start")
def telegram_polling_start(project_id: int, db: Session = Depends(get_db)):
    bot = get_project_bot(db, project_id)
    if not bot:
        return redirect_with_message(project_id, "error", "Збережіть токен перед запуском polling")

    if not bot.is_active:
        return redirect_with_message(project_id, "error", "Увімкніть бота перед запуском polling")

    ok, message = start_polling(project_id=project_id)
    message_type = "success" if ok else "error"
    return redirect_with_message(project_id, message_type, message)


@router.post("/projects/{project_id}/telegram/polling/stop")
def telegram_polling_stop(project_id: int):
    ok, message = stop_polling(project_id=project_id)
    message_type = "success" if ok else "error"
    return redirect_with_message(project_id, message_type, message)
