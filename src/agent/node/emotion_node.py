from MeMen.src.agent.state import ChatState
from MeMen.src.agent.settings import llm, strip_think_tags
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

EMOTION_PROMPT = """
Classify primary emotion.

Message:
"{message}"

Return ONLY one of:
anxiety
stress
burnout
sadness
hopeful
neutral
"""


async def emotion_node(state: ChatState) -> dict:
    try:
        resp = await llm.ainvoke(
            [HumanMessage(content=EMOTION_PROMPT.format(message=state["user_input"]))]
        )
        emotion = strip_think_tags(resp.content).strip().lower()
        return {"emotion": emotion}
    except Exception as e:
        print(f"\n[emotion node error] {e}")
        return {"emotion": "neutral"}
