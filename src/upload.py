import os
import json
import re
from datetime import datetime
from typing import List, Tuple

from dotenv import load_dotenv

from mem0 import Memory

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from sqlmodel import select
from sqlmodel import Session as SM_Session

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.upload import TRANSCRIPTS
from src.config import mem0_config, DATABASE_URL
from src.models import User, Conversation, Message, TodoItem
from src.memory import encrypt_message, build_and_cache_recall

load_dotenv()

if not os.getenv("OPENROUTER_API_KEY"):
    raise ValueError("OPENROUTER_API_KEY missing")

bot = ChatOpenAI(
    model="openai/gpt-4o-mini",
    openai_api_base="https://openrouter.ai/api/v1",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
)


def split_turns(text: str) -> List[Tuple[str, str]]:
    """
    Split transcript into structured conversation turns.
    """

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
                turns.append(
                    (
                        current_role,
                        " ".join(buffer).strip(),
                    )
                )

            current_role = "user"
            buffer = [line.replace("User:", "", 1).strip()]

        elif line.startswith("MeMen:"):

            if current_role and buffer:
                turns.append(
                    (
                        current_role,
                        " ".join(buffer).strip(),
                    )
                )

            current_role = "assistant"
            buffer = [line.replace("MeMen:", "", 1).strip()]

        else:
            if buffer:
                buffer.append(line)

    if current_role and buffer:
        turns.append(
            (
                current_role,
                " ".join(buffer).strip(),
            )
        )

    return turns


def find_or_create_user(
    username: str,
    session: SM_Session,
) -> User:

    user = session.exec(select(User).where(User.username == username)).first()

    if user:
        return user

    from passlib.context import CryptContext

    pwd_context = CryptContext(
        schemes=["pbkdf2_sha256"],
        deprecated="auto",
    )

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

    prompt = """You are reviewing the final session of a mental wellness conversation history.

            Session transcript:
            {text}

            Extract concrete things the user committed to, expressed intent to try,
            or that MeMen suggested and the user agreed to — especially things
            MeMen said it would follow up on.

            Return ONLY a JSON array of short strings. Max 3 items.
            No explanation. No markdown.

            Example: ["update LinkedIn photo today", "try journaling once this week"]"""

    try:

        response = bot.invoke([HumanMessage(content=prompt)])

        content = str(response.content).strip()

        content = re.sub(r"^```json", "", content)
        content = re.sub(r"^```", "", content)
        content = re.sub(r"```$", "", content)

        content = content.strip()

        parsed = json.loads(content)

        if isinstance(parsed, list):
            return [str(x) for x in parsed][:3]

        return []

    except json.JSONDecodeError:
        print("[WARN] Invalid JSON returned")
        return []

    except Exception as e:
        print("[WARN] Followup extraction failed:", e)
        return []


def main(username: str):

    print("\nStarting transcript ingestion...\n")

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

        user = find_or_create_user(
            target_username,
            db,
        )

        print(f"Using user: {user.username}")

        last_conversation_id = None

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

    print("\nDone!\n")


if __name__ == "__main__":
    main(username="sabari")
