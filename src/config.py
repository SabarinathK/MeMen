import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mem0 config — ChromaDB vector store
mem0_config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "mental_health_ltm",
            "path": os.path.join(BASE_DIR, "chroma_db"),
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

DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'mentra.db')}"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 24 hours
