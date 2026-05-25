import asyncio
from MeMen.src.agent.state import ChatState
from MeMen.src.agent.settings import memory_client


async def memory_node(state: ChatState) -> dict:
    try:
        records = await asyncio.to_thread(
            memory_client.search,
            query=state["user_input"],
            filters={"user_id": state["user_id"]},
            top_k=3,
        )
        memories = [item["memory"] for item in records.get("results", [])]
        return {"relevant_memories": memories}
    except Exception as e:
        print(f"\n[memory search error] {e}")
        return {"relevant_memories": []}
