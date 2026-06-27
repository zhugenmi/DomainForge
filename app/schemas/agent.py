from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    system_prompt: str = ""
    # 空字符串表示跟随系统配置默认模型（runtime 解析为 settings.DEFAULT_LLM_MODEL）
    model_name: str = Field("", max_length=100)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    domain: str | None = Field(None, max_length=50)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    system_prompt: str | None = None
    model_name: str | None = Field(None, max_length=100)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    domain: str | None = Field(None, max_length=50)


class AgentInfo(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_builtin: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
