from typing import TypedDict, Optional


class ChatState(TypedDict):
    user_id: str
    conversation_id: str
    user_input: str
    history: list

    # Written by parallel nodes — Optional so absence is detectable
    relevant_memories: Optional[list]  # memory_node
    emotion: Optional[str]  # emotion_node
    todo_status: Optional[str]  # todo_node
    active_todo: Optional[str]
    structured_profile: Optional[dict]

    # Written by response_node — must be set before followup/mem0
    reply: Optional[str]
