from MeMen.src.agent.state import ChatState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from MeMen.src.agent.settings import llm, strip_think_tags


def build_system_prompt(memories: list, emotion: str) -> str:
    memory_block = "\n".join(f"- {m}" for m in memories) if memories else "- none"
    return f"""
You are MeMen.

Relevant memories:
{memory_block}

Detected emotion:
{emotion}

Rules:
- Human, warm, conversational, natural
- Never robotic
- Never directly repeat memories
- 2-4 sentences
"""


async def response_node(state: ChatState) -> dict:
    """
    FIX 2: By the time this runs, sync_barrier has already ensured
    relevant_memories, emotion, and todo_status are all set.
    The streaming loop fully completes before returning, so followup_node
    and mem0_save_node always receive a non-empty reply.
    """
    system_prompt = build_system_prompt(
        state["relevant_memories"],
        state["emotion"],
    )

    payload = [SystemMessage(content=system_prompt)]
    payload.extend(state["history"][-8:])
    payload.append(HumanMessage(content=state["user_input"]))

    response = ""
    print("\nMeMen: ", end="")

    async for chunk in llm.astream(payload):
        content = chunk.content or ""
        response += content
        print(content, end="", flush=True)

    print()

    # reply is fully assembled here before we return — guaranteed non-empty
    return {"reply": response}
