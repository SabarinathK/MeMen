import asyncio
from src.agent.state import ChatState
from src.agent.settings import memory_client
from src.database import get_session
from src.models import UserMemorySchema
from typing import Optional


def _sync_fetch_macro_profile(user_id_str: str) -> Optional[dict]:
    """
    Synchronous helper executed inside a thread-pool via asyncio.to_thread.
    Atomically retrieves the structured user identity profile from SQLite.
    """
    with get_session() as session:
        profile = session.get(UserMemorySchema, user_id_str)
        return profile.model_dump() if profile else None


async def memory_node(state: ChatState) -> dict:
    """
    Hybrid Retrieval Layer: Combines Mem0 vector search blocks with
    relational database macro profile elements asynchronously.
    """
    try:
        # 1. Prepare the episodic micro-facts task from Mem0 vector space
        records_task = asyncio.to_thread(
            memory_client.search,
            query=state["user_input"],
            filters={"user_id": state["user_id"]},
            top_k=3,
        )

        profile_task = asyncio.to_thread(_sync_fetch_macro_profile, state["user_id"])

        # 3. CRITICAL CHANGE HERE: Fire both tasks concurrently using asyncio.gather
        # This executes the two independent network/disk I/O operations at the same time
        records, profile_data = await asyncio.gather(records_task, profile_task)

        # 4. Extract out individual memory strings from Mem0 payload structure
        memories = (
            [item["memory"] for item in records.get("results", [])]
            if isinstance(records, dict)
            else []
        )

        return {"relevant_memories": memories, "structured_profile": profile_data}
    except Exception as e:
        print(f"[FAILURE BOUNDARY] Hybrid memory node search failed: {e}")
        return {"relevant_memories": [], "structured_profile": None}
