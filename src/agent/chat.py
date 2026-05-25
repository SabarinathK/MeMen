from MeMen.src.agent.state import ChatState
from MeMen.src.agent.settings import llm, strip_think_tags
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
from MeMen.src.database import get_session
from MeMen.src.models import User, TodoItem
from uuid import UUID, uuid4
from sqlmodel import select
from MeMen.src.agent.open_message import (
    generate_opening_message,
    load_long_term_memories,
    load_pending_todos,
    mark_todos_used,
)
import asyncio
from MeMen.src.agent.graph.graph import graph


async def run_chat(user_id: str):
    with get_session() as session:
        user = session.exec(select(User).where(User.username == user_id)).first()

    if not user:
        print("User not found")
        return

    user_id = user.id
    conversation_id = uuid4()

    memories, todos = await asyncio.gather(
        load_long_term_memories(str(user_id)),
        asyncio.to_thread(load_pending_todos, user_id),
    )

    print(f"\n[+] Loaded {len(memories)} memories")
    print(f"[+] Loaded {len(todos)} todos")

    opening = await generate_opening_message(memories, todos)
    mark_todos_used(user_id)

    print("\n" + "─" * 60)
    print(f"MeMen: {opening}")
    print("─" * 60)

    history = [AIMessage(content=opening)]

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        # FIX 3: initialise Optional fields to None, not silent defaults
        state = ChatState(
            user_id=str(user_id),
            conversation_id=str(conversation_id),
            user_input=user_input,
            history=history,
            relevant_memories=None,  # written by memory_node
            emotion=None,  # written by emotion_node
            todo_status=None,  # written by todo_node
            active_todo=None,
            reply=None,  # written by response_node
        )

        result = await graph.ainvoke(state)

        history.append(HumanMessage(content=user_input))
        history.append(AIMessage(content=result["reply"]))


if __name__ == "__main__":
    asyncio.run(run_chat(user_id="sabari"))
