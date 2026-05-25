from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4
import json
from sqlmodel import SQLModel, Field as SQLField, JSON
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True)
    hashed_password: str
    memory_consent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    title: str = Field(default="New conversation")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(index=True)
    user_id: UUID = Field(index=True)
    role: str  # "user" | "assistant"
    content_encrypted: str  # fernet encrypted
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TodoItem(SQLModel, table=True):
    __tablename__ = "todo_items"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    conversation_id: Optional[UUID] = Field(default=None)
    text: str
    status: str = Field(default="pending")  # pending | done | dismissed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    used_in_opening: bool = Field(default=False)


class SessionMemoryMeta(SQLModel, table=True):
    """Audit trail for what Mem0 extracted — not the raw content."""

    __tablename__ = "session_memory_meta"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    conversation_id: UUID = Field(index=True)
    extraction_model: str = Field(default="openai/gpt-4o-mini")
    risk_flag: bool = Field(default=False)
    pii_redacted: bool = Field(default=True)
    consent_version: str = Field(default="v1.0")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime  # 90 days from now


class UserMemorySchema(SQLModel, table=True):
    __tablename__ = "user_identity_profiles"

    user_id: str = SQLField(primary_key=True, index=True)
    schema_version: str = SQLField(default="1.0.0")
    last_updated: datetime = SQLField(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    profile_summary: str = SQLField(default="")
    current_focus: Optional[str] = SQLField(default=None)
    emotional_archetype: Optional[str] = SQLField(default=None)

    # Store dynamic arrays and nested properties safely using JSON column types
    themes: List[str] = SQLField(default_factory=list, sa_type=JSON)
    key_memories: List[Dict[str, Any]] = SQLField(default_factory=list, sa_type=JSON)
    preferences: Dict[str, Any] = SQLField(default_factory=dict, sa_type=JSON)
    consent: Dict[str, Any] = SQLField(default_factory=dict, sa_type=JSON)
