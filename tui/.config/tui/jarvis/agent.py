"""Ollama API client with streaming, response parsing, and conversation state."""

from __future__ import annotations

import json
import os
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("JARVIS_MODEL", "gemma4:e2b")
KEEP_ALIVE = -1
DEFAULT_CTX = 4096
MAX_STEPS = 10

SYSTEM_PROMPT = textwrap.dedent("""\
You are Jarvis, a general-purpose agentic assistant on a Linux desktop (Hyprland/Wayland).
You can run ANY shell command, see its output, and continue acting.
You are NOT limited to Hyprland commands - you can search files, manage git repos, edit configs, etc.

Reply with EXACTLY ONE raw JSON object. No markdown, no backticks, no extra text.

FORMAT:
{"plan": [{"cmd": "...", "msg": "..."}], "reply": "..."}

- "plan": array of steps. Each has "cmd" (shell command) and "msg" (short description).
- "reply": brief overview of what you're about to do, OR the final answer.

AFTER EACH STEP you see output. Respond with REMAINING plan (adjusted if needed).
When ALL DONE: {"plan": [], "reply": "<final summary of what happened>"}
For CHAT only: {"plan": [], "reply": "<answer>"}

RULES:
- Always include both "plan" and "reply".
- If a step fails or returns no output, CHANGE the plan or finish. NEVER retry the same command.
- "reply" should describe intent BEFORE execution, or results AFTER.
- Use && to combine tightly coupled steps in one cmd.
- Prefer simple, standard commands (find, grep, ls, cat, etc.) for general tasks.
- Only use hyprctl for desktop/window management tasks.
- Each command runs in a NEW subprocess. "cd" alone has NO effect. Use full paths or combine: cd /path && ls
- SEARCHING FILES: use -iname (case-insensitive) and wildcards: find ~/Repos -maxdepth 4 -iname '*todo*'
- Use -maxdepth 3-4 on broad paths (~/) to avoid slow scans. Drop maxdepth on narrow paths.
- When a search finds nothing, try broader patterns or deeper maxdepth before giving up.
- USE PREVIOUS OUTPUT: if you listed a directory or read a file, use paths/info you saw to build the next command.
- When the user says "read that", "show me that", "open it", etc., look at prior output to find the file/path they mean.
- ALWAYS prefer running a command over giving a generic text answer. If the user asks about file contents, READ the file.

HYPRLAND COMMANDS:
hyprctl dispatch workspace <N>                          # switch to workspace
hyprctl dispatch exec <app>                             # launch app on current workspace
hyprctl dispatch exec [workspace <N> silent] <app>      # launch app on workspace N WITHOUT switching
hyprctl dispatch killactive                             # close focused window
hyprctl dispatch movefocus l|r|u|d                      # move focus
hyprctl dispatch fullscreen 0                           # toggle fullscreen
hyprctl dispatch togglefloating                         # toggle floating
hyprctl clients -j                                      # list all windows as JSON
hyprctl monitors -j                                     # list monitors as JSON

OVERLAYS (toggle-overlay.sh needs TWO arguments: name and launch command):
~/.config/hypr/scripts/toggle-overlay.sh persistent-term "wezterm start --class persistent-term"
~/.config/hypr/scripts/toggle-overlay.sh wofi "wofi --show drun --normal-window --width 1200 --height 700 --insensitive"
~/.config/hypr/scripts/toggle-overlay.sh yazi-overlay "wezterm start --class yazi-overlay -- bash -c 'yazi'"

AUDIO/MEDIA/SCREEN (run directly, NOT through hyprctl dispatch exec):
wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+|-
wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
brightnessctl s 10%+|-
hyprshot -m output|region
playerctl play-pause|next|previous

USER ENVIRONMENT:
Home: /home/marco
Repos: ~/Repos
Dotfiles: ~/Repos/.dotfiles (managed with GNU stow)
Shell: zsh
Editor: cursor (Cursor IDE)
Terminal: wezterm
Python: /usr/bin/python3
""")


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
        yield json.dumps({"plan": [], "reply": f"Ollama unreachable: {exc.reason}"})
    except Exception as exc:
        yield json.dumps({"plan": [], "reply": f"Error: {exc}"})


def chat_sync(conv: Conversation) -> str:
    return "".join(stream_chat(conv))


def _extract_first_json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_response(text: str) -> dict:
    text = text.strip()
    if "<think>" in text:
        end = text.find("</think>")
        if end >= 0:
            text = text[end + 8:].strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    obj = _extract_first_json(text)
    if obj and isinstance(obj, dict):
        plan = obj.get("plan", [])
        reply = obj.get("reply", "")
        if "cmd" in obj and "plan" not in obj:
            cmd = obj["cmd"]
            msg = obj.get("msg", "")
            if cmd:
                plan = [{"cmd": cmd, "msg": msg}]
            reply = reply or msg
        return {"plan": plan if isinstance(plan, list) else [], "reply": reply}
    return {"plan": [], "reply": text[:500] if text else "No response."}
