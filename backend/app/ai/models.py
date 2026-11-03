"""SQLAlchemy models for the prompt registry and run history."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    LargeBinary,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    step: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    recognition_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="BUILT_IN", server_default="BUILT_IN")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_versions.id", use_alter=True, name="fk_prompts_active_version"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PromptVersion(Base):
    """Insert-only. A change is always a new row with the next version number."""

    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_prompt_versions_prompt_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    system_text: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(80))
    effort: Mapped[str] = mapped_column(String(20))
    max_tokens: Mapped[int] = mapped_column(Integer)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB)
    field_definitions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    tools: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PromptRun(Base):
    __tablename__ = "prompt_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(80))
    case_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
