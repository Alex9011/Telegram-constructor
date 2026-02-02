import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Block, Project
from ..schemas import BlockPayload, FlowSaveRequest
from ..services.flow_engine import validate_blocks

router = APIRouter()


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
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "projects": projects,
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
