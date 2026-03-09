import json
from typing import Any, Dict, List
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Block, Project
from ..schemas import BlockPayload, FlowSaveRequest
from ..services.flow_engine import validate_blocks
from ..services.project_templates import create_barbershop_template, ensure_barbershop_demo_project

router = APIRouter()


def _redirect_to_index_with_message(key: str, message: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?{key}={quote_plus(message)}", status_code=303)


def _normalize_import_blocks(raw_blocks: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("У JSON має бути непорожній список blocks")

    blocks: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_blocks, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Блок #{index}: некоректний формат")

        uid = str(item.get("uid") or "").strip()
        block_type = str(item.get("type") or "").strip()
        data = item.get("data") if item.get("data") is not None else {}

        if not uid:
            raise ValueError(f"Блок #{index}: відсутній uid")
        if not block_type:
            raise ValueError(f"Блок {uid}: відсутній type")
        if not isinstance(data, dict):
            raise ValueError(f"Блок {uid}: поле data має бути об'єктом")

        blocks.append(
            {
                "uid": uid,
                "type": block_type,
                "data": data,
            }
        )

    errors = validate_blocks(blocks)
    if errors:
        raise ValueError("; ".join(errors))

    return blocks


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проєкт не знайдено")
    return project


def parse_block_data(data_json: str) -> Dict[str, Any]:
    try:
        value = json.loads(data_json or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def block_to_dict(block: Block) -> Dict[str, Any]:
    return {
        "uid": block.uid,
        "type": block.block_type,
        "data": parse_block_data(block.data_json),
    }


def project_to_schema(project: Project) -> Dict[str, Any]:
    blocks = sorted(project.blocks, key=lambda item: item.id)
    return {
        "project_id": project.id,
        "name": project.name,
        "blocks": [block_to_dict(block) for block in blocks],
    }


def persist_schema(db: Session, project: Project, blocks: List[Dict[str, Any]]) -> Project:
    project.blocks.clear()
    db.flush()

    for block in blocks:
        db.add(
            Block(
                project_id=project.id,
                uid=block["uid"],
                block_type=block["type"],
                data_json=json.dumps(block.get("data", {}), ensure_ascii=False),
            )
        )

    scheme = {
        "project_id": project.id,
        "name": project.name,
        "blocks": blocks,
    }
    project.flow_json = json.dumps(scheme, ensure_ascii=False)

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def payload_to_block(payload: BlockPayload) -> Dict[str, Any]:
    block_id = payload.uid.strip()
    if not block_id:
        raise HTTPException(status_code=400, detail="ID блоку не може бути порожнім")

    return {
        "uid": block_id,
        "type": payload.block_type,
        "data": payload.data or {},
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    ensure_barbershop_demo_project(db)
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    notice = request.query_params.get("notice")
    error = request.query_params.get("error")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "projects": projects,
            "notice": notice,
            "error": error,
        },
    )


@router.post("/projects/create")
def create_project(name: str = Form(...), db: Session = Depends(get_db)):
    project_name = (name or "").strip() or "Новий бот"
    project = Project(name=project_name)
    db.add(project)
    db.flush()

    start_block = {
        "uid": "start",
        "type": "start",
        "data": {"next_block_id": None},
    }
    db.add(
        Block(
            project_id=project.id,
            uid=start_block["uid"],
            block_type=start_block["type"],
            data_json=json.dumps(start_block["data"], ensure_ascii=False),
        )
    )

    project.flow_json = json.dumps(
        {
            "project_id": project.id,
            "name": project.name,
            "blocks": [start_block],
        },
        ensure_ascii=False,
    )

    db.add(project)
    db.commit()

    return RedirectResponse(url=f"/projects/{project.id}/editor", status_code=303)


@router.post("/projects/create-barbershop-demo")
def create_barbershop_demo_project(db: Session = Depends(get_db)):
    try:
        project = create_barbershop_template(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url=f"/projects/{project.id}/editor", status_code=303)


@router.post("/projects/import-json")
async def import_project_json(
    file: UploadFile = File(...),
    name: str = Form(""),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").strip()
    if not filename:
        return _redirect_to_index_with_message("error", "Оберіть JSON-файл для імпорту")
    if not filename.lower().endswith(".json"):
        return _redirect_to_index_with_message("error", "Підтримуються лише файли .json")

    raw_bytes = await file.read()
    if not raw_bytes:
        return _redirect_to_index_with_message("error", "Файл порожній")

    try:
        payload_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _redirect_to_index_with_message("error", "Файл має бути в UTF-8")

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _redirect_to_index_with_message("error", "Некоректний JSON-файл")

    if not isinstance(payload, dict):
        return _redirect_to_index_with_message("error", "Корінь JSON має бути об'єктом")

    try:
        blocks = _normalize_import_blocks(payload.get("blocks"))
    except ValueError as exc:
        return _redirect_to_index_with_message("error", f"Помилка схеми: {exc}")

    imported_name = str(payload.get("name") or "").strip()
    project_name = (name or "").strip() or imported_name or "Імпортований бот"

    project = Project(name=project_name)
    db.add(project)
    db.flush()
    persist_schema(db, project, blocks)

    return RedirectResponse(url=f"/projects/{project.id}/editor", status_code=303)


@router.post("/projects/{project_id}/delete")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    db.delete(project)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.get("/projects/{project_id}/editor", response_class=HTMLResponse)
def editor_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "project_editor.html",
        {
            "request": request,
            "project": project,
        },
    )


@router.get("/projects/{project_id}/export")
def export_project(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    scheme = project_to_schema(project)

    return JSONResponse(
        content=scheme,
        headers={
            "Content-Disposition": f"attachment; filename=project_{project_id}_schema.json"
        },
    )


@router.get("/api/projects/{project_id}/scheme")
def get_scheme_api(project_id: int, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    return project_to_schema(project)


@router.put("/api/projects/{project_id}/scheme")
def update_scheme_api(
    project_id: int,
    payload: FlowSaveRequest,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    blocks = [payload_to_block(block) for block in payload.blocks]
    errors = validate_blocks(blocks)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    updated_project = persist_schema(db, project, blocks)
    return {
        "ok": True,
        "scheme": project_to_schema(updated_project),
    }


@router.post("/api/projects/{project_id}/blocks")
def create_block_api(
    project_id: int,
    payload: BlockPayload,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    scheme = project_to_schema(project)
    blocks = scheme["blocks"]

    new_block = payload_to_block(payload)
    if any(block["uid"] == new_block["uid"] for block in blocks):
        raise HTTPException(status_code=400, detail="Блок з таким ID вже існує")

    blocks.append(new_block)
    errors = validate_blocks(blocks)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    updated_project = persist_schema(db, project, blocks)
    return {
        "ok": True,
        "scheme": project_to_schema(updated_project),
    }


@router.put("/api/projects/{project_id}/blocks/{block_uid}")
def update_block_api(
    project_id: int,
    block_uid: str,
    payload: BlockPayload,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)
    scheme = project_to_schema(project)
    blocks = scheme["blocks"]

    target_index = next(
        (index for index, block in enumerate(blocks) if block["uid"] == block_uid),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=404, detail="Блок не знайдено")

    updated = payload_to_block(payload)
    updated["uid"] = block_uid
    blocks[target_index] = updated

    errors = validate_blocks(blocks)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    updated_project = persist_schema(db, project, blocks)
    return {
        "ok": True,
        "scheme": project_to_schema(updated_project),
    }


@router.delete("/api/projects/{project_id}/blocks/{block_uid}")
def delete_block_api(project_id: int, block_uid: str, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    scheme = project_to_schema(project)

    blocks = [block for block in scheme["blocks"] if block["uid"] != block_uid]
    if len(blocks) == len(scheme["blocks"]):
        raise HTTPException(status_code=404, detail="Блок не знайдено")

    errors = validate_blocks(blocks)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    updated_project = persist_schema(db, project, blocks)
    return {
        "ok": True,
        "scheme": project_to_schema(updated_project),
    }
