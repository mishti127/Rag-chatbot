import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

INDEX_DATA_DIR = Path(os.environ.get("RAG_INDEX_DIR", PROJECT_ROOT / "data" / "pageindex"))
DEFAULT_WORKSPACE = "default"
API_HOST = os.environ.get("RAG_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("RAG_API_PORT", "8080"))


def _strip_or_empty(key: str) -> str:
    return (os.environ.get(key) or "").strip()


DEFAULT_OPENROUTER_MODEL = "google/gemini-2.5-flash"

_LEGACY_GEMINI_ALIASES: dict[str, str] = {
    "google/gemini-pro-latest": "google/gemini-2.5-flash",
    "~google/gemini-pro-latest": "google/gemini-2.5-flash",
}


def normalize_openrouter_model(raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return DEFAULT_OPENROUTER_MODEL
    if v.lower().startswith(("http://", "https://")):
        try:
            path = urlparse(v).path.strip("/")
            if path:
                v = path
        except ValueError:
            pass
    return _LEGACY_GEMINI_ALIASES.get(v, v)


OPENROUTER_API_KEY = _strip_or_empty("OPENROUTER_API_KEY") or _strip_or_empty("OPENAI_API_KEY")


def refresh_env_from_project_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=True)


def get_openrouter_api_key() -> str:
    return _strip_or_empty("OPENROUTER_API_KEY") or _strip_or_empty("OPENAI_API_KEY")


OPENROUTER_BASE_URL = (
    _strip_or_empty("OPENROUTER_BASE_URL")
    or _strip_or_empty("OPENAI_BASE_URL")
    or "https://openrouter.ai/api/v1"
)
OPENROUTER_MODEL = normalize_openrouter_model(
    _strip_or_empty("OPENROUTER_MODEL") or _strip_or_empty("OPENAI_MODEL")
)
OPENROUTER_HTTP_REFERER = _strip_or_empty("OPENROUTER_HTTP_REFERER") or None
OPENROUTER_APP_TITLE = _strip_or_empty("OPENROUTER_APP_TITLE") or "Vectorless RAG"

RAG_CONTEXT_MODE = "strict"
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "6"))
RAG_TEMPERATURE = float(os.environ.get("RAG_TEMPERATURE", "0.2"))
RAG_TREE_MAX_DEPTH = int(os.environ.get("RAG_TREE_MAX_DEPTH", "4"))
RAG_TREE_MAX_PAGES = int(os.environ.get("RAG_TREE_MAX_PAGES", "6"))

# Hierarchical summaries (ingestion)
RAG_SUMMARY_MAX_CHARS = int(os.environ.get("RAG_SUMMARY_MAX_CHARS", "320"))
RAG_SUMMARY_MAX_SOURCE_CHARS = int(os.environ.get("RAG_SUMMARY_MAX_SOURCE_CHARS", "12000"))
RAG_SUMMARY_SECTION_PAGES = int(os.environ.get("RAG_SUMMARY_SECTION_PAGES", "8"))

# Knowledge map
RAG_GRAPH_MAX_NODES = int(os.environ.get("RAG_GRAPH_MAX_NODES", "150"))
RAG_GRAPH_MAX_RELATED_EDGES = int(os.environ.get("RAG_GRAPH_MAX_RELATED_EDGES", "200"))
RAG_GRAPH_RELATED_MIN_SCORE = float(os.environ.get("RAG_GRAPH_RELATED_MIN_SCORE", "0.22"))

# Timeline extraction
RAG_TIMELINE_MAX_EVENTS = int(os.environ.get("RAG_TIMELINE_MAX_EVENTS", "500"))
RAG_MAX_QUERY_CHARS = int(os.environ.get("RAG_MAX_QUERY_CHARS", "4000"))

# Guardrails (document-restricted RAG)
RAG_GUARDRAILS_ENABLED = os.environ.get("RAG_GUARDRAILS_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
RAG_RETRIEVAL_MIN_SCORE = float(os.environ.get("RAG_RETRIEVAL_MIN_SCORE", "0.18"))
RAG_RETRIEVAL_MIN_PAGES = int(os.environ.get("RAG_RETRIEVAL_MIN_PAGES", "1"))
RAG_RESPONSE_MIN_CONTEXT_OVERLAP = float(os.environ.get("RAG_RESPONSE_MIN_CONTEXT_OVERLAP", "0.12"))
RAG_GUARDRAIL_BLOCK_INJECTION = os.environ.get("RAG_GUARDRAIL_BLOCK_INJECTION", "true").lower() in (
    "1",
    "true",
    "yes",
)
RAG_GUARDRAIL_BLOCK_JAILBREAK = os.environ.get("RAG_GUARDRAIL_BLOCK_JAILBREAK", "true").lower() in (
    "1",
    "true",
    "yes",
)
RAG_GUARDRAIL_LOG_BLOCKS = os.environ.get("RAG_GUARDRAIL_LOG_BLOCKS", "true").lower() in (
    "1",
    "true",
    "yes",
)
RAG_GUARDRAIL_LOG_PATH = os.environ.get(
    "RAG_GUARDRAIL_LOG_PATH",
    str(INDEX_DATA_DIR / "guardrails" / "blocked_queries.jsonl"),
)
RAG_ANSWER_MIN_CHARS = int(os.environ.get("RAG_ANSWER_MIN_CHARS", "500"))
RAG_ANSWER_MAX_CHARS = int(os.environ.get("RAG_ANSWER_MAX_CHARS", "1200"))

COLLECTION_NAME = os.environ.get("RAG_COLLECTION", DEFAULT_WORKSPACE)
CHROMA_PERSIST_DIR = PROJECT_ROOT / "data" / "chroma"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# Document compare
RAG_COMPARE_MAX_SECTIONS = int(os.environ.get("RAG_COMPARE_MAX_SECTIONS", "48"))
RAG_COMPARE_SECTION_CHARS = int(os.environ.get("RAG_COMPARE_SECTION_CHARS", "3500"))
RAG_COMPARE_EMBED_BATCH = int(os.environ.get("RAG_COMPARE_EMBED_BATCH", "24"))
RAG_COMPARE_SIM_MATCH = float(os.environ.get("RAG_COMPARE_SIM_MATCH", "0.82"))
RAG_COMPARE_SIM_CHANGED = float(os.environ.get("RAG_COMPARE_SIM_CHANGED", "0.55"))
OPENROUTER_EMBED_MODEL = _strip_or_empty("OPENROUTER_EMBED_MODEL") or "openai/text-embedding-3-small"

# Text-to-speech (Hugging Face Inference API)
HF_TOKEN = _strip_or_empty("HF_TOKEN") or _strip_or_empty("HUGGINGFACE_API_KEY")
RAG_TTS_MODEL = _strip_or_empty("RAG_TTS_MODEL") or "facebook/mms-tts-eng"
RAG_TTS_MAX_CHARS = int(os.environ.get("RAG_TTS_MAX_CHARS", "2500"))
# hf-inference = classic HF Inference API; fal-ai etc. need Inference Providers billing
RAG_TTS_PROVIDER = _strip_or_empty("RAG_TTS_PROVIDER") or "hf-inference"

# Speech-to-text (Hugging Face Inference API)
RAG_STT_MODEL = _strip_or_empty("RAG_STT_MODEL") or "openai/whisper-large-v3"
RAG_STT_PROVIDER = _strip_or_empty("RAG_STT_PROVIDER") or "hf-inference"
RAG_STT_MAX_BYTES = int(os.environ.get("RAG_STT_MAX_BYTES", str(25 * 1024 * 1024)))


def get_hf_token() -> str:
    return _strip_or_empty("HF_TOKEN") or _strip_or_empty("HUGGINGFACE_API_KEY")


RAG_HYBRID = False
RAG_HYBRID_OVERSAMPLE = 4
