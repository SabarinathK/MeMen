# MeMen Memory Agent

A prototype conversational memory assistant built with Streamlit, SQLModel, ChromaDB, and LangGraph.

## Setup

### Option A: Using `uv` (recommended for speed)

1. Install `uv`:
   ```bash
   pip install uv
   ```

2. Sync dependencies:
   ```bash
   uv sync
   ```

3. Activate the virtual environment:
   ```bash
   .venv\Scripts\activate
   ```

### Option B: Using pip

1. Create a Python 3.12+ virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   python -m pip install -e .
   ```

### Common Steps

3. Create a `.env` file in the project root with at least:
   ```env
   OPENROUTER_API_KEY=your_api_key_here
   ```

4. Optional environment variables:
   ```env
   REDIS_URL=redis://localhost:6379/0
   ENCRYPTION_KEY=your_secret_key
   JWT_SECRET=your_jwt_secret
   ```

5. Initialize the database:
   ```bash
   python src/database.py
   ```

6. Run the streamlit app:
   ```bash
   streamlit run src/agent/app.py
   ```

7. Login with the sample user:
   - username: `sabari`
   - password: `sabari`

## Design Decisions

### Why Parallel Graph Architecture?
The agent runs three independent workflows in parallel to maximize context richness while keeping latency bounded. Emotion, memory, and todo tracking are orthogonal concerns—parallelizing them ensures each has time to complete without blocking others. The sync barrier ensures all three signals are available before response generation.

### Why Emotion Detection?
Mental health support requires understanding emotional state. The emotion node provides a coarse label that downstream response generation can key off of. This allows responses to adapt tone (validation vs. solution-oriented) based on emotional context, not just semantic relevance.

### Why Mem0 + ChromaDB?
Mem0 handles high-level memory abstraction and extraction heuristics. ChromaDB provides fast semantic search with persistent storage. Together they decouple memory retrieval (fast, vector-based) from memory management (slower, LLM-based reasoning). This allows the agent to recall relevant context without the cost of re-reasoning about what matters.

### Why LangGraph?
LangGraph's graph semantics and built-in async support make the fan-out/fan-in topology explicit and easy to reason about. The sync barrier ensures deterministic ordering and prevents race conditions where a downstream node (e.g., response generation) proceeds before parallel nodes finish.

### Why Opening Messages?
New conversations start with context from prior sessions (long-term memories + pending todos). This creates continuity and signals to the user that the agent is stateful. Opening messages are generated synchronously on session creation to avoid stale context.

### Agent Pipeline
The core design is a **parallel fan-out, fan-in graph** that runs three independent workflows before generating a response:

1. **Memory Retrieval** (`memory_node`): Searches long-term memory (ChromaDB) for relevant context using semantic similarity.
2. **Emotion Detection** (`emotion_node`): Classifies the user's emotional state to inform response tone.
3. **Todo Tracking** (`todo_node`): Detects whether the user has completed or dismissed a pending action.

These three run in parallel, then converge at a sync barrier before the main response generation. The final response is generated with full context, followed by:
- **Follow-up Extraction** (`followup_node`): Extracts new commitments the user made for future sessions.
- **Memory Save** (`mem0_save_node`): Persists the conversation turn for long-term recall.

### Storage Layers
- **Vector store**: ChromaDB for semantic memory retrieval.
- **Relational store**: SQLite for user, conversation, message, and todo metadata.
- **Memory abstraction**: Mem0 for extraction and management of persistent facts.

### LLM Integration
- **Model**: OpenAI GPT-4o-mini via OpenRouter.
- **Embeddings**: Ollama (nomic-embed-text) for local embeddings.
- **Architecture**: All nodes are async to maximize parallelism.

## Key Files

- `src/agent/app.py` — Streamlit interface and chat orchestration.
- `src/database.py` — DB engine, schema creation, sample user creation.
- `src/models.py` — SQLModel table definitions.
- `src/agent/graph/graph.py` — LangGraph pipeline definition.
- `src/agent/node/` — individual graph nodes for memory, emotion, todo, response, follow-up, and memory save logic.
- `src/agent/settings.py` — LLM and memory client configuration.
- `src/config.py` — Mem0 config, ChromaDB paths, database URL, encryption keys.

## Known Limitations

### Agent & Memory
- **Brittleness of prompt-based classification**: Emotion detection, todo completion detection, and follow-up extraction are all LLM heuristics with no fallback validation. A single ambiguous user message can lead to incorrect emotion or missed commitments.
- **Memory relevance**: Semantic search in ChromaDB is limited to raw embedding similarity. The agent has no explicit ranking for *recency vs. relevance*, so older memories may surface equally to recent, important ones.
- **Repetition**: The agent lacks explicit tracking of what has been said. Over multiple turns, MeMen may repeat prior advice or memories without acknowledging prior context.
- **Latency on cold start**: The parallel fan-out requires three LLM calls (emotion, memory search via Mem0, todo detection). Each call adds ~500ms–1s latency. Total response time is often 2–3 seconds, creating perceptible delay.
- **No caching of memories**: Every turn re-queries ChromaDB and re-runs Mem0 search, even if the user asks a follow-up on the same topic.

### Conversation Quality
- **No explicit emotional support rules**: The emotion node only provides a label (anxiety, stress, etc.). The response node doesn't adapt its tone or offer proactive support strategies.
- **Shallow todo tracking**: Todos are extracted as raw strings. The agent cannot reason about dependencies (e.g., "I need to sleep before exercising") or priority.
- **No context refresh**: If a user hasn't spoken in days, the agent doesn't proactively re-surface stale context or check progress on old todos.

### Data & Privacy
- `content_encrypted` is stored as plain text; encryption is not implemented.
- No explicit consent enforcement for memory capture.
- The system logs all LLM calls and memory searches without redaction.

## 2-Week Roadmap (If Extra Time Was Given)

### Week 1: Latency & Memory Quality

**Priority 1: Reduce response latency**
- Implement request-level caching: cache memory retrieval and emotion classification for 2 minutes if the same user sends consecutive messages.
- Parallelize the LLM calls more aggressively: initiate all three classifier calls (*memory search*, *emotion detection*, *todo classification*) simultaneously without blocking on intermediate results. Target total latency: ~1 second (down from 2–3 seconds).
- Add a fast-path response for simple followups: if the user's message is flagged as a continuation (detected via embedding similarity to the prior message), skip expensive memory retrieval and re-use the prior context.

**Priority 2: Improve memory ranking**
- Add metadata-based ranking to memory retrieval: weight recent memories 3x heavier than older ones, and penalize duplicates (same fact repeated across multiple sessions).
- Implement a simple recency decay: memories older than 30 days are deprioritized unless explicitly high-relevance.
- Add memory deduplication in Mem0: when saving a new memory, check if it already exists (semantic similarity > 0.85) and update the timestamp instead of storing a duplicate.

**Priority 3: Prevent repetition & improve continuity**
- Build a turn history digest: maintain a sliding window of the last 3 responses the agent gave. Before generating a new response, check for semantic overlap with prior turns and flag if > 70% similar.
- Add explicit context carryover: embed a summary of the prior response into the system prompt for the next turn (e.g., "You just told the user about their goal to sleep earlier. Don't repeat this in your next response.").

### Week 2: Conversational Intelligence & Personalization

**Priority 4: Emotional support & tone adaptation**
- Upgrade the emotion node to output a *recommended response strategy* alongside the emotion label. Instead of just "anxiety," return `{ emotion: "anxiety", strategy: "validate_feelings + offer_grounding" }`.
- Adapt the response node's system prompt to include emotional support rules (e.g., "If the user is anxious, acknowledge their feelings before offering advice").
- Track emotion trends: if a user reports "anxious" or "stressed" 3+ times in the past week, flag this for proactive outreach (not yet implemented, but structured).

**Priority 5: Smarter todo tracking & proactive nudges**
- Enhance todo extraction to capture dependencies and context: instead of storing `"sleep earlier"`, store `{ text: "sleep earlier", context: "before_exercise", priority: "high" }`.
- Add a todo follow-up mechanism: if a user has marked a todo as "done," generate a celebratory response or use it as a confidence signal in future advice.
- Implement proactive memory refresh: at the start of a new session, if > 3 days have passed, automatically surface the top 2 recent todos and check their status.

**Priority 6: Session summarization & arc tracking**
- At the end of each conversation, generate a *session summary*: 1–2 sentences capturing the main topic, any breakthroughs, and follow-up actions. Store this as a high-priority memory.
- Track emotional arc: if the user's emotion goes from "stressed" → "hopeful" during a session, highlight this as positive progress and use it to reinforce coping strategies.
- Add optional manual reflection: let the user rate the session (helpful/neutral/unhelpful) and store this feedback to improve future agent responses.

### Success Metrics (End of 2 Weeks)
- **Latency**: Target < 1.5 seconds end-to-end response time (from < 2–3 seconds).
- **Memory accuracy**: Manual audit of 10 conversations shows < 10% repetition across turns.
- **Emotion tracking**: Agent correctly identifies and adapts to emotional cues in 90%+ of test cases.
- **Todo completion**: Users report todos are actionable and tracked; completion rate > 60%.

### Design Philosophy
This roadmap prioritizes **perceived responsiveness** (latency), **memory coherence** (no repetition, recency-aware), and **emotional intelligence** (adaptation, proactive support). The goal is for MeMen to feel like a thoughtful friend who remembers details, notices patterns, and adjusts their tone—not a chatbot that repeats itself or forgets what it just said.
