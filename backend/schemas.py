"""API 与视觉大模型输出的严格数据结构。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=100)
    count: StrictInt = Field(ge=1, le=10_000)
    confidence: Literal["high", "medium", "low"]
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("name", "reason")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value


class InventoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scene: str = Field(min_length=1, max_length=100)
    items: list[InventoryItem]

    @field_validator("scene")
    @classmethod
    def reject_blank_scene(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("场景不能为空")
        return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)
