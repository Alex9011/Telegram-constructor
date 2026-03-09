import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Block, Project
from .flow_engine import validate_blocks

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data"
_TEMPLATE_MAP = {
    "barbershop": "barbershop_template.json",
}
BARBERSHOP_DEMO_PROJECT_NAME = "Демо: OldBoy Style (Барбершоп)"
_RUSSIAN_TEXT_MARKERS = (
    "Услуги и цены",
    "Барберы",
    "Адрес и график",
    "Контакты",
    "Частые вопросы",
    "Подтвердить",
    "Изменить",
    "Отмена",
    "Как добраться",
)


def _read_template_file(template_name: str) -> Dict[str, Any]:
    file_name = _TEMPLATE_MAP.get(template_name)
    if not file_name:
        raise ValueError(f"Невідомий шаблон: {template_name}")

    template_path = _TEMPLATE_DIR / file_name
    if not template_path.exists():
        raise ValueError(f"Файл шаблону не знайдено: {template_path.name}")

    with template_path.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)

    if not isinstance(payload, dict):
        raise ValueError("Некоректний формат шаблону")
    return payload


def _normalize_blocks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = payload.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("Шаблон не містить коректного списку blocks")

    normalized: List[Dict[str, Any]] = []
    for item in blocks:
        if not isinstance(item, dict):
            raise ValueError("Блок шаблону має бути об'єктом")

        uid = str(item.get("uid") or "").strip()
        block_type = str(item.get("type") or "").strip()
        data = item.get("data")

        if not uid:
            raise ValueError("У шаблоні знайдено блок без uid")
        if not block_type:
            raise ValueError(f"Блок {uid}: відсутній тип")
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError(f"Блок {uid}: data має бути об'єктом")

        normalized.append(
            {
                "uid": uid,
                "type": block_type,
                "data": deepcopy(data),
            }
        )

    errors = validate_blocks(normalized)
    if errors:
        raise ValueError("Шаблон невалідний: " + "; ".join(errors))

    return normalized


def create_project_from_template(
    db: Session,
    template_name: str,
    project_name: Optional[str] = None,
) -> Project:
    payload = _read_template_file(template_name)
    blocks = _normalize_blocks(payload)

    name_from_template = str(payload.get("name") or "").strip()
    final_name = (project_name or "").strip() or name_from_template or "Демо-проєкт"

    project = Project(name=final_name)
    db.add(project)
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

    project.flow_json = json.dumps(
        {
            "project_id": project.id,
            "name": project.name,
            "blocks": blocks,
        },
        ensure_ascii=False,
    )

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _replace_project_schema(db: Session, project: Project, blocks: List[Dict[str, Any]]) -> Project:
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

    project.flow_json = json.dumps(
        {
            "project_id": project.id,
            "name": project.name,
            "blocks": blocks,
        },
        ensure_ascii=False,
    )

    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _has_russian_content(project: Project) -> bool:
    source = (project.flow_json or "").strip()
    if not source:
        return False
    return any(marker in source for marker in _RUSSIAN_TEXT_MARKERS)


def create_barbershop_template(db: Session) -> Project:
    return create_project_from_template(db=db, template_name="barbershop")


def ensure_barbershop_demo_project(db: Session) -> Project:
    existing = db.query(Project).filter(Project.name == BARBERSHOP_DEMO_PROJECT_NAME).first()
    if existing:
        if _has_russian_content(existing):
            payload = _read_template_file("barbershop")
            blocks = _normalize_blocks(payload)
            return _replace_project_schema(db, existing, blocks)
        return existing
    return create_project_from_template(
        db=db,
        template_name="barbershop",
        project_name=BARBERSHOP_DEMO_PROJECT_NAME,
    )
