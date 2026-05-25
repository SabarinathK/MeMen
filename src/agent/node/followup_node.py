from src.agent.state import ChatState
from src.agent.settings import llm, strip_think_tags
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import json
from src.database import get_session
from src.models import User, TodoItem
from uuid import UUID, uuid4
from sqlmodel import select

FOLLOWUP_PROMPT = """
Extract concrete commitments the user made.

User: {user}
Assistant: {assistant}

Return JSON array only.
Example: ["sleep earlier"]
Empty array if none.
"""


async def followup_node(state: ChatState) -> dict:
    """
    FIX 3: state["reply"] is guaranteed non-empty here because this node
    only runs after response_node completes (edge: response → followup).
    """
    try:
        prompt = FOLLOWUP_PROMPT.format(
            user=state["user_input"],
            assistant=state["reply"],
        )
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        text = strip_think_tags(resp.content)

        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1:
            return {}

        items = json.loads(text[start:end])
        if not items:
            return {}

        with get_session() as session:
            for item in items:
                existing = session.exec(
                    select(TodoItem).where(
                        TodoItem.user_id == UUID(state["user_id"]),
                        TodoItem.text == item,
                        TodoItem.status == "pending",
                    )
                ).first()
                if existing:
                    continue
                session.add(
                    TodoItem(
                        user_id=UUID(state["user_id"]),
                        conversation_id=UUID(state["conversation_id"]),
                        text=item,
                        status="pending",
                        used_in_opening=False,
                    )
                )
            session.commit()

        print(f"\n[tracker] saved todos -> {items}")
        return {}

    except Exception as e:
        print(f"\n[followup node error] {e}")
        return {}
