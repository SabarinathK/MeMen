import asyncio
from src.agent.settings import memory_client

from src.agent.state import ChatState


async def mem0_save_node(state: ChatState) -> dict:
    """
    FIX 3 (same as followup): state["reply"] is guaranteed non-empty here.
    In the original graph this ran in parallel with followup from response_node
    which was fine for ordering — the bug was reply could be None if
    response_node hadn't fully finished when state was snapshotted.
    The sync_barrier + sequential edge fix eliminates that.
    """
    try:
        text = f"User: {state['user_input']}\nMeMen: {state['reply']}"
        await asyncio.to_thread(
            memory_client.add,
            text,
            user_id=state["user_id"],
        )
        return {}
    except Exception as e:
        print(f"\n[mem0 save error] {e}")
        return {}
