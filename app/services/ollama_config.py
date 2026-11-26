"""Start the bundled Ollama runtime and prepare the local vision fallback."""
from __future__ import annotations

# The model list is intentionally centralized so settings, UI and runtime stay aligned.
SUPPORTED_VISION_MODELS = (
    "qwen3-vl:4b",
    "qwen2.5-vl:7b",
    "llama3.2-vision:11b",
    "gemma3:4b",
    "qwen2.5-vl:32b",
)
DEFAULT_OLLAMA_MODEL = "qwen3-vl:4b"
OLLAMA_MODEL = DEFAULT_OLLAMA_MODEL


def normalize_ollama_model(model: str | None) -> str:
    """Keep older settings and unknown values backward compatible."""
    return model if model in SUPPORTED_VISION_MODELS else DEFAULT_OLLAMA_MODEL
