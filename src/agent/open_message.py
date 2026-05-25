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


async def generate_opening_message(memories: list, todos: list) -> str:
    todo_text = todos[0].text if todos else ""
    prompt = f"""
You are MeMen.

Long term memories:
{memories}

Pending followup:
{todo_text}

Write a warm opening message that links past sessions, the current pending task, and detected emotion in a caring way.

Rules:
- Keep under 15 words
- Casual and conversational
- Subtle continuity only
- No emotional interpretation
- No life advice
- No therapist tone
- Sound like a thoughtful friend
"""
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    return strip_think_tags(resp.content)
