from src.agent.state import ChatState


async def sync_barrier(state: ChatState) -> dict:
    """
    Waits for memory_node, todo_node, and emotion_node to all finish.
    Validates that none wrote None — logs a warning if they did but
    fills a safe default so response_node never crashes.
    """
    memories = state.get("relevant_memories")
    emotion = state.get("emotion")
    todo_status = state.get("todo_status")

    if memories is None:
        print(
            "[sync_barrier] WARN: relevant_memories is None — memory_node may have failed"
        )
        memories = []

    if emotion is None:
        print("[sync_barrier] WARN: emotion is None — emotion_node may have failed")
        emotion = "neutral"

    if todo_status is None:
        print("[sync_barrier] WARN: todo_status is None — todo_node may have failed")
        todo_status = "NONE"

    return {
        "relevant_memories": memories,
        "emotion": emotion,
        "todo_status": todo_status,
    }
