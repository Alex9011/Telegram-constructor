from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_BLOCK_TYPES = {"start", "message", "buttons", "input", "end"}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class BlockPayload(BaseModel):
    uid: str = Field(..., min_length=1, max_length=50)
    block_type: str = Field(..., alias="type")
    data: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @field_validator("block_type")
    @classmethod
    def validate_block_type(cls, value: str) -> str:
        if value not in ALLOWED_BLOCK_TYPES:
            raise ValueError(f"Unsupported block type: {value}")
        return value


class FlowSaveRequest(BaseModel):
    blocks: List[BlockPayload] = Field(default_factory=list)


class SimulatorActionRequest(BaseModel):
    action: str = Field(..., pattern="^(next|choose|input)$")
    button_index: Optional[int] = None
    input_text: Optional[str] = None
