from src.agent.state import ChatState
from src.agent.settings import llm, strip_think_tags
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
from src.database import get_session
from src.models import User, TodoItem
from uuid import UUID, uuid4
from sqlmodel import select

TODO_UPDATE_PROMPT = """
Analyze whether the user updated a task.

TODO:
"{todo}"

Message:
"{message}"

Return ONLY one of:
DONE
DISMISSED
NONE
"""


async def todo_node(state: ChatState) -> dict:
    try:
        with get_session() as session:
            stmt = (
                select(TodoItem)
                .where(
                    TodoItem.user_id == UUID(state["user_id"]),
                    TodoItem.status == "pending",
                    TodoItem.used_in_opening == True,
                )
                .order_by(TodoItem.created_at.desc())
            )
            todo = session.exec(stmt).first()

        if not todo:
            return {"todo_status": "NONE", "active_todo": ""}

        prompt = TODO_UPDATE_PROMPT.format(
            todo=todo.text,
            message=state["user_input"],
        )
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        result = strip_think_tags(resp.content).strip().upper()

        if result in ("DONE", "DISMISSED"):
            with get_session() as session:
                db_todo = session.get(TodoItem, todo.id)
                db_todo.status = "done" if result == "DONE" else "dismissed"
                session.add(db_todo)
                session.commit()
            print(f"\n[todo updated] {todo.text} -> {db_todo.status}")

        return {"todo_status": result, "active_todo": todo.text}

    except Exception as e:
        print(f"\n[todo node error] {e}")
        return {"todo_status": "NONE", "active_todo": ""}
