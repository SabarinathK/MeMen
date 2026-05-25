import os
from mem0 import Memory
from dotenv import load_dotenv

load_dotenv()
print(os.getenv("OPENROUTER_API_KEY"))

config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "test",
            "path": "db",
        },
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "openai/gpt-4o-mini",
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "openai_base_url": "https://openrouter.ai/api/v1",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {"model": "nomic-embed-text"},
    },
}

m = Memory.from_config(config)

messages = [
    {
        "role": "user",
        "content": "I'm planning to watch a movie tonight. Any recommendations?",
    },
    {
        "role": "assistant",
        "content": "How about thriller movies? They can be quite engaging.",
    },
    {
        "role": "user",
        "content": "I’m not a big fan of thriller movies but I love sci-fi movies.",
    },
    {
        "role": "assistant",
        "content": "Got it! I'll avoid thriller recommendations and suggest sci-fi movies in the future.",
    },
]

m.add(messages, user_id="alice", metadata={"category": "movies"})
