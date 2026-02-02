from typing import Any, Dict, List, Optional, Tuple

ALLOWED_BLOCK_TYPES = {"start", "message", "buttons", "input", "end"}


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def build_block_map(blocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {block["uid"]: block for block in blocks}


def extract_next_ids(block: Dict[str, Any]) -> List[str]:
    data = block.get("data", {}) or {}
    next_ids: List[str] = []

    if block["type"] in {"start", "message", "input"}:
        next_block_id = data.get("next_block_id")
        if next_block_id:
            next_ids.append(next_block_id)

    if block["type"] == "buttons":
        for button in data.get("buttons", []):
            next_block_id = (button or {}).get("next_block_id")
            if next_block_id:
                next_ids.append(next_block_id)

    return next_ids


def validate_blocks(blocks: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []

    if not blocks:
        return ["Схема порожня. Додайте хоча б блоки start та end."]

    block_ids = [block.get("uid") for block in blocks]
    unique_block_ids = set(block_ids)

    if len(block_ids) != len(unique_block_ids):
        errors.append("ID блоків мають бути унікальними.")

    start_count = sum(1 for block in blocks if block.get("type") == "start")
    if start_count != 1:
        errors.append("У проєкті має бути рівно один блок start.")

    block_map = build_block_map(blocks)

    for block in blocks:
        block_type = block.get("type")
        block_id = block.get("uid")

        if block_type not in ALLOWED_BLOCK_TYPES:
            errors.append(f"Блок {block_id}: непідтримуваний тип {block_type}.")
            continue

        data = block.get("data", {}) or {}

        if block_type == "buttons" and not isinstance(data.get("buttons", []), list):
            errors.append(f"Блок {block_id}: поле buttons має бути списком.")

        for next_id in extract_next_ids(block):
            if next_id not in block_map:
                errors.append(
                    f"Блок {block_id}: перехід вказує на неіснуючий блок {next_id}."
                )

    return errors


def interpolate_text(template: Any, variables: Dict[str, Any]) -> str:
    if not isinstance(template, str):
        return ""

    try:
        return template.format_map(SafeFormatDict(variables))
    except Exception:
        return template


def find_start_block_id(blocks: List[Dict[str, Any]]) -> Optional[str]:
    for block in blocks:
        if block.get("type") == "start":
            return block.get("uid")
    return None


def run_automatic_steps(
    blocks: List[Dict[str, Any]],
    state: Dict[str, Any],
    max_hops: int = 100,
    block_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    events: List[Dict[str, Any]] = []
    if block_map is None:
        block_map = build_block_map(blocks)
    hops = 0

    while True:
        if hops >= max_hops:
            events.append(
                {
                    "type": "error",
                    "text": "Перевищено ліміт кроків. Можливий нескінченний цикл.",
                }
            )
            state["current_block_id"] = None
            state["waiting"] = None
            return events, True

        current_block_id = state.get("current_block_id")
        if not current_block_id:
            events.append(
                {
                    "type": "end",
                    "text": "Сценарій завершено (немає наступного блоку).",
                }
            )
            state["waiting"] = None
            return events, True

        block = block_map.get(current_block_id)
        if not block:
            events.append(
                {
                    "type": "error",
                    "text": f"Поточний блок {current_block_id} не знайдено.",
                }
            )
            state["current_block_id"] = None
            state["waiting"] = None
            return events, True

        block_type = block.get("type")
        data = block.get("data", {}) or {}
        variables = state.get("variables", {})

        if block_type == "start":
            state["current_block_id"] = data.get("next_block_id")
            hops += 1
            continue

        if block_type == "message":
            events.append(
                {
                    "type": "message",
                    "text": interpolate_text(data.get("text", ""), variables),
                }
            )
            state["current_block_id"] = data.get("next_block_id")
            hops += 1
            continue

        if block_type == "buttons":
            buttons = []
            for item in data.get("buttons", []):
                item = item or {}
                label = str(item.get("label", "Кнопка")).strip() or "Кнопка"
                buttons.append(
                    {
                        "label": label,
                        "next_block_id": item.get("next_block_id"),
                    }
                )

            events.append(
                {
                    "type": "buttons",
                    "text": interpolate_text(data.get("text", "Оберіть кнопку"), variables),
                    "buttons": buttons,
                }
            )
            state["waiting"] = "buttons"
            return events, False

        if block_type == "input":
            events.append(
                {
                    "type": "input",
                    "question": interpolate_text(
                        data.get("question", "Введіть текст"),
                        variables,
                    ),
                    "variable_name": data.get("variable_name", "user_input"),
                }
            )
            state["waiting"] = "input"
            return events, False

        if block_type == "end":
            events.append(
                {
                    "type": "end",
                    "text": "Сценарій завершено.",
                }
            )
            state["current_block_id"] = None
            state["waiting"] = None
            return events, True

        events.append(
            {
                "type": "error",
                "text": f"Непідтримуваний тип блоку: {block_type}",
            }
        )
        state["current_block_id"] = None
        state["waiting"] = None
        return events, True


def advance_with_action(
    blocks: List[Dict[str, Any]],
    state: Dict[str, Any],
    action: str,
    button_index: Optional[int] = None,
    input_text: Optional[str] = None,
    block_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    if block_map is None:
        block_map = build_block_map(blocks)
    current_block = block_map.get(state.get("current_block_id"))

    waiting = state.get("waiting")
    if waiting == "buttons":
        if action != "choose":
            return [{"type": "error", "text": "Очікується вибір кнопки."}], False

        if not current_block:
            return [{"type": "error", "text": "Поточний блок для вибору не знайдено."}], True

        buttons = (current_block.get("data", {}) or {}).get("buttons", [])
        if button_index is None or button_index < 0 or button_index >= len(buttons):
            return [{"type": "error", "text": "Некоректний індекс кнопки."}], False

        next_block_id = (buttons[button_index] or {}).get("next_block_id")
        state["current_block_id"] = next_block_id
        state["waiting"] = None
        return run_automatic_steps(blocks, state, block_map=block_map)

    if waiting == "input":
        if action != "input":
            return [{"type": "error", "text": "Очікується введення тексту."}], False

        if not current_block:
            return [{"type": "error", "text": "Поточний блок для введення не знайдено."}], True

        data = current_block.get("data", {}) or {}
        variable_name = str(data.get("variable_name", "user_input")).strip() or "user_input"
        state.setdefault("variables", {})[variable_name] = input_text or ""

        state["current_block_id"] = data.get("next_block_id")
        state["waiting"] = None
        return run_automatic_steps(blocks, state, block_map=block_map)

    return run_automatic_steps(blocks, state, block_map=block_map)
