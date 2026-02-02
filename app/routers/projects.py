import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Block, Project

router = APIRouter()


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проєкт не знайдено")
    return project


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
