import os
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple


from dotenv import load_dotenv


from mem0 import Memory
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sqlmodel import select
from sqlmodel import Session as SM_Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from src.config import mem0_config, DATABASE_URL
from src.models import User, Conversation, Message, TodoItem
from src.memory import encrypt_message, build_and_cache_recall
from src.transcript import TRANSCRIPTS
from src.upload import *

load_dotenv()


if not os.getenv("OPENROUTER_API_KEY"):
    raise ValueError("OPENROUTER_API_KEY missing")


bot = ChatOpenAI(
    model="openai/gpt-4o-mini",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Example: your schema‑aligned memory object
USER_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "schema_version": {"type": "string"},
        "last_updated": {"type": "string", "format": "date-time"},
        "profile_summary": {"type": "string"},
        "current_focus": {"type": "string"},
        "themes": {"type": "array", "items": {"type": "string"}},
        "emotional_archetype": {"type": "string"},
        "key_memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "session_theme": {"type": "string"},
                    "emotional_tone": {"type": "string"},
                    "summary": {"type": "string"},
                    "action_taken": {"type": "string"},
                    "sentiment_impact": {"type": "string"},
                },
                "required": [
                    "id",
                    "timestamp",
                    "session_theme",
                    "emotional_tone",
                    "summary",
                ],
            },
        },
        "preferences": {
            "type": "object",
            "properties": {
                "tone": {"type": "string"},
                "depth_preference": {"type": "string"},
                "avoid_topics": {"type": "array", "items": {"type": "string"}},
                "response_style": {"type": "string"},
            },
        },
        "consent": {
            "type": "object",
            "properties": {
                "memory_enabled": {"type": "boolean"},
                "session_summaries_archived": {"type": "boolean"},
                "deletion_requested": {"type": "boolean"},
            },
            "required": [
                "memory_enabled",
                "session_summaries_archived",
                "deletion_requested",
            ],
        },
    },
    "required": [
        "user_id",
        "schema_version",
        "last_updated",
        "profile_summary",
        "themes",
        "key_memories",
        "preferences",
        "consent",
    ],
}


# === NEW: extract structured memory summary ===
def extract_memory_summary(
    session_text: str,
    session_label: str,
    session_id: int,
) -> Dict[str, Any]:
    """
    Call LLM to extract a structured memory summary for one session.
    In practice, for DeepSeek you'd enable JSON mode and validate against USER_MEMORY_SCHEMA.
    """
    prompt = f"""
You are a psychology‑aware assistant that helps a therapist AI remember key insights from past sessions.

Please read this session transcript and return a JSON object that matches the following schema:

{json.dumps(USER_MEMORY_SCHEMA, indent=2)}

Guidelines:
- `profile_summary`: 2–3 sentences summarizing the user's main struggles, growth, and emotional tone.
- `current_focus`: 1 sentence describing the user's current main concern.
- `themes`: 3–5 short strings (e.g., ["anxiety", "work‑life balance"]).
- `emotional_archetype`: 1 short phrase describing the user's predominant emotional pattern or style.
- `key_memories`: Array of exactly one entry representing this session:
  - `id`: "s{session_id}"
  - `timestamp`: use ISO 8601 UTC (e.g., "2026-05-25T18:00:00Z")
  - `session_theme`: session label
  - `emotional_tone`: 1–2 words describing the user's mood (e.g., "frustrated", "relieved")
  - `summary`: 1–2 sentences in a warm, narrative tone describing what happened.
  - `action_taken`: What the user committed to, tried, or agreed to do.
  - `sentiment_impact`: 1 short phrase describing how the user felt after the session.
- `preferences`:
  - `tone`: how the user prefers the AI to sound (e.g., "gentle, validating").
  - `depth_preference`: how much depth the user likes early vs. later (e.g., "moderate early, deeper later").
  - `avoid_topics`: topics the user has asked to avoid (e.g., "family conflict", "past trauma").
  - `response_style`: how the user prefers responses (e.g., "short paragraphs, 1‑2 questions").
- `consent`:
  - `memory_enabled`: True
  - `session_summaries_archived`: True
  - `deletion_requested`: False

Session transcript:
{session_text}

Return only a valid JSON object, no extra text, no markdown.
""".strip()

    try:
        response = bot.invoke([HumanMessage(content=prompt)])
        content = str(response.content).strip()

        # If you were using DeepSeek or another JSON‑mode API, you'd set:
        #   response_format={"type": "json_object"}
        # and parse directly; here we just clean and parse.
        content = re.sub(r"^```json", "", content)
        content = re.sub(r"^```", "", content)
        content = re.sub(r"```$", "", content)
        content = content.strip()

        parsed = json.loads(content)
        if isinstance(parsed, dict):
            # Patch in missing fields to roughly match schema
            parsed.setdefault("user_id", "usr_123")
            parsed.setdefault("schema_version", "1.0")
            parsed.setdefault(
                "last_updated",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            return parsed
    except (json.JSONDecodeError, Exception) as e:
        print(f"[WARN] Failed to parse memory JSON for session {session_id}: {e}")

    # Fallback minimal memory
    return {
        "user_id": "usr_123",
        "schema_version": "1.0",
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "profile_summary": "User shared feelings of anxiety and stress and is exploring ways to cope with them.",
        "current_focus": "Managing stress and sleep issues.",
        "themes": ["anxiety", "stress", "sleep"],
        "emotional_archetype": "overwhelmed, caring",
        "key_memories": [
            {
                "id": f"s{session_id}",
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "session_theme": session_label,
                "emotional_tone": "neutral",
                "summary": f"User discussed {session_label.lower()} and agreed to try some coping strategies.",
                "action_taken": "User agreed to try a grounding exercise or small behavioral change.",
                "sentiment_impact": "slightly more hopeful",
            }
        ],
        "preferences": {
            "tone": "gentle, validating",
            "depth_preference": "moderate early, deeper later",
            "avoid_topics": [],
            "response_style": "short paragraphs, 1–2 questions",
        },
        "consent": {
            "memory_enabled": True,
            "session_summaries_archived": True,
            "deletion_requested": False,
        },
    }


# === NEW: merge session‑level memory into a per‑user artifact ===
def merge_memory_into_user(user_id: str, base_memory: Dict[str, Any]) -> Dict[str, Any]:
    """
    In real code, you'd:
    - Load existing user memory artifact from DB.
    - Merge new key_memories (limit to last N).
    - Re‑summarize profile_summary / current_focus if needed.
    - Return the updated memory JSON.
    """
    # In practice you'd load from DB; here we fake it
    user_memory = {
        "user_id": user_id,
        "schema_version": "1.0",
        "last_updated": base_memory["last_updated"],
        "profile_summary": base_memory.get(
            "profile_summary", "User is exploring anxiety and stress concerns."
        ),
        "current_focus": base_memory.get(
            "current_focus", "Managing stress and sleep issues."
        ),
        "themes": list(set(base_memory.get("themes", []) + ["stress", "anxiety"][:2])),
        "emotional_archetype": base_memory.get(
            "emotional_archetype", "overwhelmed, caring"
        ),
        "key_memories": base_memory.get("key_memories", []),
        "preferences": base_memory.get(
            "preferences",
            {
                "tone": "gentle, validating",
                "depth_preference": "moderate early, deeper later",
                "avoid_topics": [],
                "response_style": "short paragraphs, 1–2 questions",
            },
        ),
        "consent": base_memory.get(
            "consent",
            {
                "memory_enabled": True,
                "session_summaries_archived": True,
                "deletion_requested": False,
            },
        ),
    }

    # Trim key_memories to, say, last 5
    user_memory["key_memories"] = user_memory["key_memories"][-5:]
    user_memory["last_updated"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    return user_memory


# === NEW: generate a warm opening message referencing past sessions ===
def generate_warm_opening(user_memory: Dict[str, Any]) -> str:
    """
    Use the memory JSON to generate a warm, natural‑sounding opening.
    In production you'd call the LLM with the user_memory injected into the context.
    """
    # Example: hard‑coded template using the memory
    last_mem = user_memory["key_memories"][-1] if user_memory["key_memories"] else None
    if last_mem:
        opening = (
            f"Hi there. It’s good to reconnect. "
            f"Last time we talked about {last_mem['session_theme'].lower()} "
            f"and you mentioned feeling {last_mem['emotional_tone']} — "
            f"it’s okay if that still feels tough. "
            f"Since then, your current focus has been on {user_memory['current_focus'].lower()}. "
            f"Would you like to start there, or is there something else on your mind today?"
        )
    else:
        opening = (
            f"Hi there. Long time no talk. "
            f"From what we’ve explored so far, you’ve been working on {user_memory['current_focus'].lower()}. "
            f"Would you like to pick up there today, or share what’s freshest on your mind?"
        )

    return opening


# === main(...) updated to show memory extraction and opening message ===
def main(username: str):
    print("\nStarting transcript ingestion and memory extraction...\n")

    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(
        bind=engine,
        class_=SM_Session,
        autoflush=False,
        autocommit=False,
    )

    try:
        mem0 = Memory.from_config(mem0_config)
    except Exception as e:
        print("\n[ERROR] Mem0 initialization failed")
        print(e)
        return

    with SessionLocal() as db:
        target_username = username
        user = find_or_create_user(target_username, db)
        print(f"Using user: {user.username}")

        last_conversation_id = None

        # --- First: ingest conversations as before ---
        for transcript in TRANSCRIPTS:
            print(f"\nProcessing Session {transcript['session']}...")

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
                        created_at=datetime.utcnow(),
                    )
                    db.add(message)
                except Exception as e:
                    print(f"[WARN] Failed storing message: {e}")

            db.commit()

            # Send raw transcript to mem0 for traditional memory
            try:
                mem0.add(
                    messages=[
                        {
                            "role": "user",
                            "content": transcript["text"].strip(),
                        }
                    ],
                    user_id=str(user.id),
                )
                print(f"[OK] Memory stored for Session {transcript['session']}")
            except Exception as e:
                print(f"[WARN] Mem0 add failed: {e}")

            last_conversation_id = conversation.id

        try:
            build_and_cache_recall(
                str(user.id),
                [],
            )
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

        # --- NEW: extract structured memory summaries for each session ---
        print("\n--- Generating structured memories ---")
        user_memories = []
        for transcript in TRANSCRIPTS:
            print(f"Extracting memory for Session {transcript['session']}...")
            memory = extract_memory_summary(
                session_text=transcript["text"],
                session_label=transcript["label"],
                session_id=transcript["session"],
            )
            user_memories.append(memory)

        # --- Merge into a single user memory artifact ---
        if user_memories:
            # In reality, you’d load existing user memory from DB and merge incrementally
            merged_memory = user_memories[-1]  # for demo, just use last session
            consolidated_memory = merge_memory_into_user(str(user.id), merged_memory)

            # --- Print a warm opening message as a demo ---
            print("\n--- Warm opening message ---")
            opening = generate_warm_opening(consolidated_memory)
            print(opening)

            # In production, you’d:
            #  - store consolidated_memory in DB (e.g., JSONB column)
            #  - inject it into the LLM context at session start
        else:
            print("\nNo memory summaries generated.")

    print("\nDone!\n")


if __name__ == "__main__":
    main(username="sabari")
