import os
import json
import re
import hashlib
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Tuple

from dotenv import load_dotenv
from mem0 import Memory
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlmodel import select, create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session as SM_Session

from src.transcript import TRANSCRIPTS
from src.config import mem0_config, DATABASE_URL
from src.models import User, Conversation, Message, TodoItem, UserMemorySchema
from src.memory import encrypt_message, build_and_cache_recall, redact_pii

load_dotenv()

if not os.getenv("OPENROUTER_API_KEY"):
    raise ValueError("OPENROUTER_API_KEY missing")

llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.1,
)


class KeyMemoryItem(BaseModel):
    id: str = Field(description="Unique session snapshot tracking ID")
    timestamp: str = Field(description="ISO date-time string representation")
    session_theme: str = Field(description="Dominant theme discussed")
    emotional_tone: str = Field(description="User emotional state overview")
    summary: str = Field(description="Factual core breakdown")
    action_taken: str = Field(default="")
    sentiment_impact: str = Field(default="")


class ProfilePreferences(BaseModel):
    tone: str = Field(default="")
    depth_preference: str = Field(default="")
    avoid_topics: List[str] = Field(default_factory=list)
    response_style: str = Field(default="")


class CoreConsent(BaseModel):
    memory_enabled: bool
    session_summaries_archived: bool
    deletion_requested: bool


class FullIdentityProfileExtractor(BaseModel):
    schema_version: str = Field(default="1.0.0")
    profile_summary: str = Field(
        description="Cohesive high-level synthesis of user state"
    )
    current_focus: str = Field(default="")
    emotional_archetype: str = Field(default="")
    themes: List[str] = Field(default_factory=list)
    key_memories: List[KeyMemoryItem] = Field(default_factory=list)
    preferences: ProfilePreferences
    consent: CoreConsent


# Dynamic runtime verification binding for LangChain structured outputs
structured_identity_llm = llm.with_structured_output(FullIdentityProfileExtractor)

identity_prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an identity profiling engine. Synthesize conversation inputs "
                "and existing schema parameters into a unified profile matching the requested structure. "
                "Ensure data privacy rules and consent flags are preserved accurately."
            ),
        ),
        (
            "human",
            "Transcript:\n{transcript}\n\nExisting Profile State Context:\n{existing_context}",
        ),
    ]
)

identity_extraction_chain = identity_prompt_template | structured_identity_llm


def split_turns(text: str) -> List[Tuple[str, str]]:
    lines = text.splitlines()
    turns = []
    current_role = None
    buffer = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("User:"):
            if current_role and buffer:
                turns.append((current_role, " ".join(buffer).strip()))
            current_role = "user"
            buffer = [line.replace("User:", "", 1).strip()]
        elif line.startswith("MeMen:"):
            if current_role and buffer:
                turns.append((current_role, " ".join(buffer).strip()))
            current_role = "assistant"
            buffer = [line.replace("MeMen:", "", 1).strip()]
        else:
            if buffer:
                buffer.append(line)

    if current_role and buffer:
        turns.append((current_role, " ".join(buffer).strip()))
    return turns


def find_or_create_user(username: str, session: SM_Session) -> User:
    user = session.exec(select(User).where(User.username == username)).first()
    if user:
        return user

    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    hashed_password = pwd_context.hash("Password123")

    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hashed_password,
        memory_consent=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def extract_followups(text: str) -> List[str]:
    prompt = f"You are reviewing the final session of a mental wellness conversation history.\nSession transcript:\n{text}\nExtract concrete things the user committed to.\nReturn ONLY a JSON array of short strings. Max 3 items."
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = str(response.content).strip()
        content = re.sub(r"^```json|```$", "", content, flags=re.IGNORECASE).strip()
        parsed = json.loads(content)
        return [str(x) for x in parsed][:3] if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[WARN] Followup extraction failed: {e}")
        return []


def sync_structured_identity_profile(
    user_id: str, transcript: str, db: SM_Session
) -> None:
    try:
        profile = db.get(UserMemorySchema, user_id)
        existing_context = profile.model_dump_json() if profile else "{}"

        # Invoke the LangChain extraction graph
        extracted_data: FullIdentityProfileExtractor = identity_extraction_chain.invoke(
            {"transcript": transcript, "existing_context": existing_context}
        )

        now = datetime.now(timezone.utc)
        model_dictionary = extracted_data.model_dump()

        if profile:
            profile.schema_version = model_dictionary["schema_version"]
            profile.last_updated = now
            profile.profile_summary = model_dictionary["profile_summary"]
            profile.current_focus = model_dictionary["current_focus"]
            profile.emotional_archetype = model_dictionary["emotional_archetype"]
            profile.themes = model_dictionary["themes"]
            profile.key_memories = model_dictionary["key_memories"]
            profile.preferences = model_dictionary["preferences"]
            profile.consent = model_dictionary["consent"]
            db.add(profile)
        else:
            new_profile = UserMemorySchema(
                user_id=user_id, last_updated=now, **model_dictionary
            )
            db.add(new_profile)
        db.commit()
        print(
            f"[OK] Structured UserMemorySchema compiled by LangChain for user {user_id}"
        )
    except Exception as e:
        print(f"[FAILURE BOUNDARY] LangChain identity schema compilation aborted: {e}")


def main(username: str):
    print("\nStarting transcript ingestion...\n")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(
        bind=engine, class_=SM_Session, autoflush=False, autocommit=False
    )

    try:
        mem0 = Memory.from_config(mem0_config)
    except Exception as e:
        print(f"\n[ERROR] Mem0 initialization failed: {e}")
        return

    with SessionLocal() as db:
        user = find_or_create_user(username, db)
        print(f"Using user: {user.username}")
        last_conversation_id = None
        combined_transcripts_text = ""

        for transcript in TRANSCRIPTS:
            print(f"\nProcessing Session {transcript['session']}...")
            combined_transcripts_text += f"\n{transcript['text']}"

            conversation = Conversation(
                user_id=user.id,
                title=f"Session {transcript['session']}: {transcript['label']}",
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)

            turns = split_turns(transcript["text"])
            for role, content in turns:
                try:
                    encrypted = encrypt_message(content)
                    message = Message(
                        conversation_id=conversation.id,
                        user_id=user.id,
                        role=role,
                        content_encrypted=encrypted,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(message)
                except Exception as e:
                    print(f"[WARN] Failed storing message: {e}")
            db.commit()

            # Idempotent Unstructured Vector Storage
            try:
                clean_text = redact_pii(transcript["text"].strip())
                hasher = hashlib.sha256(clean_text.encode("utf-8"))
                namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
                deterministic_run_id = str(
                    uuid.uuid5(namespace, f"{user.id}_{hasher.hexdigest()}")
                )

                mem0.add(
                    messages=[{"role": "user", "content": clean_text}],
                    user_id=str(user.id),
                    metadata={
                        "run_id": deterministic_run_id,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                print(
                    f"[OK] Unstructured memory fragments securely stored for Session {transcript['session']}"
                )
            except Exception as e:
                print(f"[FAILURE BOUNDARY] Mem0 partition storage bypassed safely: {e}")

            last_conversation_id = conversation.id

        # Compile and Update Core Relational User Identity Profile Matrix
        print("\nCompiling structured identity matrix summary...")
        sync_structured_identity_profile(str(user.id), combined_transcripts_text, db)

        try:
            build_and_cache_recall(str(user.id), [])
            print("\n[OK] Recall cache updated")
        except Exception as e:
            print(f"\n[WARN] Recall cache failed: {e}")

        print("\nExtracting follow-up tasks...")
        followups = extract_followups(TRANSCRIPTS[-1]["text"])

        if followups:
            print(f"\nFound {len(followups)} follow-up items")
            for item in followups:
                print(f" - {item}")
                try:
                    todo = TodoItem(
                        user_id=user.id,
                        conversation_id=last_conversation_id,
                        text=item,
                        status="pending",
                    )
                    db.add(todo)
                except Exception as e:
                    print(f"[WARN] Failed todo insert: {e}")
            db.commit()
        else:
            print("\nNo followups extracted")

    print("\nDone!\n")


if __name__ == "__main__":
    main(username="sabari")
