from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.chat_service import (
    block_chat_user,
    clear_chat_history,
    get_chat_by_db_id,
    get_chat_session_variables,
    get_chat_with_messages,
    is_chat_blocked,
    list_chats,
    mark_chat_read,
    switch_human_mode,
    unblock_chat_user,
)
from ..services.operator_sender import send_operator_message

router = APIRouter()

VARIABLE_LABELS: Dict[str, str] = {
    "client_name": "Ім'я клієнта",
    "client_phone": "Телефон",
    "selected_service": "Обрана послуга",
    "selected_barber": "Обраний барбер",
    "booking_date": "Дата",
    "booking_time": "Час",
    "comment": "Коментар",
    "booking_request_id": "ID заявки",
}


def _build_variable_items(variables: Dict[str, Any]) -> List[Dict[str, str]]:
    preferred_order = [
        "client_name",
        "client_phone",
        "selected_service",
        "selected_barber",
        "booking_date",
        "booking_time",
        "comment",
        "booking_request_id",
    ]

    items: List[Dict[str, str]] = []
    seen = set()

    for key in preferred_order:
        if key not in variables:
            continue
        value = str(variables.get(key) or "").strip() or "—"
        items.append({"key": key, "label": VARIABLE_LABELS.get(key, key), "value": value})
        seen.add(key)

    for key in sorted(variables.keys()):
        if key in seen:
            continue
        value = str(variables.get(key) or "").strip() or "—"
        items.append({"key": key, "label": VARIABLE_LABELS.get(key, key), "value": value})

    return items


def _redirect_to_chat(chat_db_id: int, notice: Optional[str] = None, error: Optional[str] = None):
    params = []
    if notice:
        params.append(f"notice={quote_plus(notice)}")
    if error:
        params.append(f"error={quote_plus(error)}")

    suffix = ""
    if params:
        suffix = "?" + "&".join(params)

    return RedirectResponse(url=f"/admin/chats/{chat_db_id}{suffix}", status_code=303)


@router.get("/admin/chats", response_class=HTMLResponse)
def admin_chats_page(
    request: Request,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    chats = list_chats(db, project_id=project_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "admin_chats.html",
        {
            "request": request,
            "chats": chats,
            "project_id": project_id,
        },
    )


@router.get("/admin/chats/{chat_id}", response_class=HTMLResponse)
def admin_chat_detail_page(chat_id: int, request: Request, db: Session = Depends(get_db)):
    chat_data = get_chat_with_messages(db, chat_db_id=chat_id)
    if not chat_data:
        return RedirectResponse(url="/admin/chats", status_code=303)

    chat = chat_data["chat"]
    if chat.unread_count:
        mark_chat_read(db, chat)

    notice = request.query_params.get("notice")
    error = request.query_params.get("error")
    session_variables = get_chat_session_variables(db, chat)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "admin_chat_detail.html",
        {
            "request": request,
            "chat": chat,
            "messages": chat_data["messages"],
            "chat_variable_items": _build_variable_items(session_variables),
            "notice": notice,
            "error": error,
        },
    )


@router.post("/admin/chats/{chat_id}/send")
async def admin_send_message(chat_id: int, text: str = Form(...), db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)
    if is_chat_blocked(chat):
        return _redirect_to_chat(chat_id, error="Користувача заблоковано. Спочатку розблокуйте його")

    text_value = (text or "").strip()
    if not text_value:
        return _redirect_to_chat(chat_id, error="Повідомлення не може бути порожнім")

    try:
        await send_operator_message(db=db, chat=chat, text=text_value)
    except Exception as exc:
        return _redirect_to_chat(chat_id, error=f"Не вдалося відправити: {exc}")

    return _redirect_to_chat(chat_id, notice="Повідомлення відправлено")


@router.post("/admin/chats/{chat_id}/take")
def admin_take_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)
    if is_chat_blocked(chat):
        return _redirect_to_chat(chat_id, error="Спочатку розблокуйте користувача")

    switch_human_mode(db, chat, enabled=True)
    return _redirect_to_chat(chat_id, notice="Діалог передано оператору")


@router.post("/admin/chats/{chat_id}/release")
def admin_release_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)
    if is_chat_blocked(chat):
        return _redirect_to_chat(chat_id, error="Користувача заблоковано")

    switch_human_mode(db, chat, enabled=False)
    return _redirect_to_chat(chat_id, notice="Діалог повернуто боту")


@router.post("/admin/chats/{chat_id}/clear-history")
def admin_clear_chat_history(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)

    try:
        clear_chat_history(db, chat)
    except Exception as exc:
        return _redirect_to_chat(chat_id, error=f"Не вдалося очистити історію: {exc}")

    return _redirect_to_chat(chat_id, notice="Історію чату очищено")


@router.post("/admin/chats/{chat_id}/block")
def admin_block_user(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)

    block_chat_user(db, chat)
    return _redirect_to_chat(chat_id, notice="Користувача заблоковано")


@router.post("/admin/chats/{chat_id}/unblock")
def admin_unblock_user(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)

    unblock_chat_user(db, chat)
    return _redirect_to_chat(chat_id, notice="Користувача розблоковано")
