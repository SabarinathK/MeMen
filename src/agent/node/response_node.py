from src.agent.state import ChatState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.agent.settings import llm, strip_think_tags
from typing import Optional, Any


def build_system_prompt(memories: list, profile: Any, emotion: str) -> str:
    memory_block = "\n".join(f"- {m}" for m in memories) if memories else "- none"

    if profile:
        # Standardize input format: convert object instances to dictionary safely if needed
        p_dict = (
            profile
            if isinstance(profile, dict)
            else getattr(profile, "model_dump", lambda: {})()
        )
        if not p_dict and hasattr(profile, "__dict__"):
            p_dict = profile.__dict__

        # Extract preferences dictionary block safely
        prefs = p_dict.get("preferences") or {}
        if not isinstance(prefs, dict):
            prefs = getattr(prefs, "model_dump", lambda: {})()

        # Handle formatting for lists or arrays seamlessly
        raw_themes = p_dict.get("themes") or []
        themes_str = (
            ", ".join(raw_themes) if isinstance(raw_themes, list) else str(raw_themes)
        )

        profile_block = (
            f"Summary: {p_dict.get('profile_summary') or 'Not specified'}\n"
            f"Current Focus: {p_dict.get('current_focus') or 'Not specified'}\n"
            f"Themes Covered: {themes_str or 'None yet'}\n"
            f"Emotional Archetype: {p_dict.get('emotional_archetype') or 'Not specified'}\n"
            f"Communication Preference: {prefs.get('tone') or 'warm tone'}"
        )
    else:
        profile_block = "No high-level identity profile established yet."

    return f"""You are MeMen, a warm and empathetic mental wellness companion.

# USER CONTEXT STATE MAP
## CORE USER IDENTITY PROFILE (SQLite structured):
{profile_block}

## CONTEXTUAL SITUATIONAL FACTS (Mem0 episodic):
{memory_block}

## CURRENT TURN PARAMETERS:
- Detected Emotion: {emotion}

Rules:
- Speak naturally, warmly, and inspirationally like a caring friend.
- Keep response lengths between 2-4 sentences.
- Never explicitly mention system schemas or say 'based on your profile summary'.
"""


async def response_node(state: ChatState) -> dict:
    # Pass state["structured_profile"] right into your system prompt compiler
    system_prompt = build_system_prompt(
        state.get("relevant_memories") or [],
        state.get("structured_profile"),  # Safe fallback to None if missing
        state.get("emotion") or "neutral",
    )

    print(system_prompt)  # Debug: print the system prompt to verify its content

    payload = [SystemMessage(content=system_prompt)]
    payload.extend(state["history"][-8:])
    payload.append(HumanMessage(content=state["user_input"]))

    response = ""
    async for chunk in llm.astream(payload):
        content = chunk.content or ""
        response += content
        print(content, end="", flush=True)
    print()

    return {"reply": response}
