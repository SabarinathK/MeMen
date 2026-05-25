import os
import re
import json
import asyncio

from uuid import UUID, uuid4

from dotenv import load_dotenv

from sqlmodel import select

from langgraph.graph import StateGraph, START, END

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from mem0 import Memory

from src.models import User, TodoItem
from src.agent.state import ChatState
from src.agent.node.memory_node import memory_node
import chromadb
from src.agent.settings import *
from src.database import get_session
from src.agent.settings import llm, chroma_client, collection
from typing import Optional

load_dotenv()


def strip_think_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def load_long_term_memories(user_id: str) -> list:
    try:
        data = await asyncio.to_thread(
            collection.get,
            where={"user_id": user_id},
        )
        results = [
            {
                "text_lemmatized": data["metadatas"][i].get("text_lemmatized", ""),
                "metadata": data["metadatas"][i],
            }
            for i in range(len(data["ids"]))
        ]
        latest_5 = sorted(
            results,
            key=lambda x: x["metadata"].get("created_at", ""),
            reverse=True,
        )[:5]
        return [r["text_lemmatized"] for r in latest_5 if r["text_lemmatized"]]
    except Exception as e:
        print(f"\n[memory load error] {e}")
        return []


def load_pending_todos(user_id: UUID) -> list:
    with get_session() as session:
        stmt = (
            select(TodoItem)
            .where(
                TodoItem.user_id == user_id,
                TodoItem.status == "pending",
                TodoItem.used_in_opening == False,
            )
            .order_by(TodoItem.created_at.desc())
        )
        return session.exec(stmt).all()


def mark_todos_used(user_id: UUID) -> None:
    with get_session() as session:
        stmt = select(TodoItem).where(
            TodoItem.user_id == user_id,
            TodoItem.status == "pending",
            TodoItem.used_in_opening == False,
        )
        for todo in session.exec(stmt).all():
            todo.used_in_opening = True
            session.add(todo)
        session.commit()


async def generate_opening_message(
    memories: list, todos: list, profile: Optional[dict]
) -> str:
    todo_text = todos[0].text if todos else ""

    # Format the structured identity parameters cleanly for the LLM context wrapper
    if profile:
        profile_block = (
            f"Summary: {profile.get('profile_summary', '')}\n"
            f"Current Focus: {profile.get('current_focus', '')}\n"
            f"Themes Covered: {', '.join(profile.get('themes', []))}\n"
            f"Emotional Archetype: {profile.get('emotional_archetype', '')}"
        )
    else:
        profile_block = "No high-level identity profile established yet."

    prompt = f"""
You are MeMen, a warm, thoughtful mental wellness companion.

[CORE USER PROFILE SCHEMA Context]
{profile_block}

[RELEVANT LTM ATOMIC FACT NODES]
{memories}

[PENDING FOLLOWUP ACTION ITEM]
{todo_text}

Task:
Write a warm, deeply personalized session-opening message. Use the user profile schema to match their current emotional archetype and primary focus area seamlessly without explicitly mentioning the database keys.

Rules:
- Keep under 15 words
- Casual, warm, and conversational
- Subtle continuity only (e.g., 'Hey, how's that evening walking goal going?')
- No explicit emotional interpretation or therapist phrasing
- No life advice
- Sound like a thoughtful friend checking in via text
"""
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    return strip_think_tags(resp.content)
