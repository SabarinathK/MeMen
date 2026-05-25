import os, re, json
from uuid import UUID
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from mem0 import Memory
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import redis as sync_redis
from MeMen.src.config import mem0_config, REDIS_URL, ENCRYPTION_KEY

# ── LLM client ────────────────────────────────────────────────────────────────

bot = ChatOpenAI(
    model="openai/gpt-4o-mini",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# ── Encryption ────────────────────────────────────────────────────────────────


def get_fernet() -> Fernet:
    key = ENCRYPTION_KEY
    if not key:
        # Dev fallback — generate and warn
        key = Fernet.generate_key()
        print(
            "[WARN] No ENCRYPTION_KEY set — using ephemeral key. Set in .env for production."
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_message(text: str) -> str:
    return get_fernet().encrypt(text.encode()).decode()


def decrypt_message(encrypted: str) -> str:
    return get_fernet().decrypt(encrypted.encode()).decode()


# ── Privacy layer ─────────────────────────────────────────────────────────────

PII_PATTERNS = [
    r"\b\d{10,12}\b",
    r"[a-zA-Z0-9._%+-]+@[\w.-]+\.[a-zA-Z]{2,}",
    r"\b(?:dr\.?|doctor|therapist|counselor)\s[A-Z][a-z]+\b",
    r"\b(?:Mr|Mrs|Ms|Dr)\.?\s[A-Z][a-z]+\b",
]
FORBIDDEN_CLINICAL = [
    "depression",
    "major depressive",
    "anxiety disorder",
    "ptsd",
    "bipolar",
    "schizophrenia",
    "ocd",
    "bpd",
    "borderline personality",
    "suicidal ideation",
    "eating disorder",
    "adhd",
]


def redact_pii(text: str) -> str:
    for p in PII_PATTERNS:
        text = re.sub(p, "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def validate_extracted(memory_text: str) -> tuple[bool, str]:
    low = memory_text.lower()
    for term in FORBIDDEN_CLINICAL:
        if term in low:
            return False, f"clinical term: {term}"
    for p in PII_PATTERNS:
        if re.search(p, memory_text, re.IGNORECASE):
            return False, "pii in extracted memory"
    return True, "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_json_list(text: str) -> list:
    text = strip_think(text).replace("```json", "").replace("```", "").strip()
    s, e = text.find("["), text.rfind("]") + 1
    if s != -1 and e > s:
        try:
            return json.loads(text[s:e])
        except Exception:
            return []
    return []


# ── Mem0 LTM ──────────────────────────────────────────────────────────────────


def get_mem0() -> Memory:
    return Memory.from_config(mem0_config)


def store_transcript_to_ltm(user_id: str, transcript: str) -> bool:
    """
    Privacy-safe ingestion:
    1. Redact PII
    2. Add to Mem0 (which extracts + stores in Chroma)
    """
    clean = redact_pii(transcript)
    m = get_mem0()
    m.add(clean, user_id=user_id)
    return True


def get_ltm_facts(user_id: str) -> list[str]:
    """Load all long-term memories for user."""
    m = get_mem0()
    records = m.get_all(filters={"user_id": user_id})
    if not records:
        return []
    raw = [item["memory"] for item in records.get("memories", [])]
    # Validate each — filter out anything with clinical terms
    clean = []
    for fact in raw:
        valid, _ = validate_extracted(fact)
        if valid:
            clean.append(fact)
    return clean


def search_ltm(user_id: str, query: str, top_k: int = 3) -> list[str]:
    """Semantic search against LTM for current message context."""
    m = get_mem0()
    results = m.search(query=query, filters={"user_id": user_id}, top_k=top_k)
    if not results:
        return []
    return [item["memory"] for item in results.get("results", [])]


def save_session_to_ltm(user_id: str, conversation_history: list[dict]) -> None:
    """Called at session end — save full conversation to Mem0."""
    session_text = "\n".join(
        [
            f"{'User' if m['role'] == 'user' else 'MeMen'}: {m['content']}"
            for m in conversation_history
        ]
    )
    clean = redact_pii(session_text)
    m = get_mem0()
    m.add(clean, user_id=user_id)


# ── Redis recall cache ────────────────────────────────────────────────────────


def _redis():
    return sync_redis.from_url(REDIS_URL, decode_responses=True)


RECALL_TTL = 3600  # 1 hour


def cache_recall(user_id: str, recall_block: str, todos: list[str]) -> None:
    r = _redis()
    r.setex(f"recall:{user_id}", RECALL_TTL, recall_block or "__empty__")
    r.setex(f"todos:{user_id}", RECALL_TTL, json.dumps(todos))


def get_cached_recall(user_id: str) -> tuple[str, list[str]]:
    r = _redis()
    recall = r.get(f"recall:{user_id}") or ""
    todos_raw = r.get(f"todos:{user_id}") or "[]"
    recall = "" if recall == "__empty__" else recall
    try:
        todos = json.loads(todos_raw)
    except Exception:
        todos = []
    return recall, todos


def invalidate_cache(user_id: str) -> None:
    r = _redis()
    r.delete(f"recall:{user_id}")
    r.delete(f"todos:{user_id}")


def build_and_cache_recall(user_id: str, todos: list[str]) -> str:
    """Build recall block from LTM facts and cache with todos."""
    facts = get_ltm_facts(user_id)
    if not facts:
        cache_recall(user_id, "", todos)
        return ""
    # Build a compact recall string
    lines = facts[:8]  # top 8 most recent facts
    recall = "\n".join(f"- {l}" for l in lines)
    cache_recall(user_id, recall, todos)
    return recall


# ── Opening message ───────────────────────────────────────────────────────────


def generate_opening_message(recall_block: str, todos: list[str]) -> str:
    if not recall_block and not todos:
        return "Hey — really glad you're here. How have things been lately?"

    # Path: only todos, no LTM yet
    if not recall_block and todos:
        prompt = f"""You are MeMen, a warm mental wellness companion starting a session.

Last time, this person committed to: "{todos[0]}"

Write a warm opening message (1-3 sentences) that:
- Asks about that specific thing naturally, like a caring friend who remembered
- Does NOT sound like a to-do list check
- Tone: warm text from someone thinking about them

Write only the opening message."""
        resp = bot.invoke([HumanMessage(content=prompt)])
        return strip_think(resp.content).strip()

    # Path: has LTM (with or without todos)
    todo_block = ""
    if todos:
        todo_block = "\n\nRecently committed to:\n" + "\n".join(f"- {t}" for t in todos)

    narrative_prompt = f"""Brief a mental wellness companion before a session.

Known about this person:
{recall_block}
{todo_block}

Write a 3-5 sentence flowing paragraph briefing.
- What kind of person, what they've been through, what they recently committed to
- No clinical labels, no session numbers, no bullet points
- Use "they" / "this person" """

    narrative = strip_think(
        bot.invoke([HumanMessage(content=narrative_prompt)]).content
    ).strip()

    todo_instruction = ""
    if todos:
        todo_instruction = f"\n- They committed to: {todos[0]} — ask about this naturally, not as a checkbox"

    opening_prompt = f"""You are MeMen, a warm mental wellness companion.

What you know:
{narrative}

Write the session-opening message.
Rules:
- 2-3 sentences only
- Caring friend who remembered — not a system
- Do NOT say "Last session you mentioned..."
- Do NOT list facts{todo_instruction}
- Do NOT use "journey", "safe space", "I'm here for you"
- ONE question max
- Tone: warm text from someone who was thinking about them

Write only the opening message."""

    resp = bot.invoke([HumanMessage(content=opening_prompt)])
    return strip_think(resp.content).strip()


# ── Todo extractor ────────────────────────────────────────────────────────────

TODO_EXTRACT_PROMPT = """Review this single mental wellness conversation turn.

User said: {user_message}
Bot replied: {bot_reply}

Extract ONLY concrete things the USER committed to or agreed to try.
Must be user's own words — not bot suggestions unless user agreed.

Return ONLY a JSON array of short strings. Max 2 items. [] if nothing.
No explanation. No markdown.
Example: ["try journaling once this week", "call old friend"]"""


def extract_todos_from_turn(user_msg: str, bot_reply: str) -> list[str]:
    try:
        resp = bot.invoke(
            [
                HumanMessage(
                    content=TODO_EXTRACT_PROMPT.format(
                        user_message=user_msg, bot_reply=bot_reply
                    )
                )
            ]
        )
        result = parse_json_list(resp.content)
        return [str(i).strip() for i in result if i]
    except Exception:
        return []


# ── STM compaction ────────────────────────────────────────────────────────────

COMPACTION_PROMPT = """Summarize these conversation turns into 3-4 warm, factual sentences.
Capture key emotional themes and what was discussed.
No clinical labels. No preamble.

Turns:
{turns}"""


def should_compact(messages: list[dict]) -> bool:
    if len(messages) < 8:
        return False
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 4 > 2500  # ~2500 token estimate


def compact_messages(messages: list[dict]) -> list[dict]:
    """Summarize old turns, keep last 4."""
    old = messages[:-4]
    recent = messages[-4:]
    turns_text = "\n".join(
        f"{'User' if m['role']=='user' else 'MeMen'}: {m['content']}" for m in old
    )
    try:
        resp = bot.invoke(
            [HumanMessage(content=COMPACTION_PROMPT.format(turns=turns_text))]
        )
        summary = strip_think(resp.content).strip()
    except Exception:
        summary = (
            "Earlier in this conversation, the user shared some personal challenges."
        )

    summary_msg = {
        "role": "system",
        "content": f"[Earlier conversation summary: {summary}]",
    }
    return [summary_msg] + recent
