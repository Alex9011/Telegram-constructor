from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.chat_service import (
    get_chat_by_db_id,
    get_chat_with_messages,
    list_chats,
    mark_chat_read,
    switch_human_mode,
)
from ..services.operator_sender import send_operator_message

router = APIRouter()


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

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "admin_chat_detail.html",
        {
            "request": request,
            "chat": chat,
            "messages": chat_data["messages"],
            "notice": notice,
            "error": error,
        },
    )


@router.post("/admin/chats/{chat_id}/send")
async def admin_send_message(chat_id: int, text: str = Form(...), db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)

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

    switch_human_mode(db, chat, enabled=True)
    return _redirect_to_chat(chat_id, notice="Діалог передано оператору")


@router.post("/admin/chats/{chat_id}/release")
def admin_release_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = get_chat_by_db_id(db, chat_db_id=chat_id)
    if not chat:
        return RedirectResponse(url="/admin/chats", status_code=303)

    switch_human_mode(db, chat, enabled=False)
    return _redirect_to_chat(chat_id, notice="Діалог повернуто боту")
