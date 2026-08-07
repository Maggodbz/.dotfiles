"""Ollama API client with streaming and conversation state."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = (
    os.environ.get("KAYA_MODEL")
    or os.environ.get("JARVIS_MODEL", "gemma4:e2b")
)
KEEP_ALIVE = -1
DEFAULT_CTX = 4096
SYSTEM_PROMPT = """\
You are Kaya, Marco's concise and helpful local AI assistant.
Have a natural conversation and answer directly in plain text or Markdown.
Do not emit JSON, plans, shell commands for execution, or action requests.
You cannot operate the computer or inspect files; clearly say so when relevant.
"""


@dataclass
class Conversation:
    messages: list[dict] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    num_ctx: int = DEFAULT_CTX
    prompt_tokens: int = 0
    total_tokens: int = 0

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        self.messages.clear()
        self.prompt_tokens = 0
        self.total_tokens = 0

    @property
    def context_pct(self) -> int:
        if not self.prompt_tokens:
            return 0
        return int(self.prompt_tokens / self.num_ctx * 100)


# Models this process has asked Ollama to keep resident, so we can release
# exactly those on shutdown without touching models loaded by other clients.
_loaded_lock = threading.Lock()
_loaded_models: set[str] = set()


def mark_loaded(model: str) -> None:
    with _loaded_lock:
        _loaded_models.add(model)


def unload_model(model: str, timeout: float = 3.0) -> bool:
    """Drop a model from VRAM now by re-requesting it with keep_alive=0."""
    payload = json.dumps({"model": model, "keep_alive": 0}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False
    finally:
        with _loaded_lock:
            _loaded_models.discard(model)


def unload_all(timeout: float = 3.0) -> None:
    """Release every model this process loaded. Safe to call repeatedly."""
    with _loaded_lock:
        models = list(_loaded_models)
    for model in models:
        unload_model(model, timeout=timeout)


def fetch_models() -> list[dict]:
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        data = json.loads(resp.read().decode())
        result = []
        for m in data.get("models", []):
            d = m.get("details", {})
            result.append({
                "name": m["name"],
                "params": d.get("parameter_size", "?"),
                "quant": d.get("quantization_level", "?"),
                "family": d.get("family", "?"),
                "size_gb": m.get("size", 0) / (1024**3),
            })
        return result
    except Exception:
        return [{"name": DEFAULT_MODEL, "params": "?", "quant": "?", "family": "?", "size_gb": 0}]


def check_ollama() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def warmup(conv: Conversation) -> None:
    try:
        payload = json.dumps({
            "model": conv.model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False, "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 4, "num_ctx": conv.num_ctx},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        mark_loaded(conv.model)
        resp = urllib.request.urlopen(req, timeout=120)
        resp.read()
        resp.close()
    except Exception:
        pass


def stream_chat(conv: Conversation):
    """Yield tokens one by one from Ollama streaming API."""
    payload = json.dumps({
        "model": conv.model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + conv.messages[-30:],
        "stream": True, "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.1, "num_predict": 1024, "num_ctx": conv.num_ctx},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"},
    )

    mark_loaded(conv.model)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tok = chunk.get("message", {}).get("content", "")
                if tok:
                    yield tok
                if chunk.get("done"):
                    conv.prompt_tokens = chunk.get("prompt_eval_count", 0)
                    eval_count = chunk.get("eval_count", 0)
                    conv.total_tokens = conv.prompt_tokens + eval_count
    except urllib.error.URLError as exc:
        yield f"Ollama unreachable: {exc.reason}"
    except Exception as exc:
        yield f"Error: {exc}"


def chat_sync(conv: Conversation) -> str:
    return "".join(stream_chat(conv))
