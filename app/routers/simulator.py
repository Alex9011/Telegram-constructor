import json
import time
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Project
from ..schemas import SimulatorActionRequest
from ..services.flow_engine import (
    advance_with_action,
    find_start_block_id,
    run_automatic_steps,
    validate_blocks,
)

router = APIRouter()
SIM_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_TTL_SECONDS = 60 * 60


def parse_block_data(data_json: str) -> Dict[str, Any]:
    try:
        value = json.loads(data_json or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проєкт не знайдено")
    return project


def get_project_blocks(project: Project) -> List[Dict[str, Any]]:
    ordered_blocks = sorted(project.blocks, key=lambda item: item.id)
    return [
        {
            "uid": block.uid,
            "type": block.block_type,
            "data": parse_block_data(block.data_json),
        }
        for block in ordered_blocks
    ]


def clean_old_sessions() -> None:
    now = time.time()
    stale_session_ids = [
        session_id
        for session_id, session in SIM_SESSIONS.items()
        if now - session.get("updated_at", now) > SESSION_TTL_SECONDS
    ]
    for session_id in stale_session_ids:
        SIM_SESSIONS.pop(session_id, None)


@router.get("/projects/{project_id}/simulator", response_class=HTMLResponse)
def simulator_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = get_project_or_404(db, project_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "simulator.html",
        {
            "request": request,
            "project": project,
        },
    )


@router.post("/api/simulator/start/{project_id}")
def simulator_start(project_id: int, db: Session = Depends(get_db)):
    clean_old_sessions()
    project = get_project_or_404(db, project_id)
    blocks = get_project_blocks(project)

    errors = validate_blocks(blocks)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    start_block_id = find_start_block_id(blocks)
    if not start_block_id:
        raise HTTPException(status_code=400, detail="Не знайдено блок start")

    block_map = {block["uid"]: block for block in blocks}

    state = {
        "current_block_id": start_block_id,
        "variables": {},
        "waiting": None,
    }

    events, finished = run_automatic_steps(blocks, state, block_map=block_map)
    session_id = str(uuid.uuid4())

    if not finished:
        SIM_SESSIONS[session_id] = {
            "project_id": project_id,
            "blocks": blocks,
            "block_map": block_map,
            "state": state,
            "updated_at": time.time(),
        }

    return {
        "session_id": session_id,
        "events": events,
        "finished": finished,
        "waiting": state.get("waiting"),
        "variables": state.get("variables", {}),
    }


@router.post("/api/simulator/step/{session_id}")
def simulator_step(
    session_id: str,
    payload: SimulatorActionRequest,
):
    clean_old_sessions()
    session = SIM_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сесію симуляції не знайдено")

    events, finished = advance_with_action(
        session["blocks"],
        session["state"],
        action=payload.action,
        button_index=payload.button_index,
        input_text=payload.input_text,
        block_map=session.get("block_map"),
    )

    state = session["state"]

    if finished:
        SIM_SESSIONS.pop(session_id, None)
    else:
        session["updated_at"] = time.time()

    return {
        "session_id": session_id,
        "events": events,
        "finished": finished,
        "waiting": state.get("waiting"),
        "variables": state.get("variables", {}),
    }
