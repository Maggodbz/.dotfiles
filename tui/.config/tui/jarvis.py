#!/usr/bin/env python3
"""Jarvis - agentic LLM desktop assistant for Hyprland.

Plan-based agent: the model creates a plan, executes step by step,
and adjusts the plan after observing each result.

Commands:  /model  /ctx <N>  /clear  /help  q
"""

import json
import os
import select
import signal
import subprocess
import sys
import termios
import textwrap
import threading
import tty
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from theme import NORD, ignore_sigint

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("JARVIS_MODEL", "qwen2.5-coder:3b")
KEEP_ALIVE = -1
DEFAULT_CTX = 16384
MAX_STEPS = 10

SAFE_PREFIXES = (
    "ls", "cat", "head", "tail", "grep", "rg", "find", "wc", "file", "stat",
    "which", "echo", "date", "uptime", "df", "du", "ps", "free", "uname",
    "hyprctl clients", "hyprctl monitors", "hyprctl activewindow",
    "hyprctl workspaces", "hyprctl devices", "ollama list",
    "pip list", "pip show", "npm list", "pwd", "whoami", "hostname",
    "ip addr", "ip link", "ss ", "nmcli", "bluetoothctl info",
    "bluetoothctl devices", "pactl list", "wpctl status",
)

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
~/.config/hypr/scripts/toggle-overlay.sh netmetrics-overlay "wezterm start --class netmetrics-overlay -- /usr/bin/python3 ~/.config/tui/netmetrics-dashboard.py"
~/.config/hypr/scripts/toggle-overlay.sh bluetooth-overlay "wezterm start --class bluetooth-overlay -- /usr/bin/python3 ~/.config/tui/bluetooth-manager.py"
~/.config/hypr/scripts/toggle-overlay.sh keybindings-overlay "wezterm start --class keybindings-overlay -- /usr/bin/python3 ~/.config/tui/keybindings-display.py"

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

console = Console()
C = NORD


# ── State ────────────────────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.model = DEFAULT_MODEL
        self.num_ctx = DEFAULT_CTX
        self.models = [DEFAULT_MODEL]
        self.messages = []
        self.ready = False
        self.prompt_tokens = 0
        self.total_tokens = 0

state = State()
_model_ready = threading.Event()


# ── Keyboard ─────────────────────────────────────────────────────────────────

def read_key():
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return ""
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if select.select([sys.stdin], [], [], 30)[0]:
            return sys.stdin.read(1)
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── Ollama ───────────────────────────────────────────────────────────────────

def fetch_models():
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        data = json.loads(resp.read().decode())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return [DEFAULT_MODEL]


def fetch_models_detail():
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


def warmup_model():
    try:
        payload = json.dumps({
            "model": state.model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False, "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 4, "num_ctx": state.num_ctx},
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
    state.ready = True
    _model_ready.set()


def chat_ollama(messages):
    _model_ready.wait()
    payload = json.dumps({
        "model": state.model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages[-30:],
        "stream": True, "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.1, "num_predict": 1024, "num_ctx": state.num_ctx},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=payload,
        headers={"Content-Type": "application/json"},
    )

    tokens = []
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
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
                    tokens.append(tok)
                if chunk.get("done"):
                    state.prompt_tokens = chunk.get("prompt_eval_count", 0)
                    eval_count = chunk.get("eval_count", 0)
                    state.total_tokens = state.prompt_tokens + eval_count
                    break
    except urllib.error.URLError as exc:
        return json.dumps({"plan": [], "reply": f"Ollama unreachable: {exc.reason}"})
    except Exception as exc:
        return json.dumps({"plan": [], "reply": f"Error: {exc}"})

    return "".join(tokens)


def _extract_first_json(text):
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


def parse_response(text):
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
        # Handle old single-cmd format gracefully
        if "cmd" in obj and "plan" not in obj:
            cmd = obj["cmd"]
            msg = obj.get("msg", "")
            if cmd:
                plan = [{"cmd": cmd, "msg": msg}]
            reply = reply or msg
        return {"plan": plan if isinstance(plan, list) else [], "reply": reply}
    return {"plan": [], "reply": text[:500] if text else "No response."}


def execute(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        err = r.stderr.strip()
        combined = out if out else err
        return r.returncode == 0, combined[:2000]
    except subprocess.TimeoutExpired:
        return False, "Command timed out (30s). Try a narrower search or add -maxdepth."
    except Exception as exc:
        return False, str(exc)


def is_safe(cmd):
    stripped = cmd.strip()
    return any(stripped.startswith(p) for p in SAFE_PREFIXES)


def check_ollama():
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except Exception:
        return False


# ── Display ──────────────────────────────────────────────────────────────────

def show_header():
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)
    grid.add_row(
        Text("\u25c8 SYSTEM LINK", style=f"bold {C['accent']}"),
        Text("\u2591\u2592\u2593 J.A.R.V.I.S \u2593\u2592\u2591", style=f"bold {C['fg']}"),
        Text(datetime.now().strftime("%H:%M:%S") + " \u25c8", style=f"dim {C['fg_dim']}"),
    )
    status = Text("\u25cf ONLINE", style=f"bold {C['green']}") if state.ready else Text("\u25cb LOADING...", style=f"bold {C['yellow']}")
    pct = int(state.prompt_tokens / state.num_ctx * 100) if state.prompt_tokens else 0
    tok_color = C["green"] if pct < 60 else C["yellow"] if pct < 85 else C["red"]
    tok_str = f"{state.prompt_tokens}/{state.num_ctx}" if state.prompt_tokens else f"0/{state.num_ctx}"
    info = Text(f"\u25b8 {state.model}  ", style=f"dim {C['dim']}") + Text(f"[{tok_str} {pct}%]", style=f"dim {tok_color}") + Text(f"  msgs:{len(state.messages)//2}", style=f"dim {C['dim']}")
    bar = Table.grid(expand=True)
    bar.add_column(justify="left", ratio=1)
    bar.add_column(justify="right", ratio=1)
    bar.add_row(info, status)
    console.print(Panel(
        Group(grid, Text(""), bar),
        border_style=C["accent"],
        title=Text(" \u25c6 NEURAL INTERFACE \u25c6 ", style=f"bold {C['bg']} on {C['accent']}"),
        subtitle=Text(" /model /ctx /clear /help \u2502 q: quit ", style=f"dim {C['fg_dim']}"),
        padding=(0, 2), expand=True,
    ))
    console.print()


def show_thinking():
    console.print(Text("  \u25e6 thinking...", style=f"dim {C['fg_dim']}"), end="\r")


def clear_thinking():
    console.print(" " * 40, end="\r")


def show_plan(plan, updated=False):
    label = "PLAN UPDATED" if updated else "PLAN"
    style = C["yellow"] if updated else C["accent"]
    console.print(Text(f"  \u250c\u2500 {label} ", style=f"bold {style}") + Text("\u2500" * 40, style=f"dim {C['dim']}"))
    for i, step in enumerate(plan):
        num = Text(f"  \u2502 {i + 1}. ", style=f"bold {style}")
        msg = Text(step.get("msg", step.get("cmd", "")), style=C["fg_dim"])
        console.print(num + msg)
    console.print(Text("  \u2514" + "\u2500" * 44, style=f"dim {C['dim']}"))
    console.print()


def show_step(num, total, msg, cmd):
    console.print(Text(f"  \u25b8 [{num}/{total}] {msg}", style=f"bold {C['accent']}"))
    console.print(Text(f"    {cmd}", style=f"dim {C['dim']}"))


def show_output(ok, output):
    if not output:
        if ok:
            console.print(Text("    \u2713 done", style=f"dim {C['green']}"))
        else:
            console.print(Text("    \u2717 failed (no output)", style=f"dim {C['red']}"))
        console.print()
        return

    lines = output.split("\n")
    max_lines = 20
    truncated = len(lines) > max_lines
    display = lines[:max_lines]

    console.print(Text("    \u250c" + "\u2500" * 60, style=f"dim {C['dim']}"))
    for line in display:
        console.print(Text(f"    \u2502 {line[:100]}", style=C["fg_dim"]))
    if truncated:
        console.print(Text(f"    \u2502 ... ({len(lines) - max_lines} more lines)", style=f"dim {C['dim']}"))
    console.print(Text("    \u2514" + "\u2500" * 60, style=f"dim {C['dim']}"))
    console.print()


def show_context_bar():
    if not state.prompt_tokens:
        return
    pct = int(state.prompt_tokens / state.num_ctx * 100)
    tok_color = C["green"] if pct < 60 else C["yellow"] if pct < 85 else C["red"]
    bar_width = 20
    filled = int(bar_width * pct / 100)
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
    console.print(Text(f"  {bar} {state.prompt_tokens}/{state.num_ctx} ({pct}%)", style=f"dim {tok_color}"))
    console.print()


def show_reply(msg):
    if not msg:
        return
    console.print()
    for line in msg.split("\n"):
        console.print(Text(f"  {line}", style=C["fg"]))
    console.print()


def show_approval():
    console.print(Text("    run? [y/n] ", style=f"bold {C['yellow']}"), end="")


# ── Agent loop ───────────────────────────────────────────────────────────────

def agent_loop(user_input):
    state.messages.append({"role": "user", "content": user_input})
    console.print()

    show_thinking()
    raw = chat_ollama(state.messages)
    clear_thinking()

    result = parse_response(raw)
    plan = result.get("plan", [])
    reply = result.get("reply", "")
    state.messages.append({"role": "assistant", "content": raw})

    if not plan:
        show_reply(reply)
        show_context_bar()
        return

    if reply:
        console.print(Text(f"  \u25c7 {reply}", style=f"bold {C['accent']}"))
        console.print()

    show_plan(plan)
    total = len(plan)
    step_num = 0

    while plan and step_num < MAX_STEPS:
        step = plan.pop(0)
        step_num += 1
        cmd = step.get("cmd", "")
        msg = step.get("msg", "")

        show_step(step_num, total, msg, cmd)

        if not cmd:
            console.print(Text("    \u25b8 no command", style=f"dim {C['dim']}"))
            console.print()
            continue

        if is_safe(cmd):
            ok, output = execute(cmd)
            show_output(ok, output)
        else:
            show_approval()
            key = read_key()
            if key not in ("y", "\r", "\n"):
                console.print("n")
                console.print(Text("    \u25b8 skipped", style=f"dim {C['yellow']}"))
                console.print()
                ok, output = True, "[skipped by user]"
            else:
                console.print("y")
                ok, output = execute(cmd)
                show_output(ok, output)

        status = "exit 0" if ok else "exit non-zero"
        if output and output != "[skipped by user]":
            feedback = f"[Step {step_num} ({status})]: {cmd}\nOutput:\n{output}"
        elif ok:
            feedback = f"[Step {step_num} ({status})]: {cmd}\nCommand succeeded with no output. If this was a search, it means NO RESULTS FOUND. Do NOT retry the same command."
        else:
            feedback = f"[Step {step_num} ({status})]: {cmd}"

        if plan:
            feedback += f"\nRemaining: {json.dumps(plan)}"

        state.messages.append({"role": "user", "content": feedback})

        # Skip re-evaluation for trivial successes when more steps remain
        if ok and not output and plan:
            continue

        show_thinking()
        raw = chat_ollama(state.messages)
        clear_thinking()

        result = parse_response(raw)
        new_plan = result.get("plan", [])
        new_reply = result.get("reply", "")
        state.messages.append({"role": "assistant", "content": raw})

        # Loop detection: if the model returns the same cmd we just ran, stop
        if new_plan and len(new_plan) == 1 and new_plan[0].get("cmd", "").strip() == cmd.strip():
            show_reply(new_reply or "No results found.")
            show_context_bar()
            return

        if new_plan and new_plan != plan:
            plan = new_plan
            total = step_num + len(plan)
            show_plan(plan, updated=True)
        elif not new_plan:
            plan = []

        if not plan and new_reply:
            show_reply(new_reply)

    show_context_bar()
    if plan:
        show_reply("Reached max steps. Use /clear to reset.")


# ── Slash commands ───────────────────────────────────────────────────────────

def handle_slash(cmd):
    parts = cmd.strip().split(None, 1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb == "/model":
        details = fetch_models_detail()
        state.models = [d["name"] for d in details]

        if arg:
            matches = [d for d in details if arg.lower() in d["name"].lower()]
            if not matches:
                console.print(Text(f"  No model matching '{arg}'.", style=C["red"]))
                return
            chosen = matches[0]["name"]
        else:
            console.print()
            table = Table(
                show_header=True, header_style=f"bold {C['accent']}",
                border_style=C["dim"], expand=False, pad_edge=True,
                padding=(0, 1),
            )
            table.add_column("#", width=3, justify="center", style=f"bold {C['accent']}")
            table.add_column("MODEL", min_width=20, style=C["fg"])
            table.add_column("PARAMS", width=8, justify="center", style=C["fg_dim"])
            table.add_column("QUANT", width=8, justify="center", style=C["fg_dim"])
            table.add_column("SIZE", width=8, justify="right", style=C["fg_dim"])
            table.add_column("FAMILY", width=10, justify="center", style=f"dim {C['dim']}")
            table.add_column("", width=3, justify="center")

            for i, d in enumerate(details):
                active = Text("\u25cf", style=f"bold {C['green']}") if d["name"] == state.model else Text("")
                name_style = f"bold {C['fg']}" if d["name"] == state.model else C["fg"]
                table.add_row(
                    str(i + 1), Text(d["name"], style=name_style),
                    d["params"], d["quant"], f"{d['size_gb']:.1f} GB",
                    d["family"], active,
                )

            console.print(table)
            console.print(Text("  select [1-9] or any key to cancel", style=f"dim {C['fg_dim']}"))

            key = read_key()
            if not key or not key.isdigit() or int(key) < 1 or int(key) > len(details):
                return
            chosen = details[int(key) - 1]["name"]

        if chosen == state.model:
            console.print(Text(f"  already using {chosen}", style=f"dim {C['dim']}"))
            return

        state.model = chosen
        state.ready = False
        _model_ready.clear()
        console.print(Text(f"  \u25b8 loading {state.model}...", style=f"dim {C['yellow']}"))
        warmup_model()
        console.print(Text(f"  \u25b8 {state.model} ready", style=f"dim {C['green']}"))
        show_header()

    elif verb == "/ctx":
        if arg.isdigit():
            state.num_ctx = max(512, min(131072, int(arg)))
            console.print(Text(f"  context set to {state.num_ctx}", style=f"dim {C['green']}"))
        else:
            console.print(Text(f"  context: {state.num_ctx}. Usage: /ctx <number>", style=f"dim {C['fg_dim']}"))

    elif verb == "/clear":
        state.messages.clear()
        console.clear()
        show_header()
        console.print(Text("  context cleared", style=f"dim {C['green']}"))
        console.print()

    elif verb == "/help":
        console.print()
        console.print(Text("  /model          select model", style=C["fg_dim"]))
        console.print(Text("  /model <name>   switch by name", style=C["fg_dim"]))
        console.print(Text("  /ctx <N>        set context size", style=C["fg_dim"]))
        console.print(Text("  /clear          reset conversation", style=C["fg_dim"]))
        console.print(Text("  q               quit", style=C["fg_dim"]))
        console.print()
        console.print(Text("  Jarvis creates a plan, executes step by step,", style=f"dim {C['dim']}"))
        console.print(Text("  and adapts based on output. Safe commands auto-run.", style=f"dim {C['dim']}"))
        console.print()

    else:
        console.print(Text(f"  unknown: {verb}", style=C["red"]))


# ── Main ─────────────────────────────────────────────────────────────────────

def prompt_input():
    console.print(Text("  \u25b6 ", style=f"bold {C['accent']}"), end="")
    try:
        return input()
    except (EOFError, KeyboardInterrupt):
        return "q"


def main():
    ignore_sigint()
    console.clear()
    state.models = fetch_models()

    if not check_ollama():
        console.print(Text("  Ollama not reachable. Run: ollama serve", style=f"bold {C['red']}"))
        signal.pause()
        return

    show_header()
    console.print(Text(f"  loading {state.model}...", style=f"dim {C['yellow']}"))

    warmup_thread = threading.Thread(target=warmup_model, daemon=True)
    warmup_thread.start()
    warmup_thread.join()

    console.clear()
    show_header()

    while True:
        user_input = prompt_input()
        if not user_input or user_input.strip().lower() in ("q", "quit", "exit"):
            break
        stripped = user_input.strip()
        if stripped.startswith("/"):
            handle_slash(stripped)
            continue
        agent_loop(stripped)


if __name__ == "__main__":
    main()
