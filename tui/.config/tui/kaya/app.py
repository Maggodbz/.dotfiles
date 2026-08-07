"""Kaya TUI application — streaming local-LLM chat with voice."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static
from textual.worker import get_current_worker

from . import agent
from .orb import Orb
from .voice import Voice
from .widgets import (
    ChatMessage,
    StatusBar,
    StreamingMessage,
    ThinkingIndicator,
)

HELP_TEXT = (
    "/model              — list Ollama models\n"
    "/model <name>       — switch LLM\n"
    "/voice              — voice status\n"
    "/voice on|off       — toggle speech\n"
    "/voice list         — list TTS voices\n"
    "/voice <name>       — switch TTS voice\n"
    "/ctx <N>            — set context size\n"
    "/clear              — reset conversation\n"
    "/status             — show current settings\n"
    "/help               — this help\n"
    "q                   — quit"
)


class KayaApp(App):
    CSS_PATH = "kaya.tcss"
    TITLE = "Kaya"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.conv = agent.Conversation()
        self._streaming_widget: StreamingMessage | None = None
        self.voice = Voice(on_level=self._on_audio_level, on_state=self._on_speaking)

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-area"):
            yield Orb(id="orb")
            with VerticalScroll(id="chat-scroll"):
                yield Static(id="chat-panel")
        with Horizontal(id="input-bar"):
            yield Static("▶ ", id="input-prompt")
            yield Input(
                placeholder="Message Kaya…  (/model /voice /help)",
                id="input-field",
            )

    def on_mount(self) -> None:
        self.query_one("#orb").border_title = "Kaya"
        self.query_one("#chat-scroll").border_title = "Transcript"
        self.query_one("#input-field", Input).focus()

        status = self.query_one(StatusBar)
        status.model_name = self.conv.model
        status.status = "LOADING"

        self._add_chat("assistant", "Loading local model…")
        self.run_worker(self._warmup_worker, thread=True, group="warmup")
        self.run_worker(self._voice_warmup_worker, thread=True, group="voice-warmup")

    def _voice_warmup_worker(self) -> None:
        if not self.voice.load():
            self.call_from_thread(
                self._add_chat, "assistant", f"Voice off — {self.voice.status}"
            )

    def _warmup_worker(self) -> None:
        if not agent.check_ollama():
            self.call_from_thread(
                self._add_chat,
                "assistant",
                "Ollama is not reachable. Start it with `ollama serve`.",
            )
            self.call_from_thread(self._set_input_enabled, True)
            return
        agent.warmup(self.conv)
        self.call_from_thread(self._on_model_ready)

    def _on_model_ready(self) -> None:
        status = self.query_one(StatusBar)
        status.status = "ONLINE"
        status.model_name = self.conv.model
        self._add_chat("assistant", f"{self.conv.model} is ready. Type `/help` for commands.")
        self._update_context_info()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        if text.lower() in ("q", "quit", "exit"):
            self.exit()
            return

        if text.startswith("/"):
            self._handle_slash(text)
            return

        self._add_chat("user", text)
        self.conv.add_user(text)
        self._run_agent()

    def _handle_slash(self, cmd: str) -> None:
        parts = cmd.split(None, 1)
        verb = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if verb == "/model":
            self._handle_model_cmd(arg)
        elif verb == "/ctx":
            if arg.isdigit():
                self.conv.num_ctx = max(512, min(131072, int(arg)))
                self._add_chat("assistant", f"Context set to {self.conv.num_ctx}.")
            else:
                self._add_chat(
                    "assistant",
                    f"Context: {self.conv.num_ctx}. Usage: `/ctx <number>`",
                )
        elif verb == "/clear":
            self.conv.clear()
            chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
            for child in list(chat_scroll.children):
                if child.id != "chat-panel":
                    child.remove()
            self._add_chat("assistant", "Conversation cleared.")
            self._update_context_info()
        elif verb == "/voice":
            self._handle_voice_cmd(arg)
        elif verb == "/status":
            voice_state = "on" if self.voice.enabled else "off"
            self._add_chat(
                "assistant",
                f"Model: {self.conv.model}\n"
                f"Context: {self.conv.num_ctx}\n"
                f"Voice: {voice_state} ({self.voice.voice_name})\n"
                f"Voice status: {self.voice.status}",
            )
        elif verb == "/help":
            self._add_chat("assistant", HELP_TEXT)
        else:
            self._add_chat(
                "assistant",
                f"Unknown command: `{verb}`\nType `/help` for available commands.",
            )

    def _handle_voice_cmd(self, arg: str) -> None:
        arg = arg.strip()
        lower = arg.lower()

        if not arg:
            state = "on" if self.voice.enabled else "off"
            self._add_chat(
                "assistant",
                f"Voice {state} — {self.voice.voice_name}\n{self.voice.status}\n"
                "Usage: `/voice on|off|list|<name>`",
            )
            return

        if lower in ("on", "off"):
            self.voice.enabled = lower == "on"
            if not self.voice.enabled:
                self.voice.stop()
            state = "on" if self.voice.enabled else "off"
            self._add_chat("assistant", f"Voice {state} — {self.voice.status}")
            return

        if lower in ("list", "voices"):
            voices = self.voice.list_voices()
            if not voices:
                self._add_chat("assistant", f"No voices available — {self.voice.status}")
                return
            current = self.voice.voice_name
            lines = ["Available voices:"]
            for name in voices:
                mark = " ●" if name == current else ""
                lines.append(f"  {name}{mark}")
            lines.append("\nUse `/voice <name>` to switch")
            self._add_chat("assistant", "\n".join(lines))
            return

        if self.voice.set_voice(arg):
            self._add_chat("assistant", f"Voice set to `{self.voice.voice_name}`.")
        else:
            self._add_chat(
                "assistant",
                f"No voice matching `{arg}`.\nUse `/voice list` to see options.",
            )

    def _handle_model_cmd(self, arg: str) -> None:
        models = agent.fetch_models()
        if arg:
            matches = [m for m in models if arg.lower() in m["name"].lower()]
            if not matches:
                self._add_chat("assistant", f"No model matching `{arg}`.")
                return
            chosen = matches[0]["name"]
        else:
            listing = "Available models:\n"
            for i, m in enumerate(models):
                active = " ●" if m["name"] == self.conv.model else ""
                listing += (
                    f"  {i+1}. {m['name']} "
                    f"({m['params']}, {m['quant']}, {m['size_gb']:.1f}GB){active}\n"
                )
            listing += "\nUse `/model <name>` to switch"
            self._add_chat("assistant", listing)
            return

        if chosen == self.conv.model:
            self._add_chat("assistant", f"Already using {chosen}.")
            return

        previous = self.conv.model
        self.conv.model = chosen
        status = self.query_one(StatusBar)
        status.status = "LOADING"
        status.model_name = chosen
        self._add_chat("assistant", f"Switching to {chosen}…")
        self.run_worker(
            lambda: self._swap_model_worker(previous), thread=True, group="warmup",
        )

    def _swap_model_worker(self, previous: str) -> None:
        agent.unload_model(previous)
        self._warmup_worker()

    # ── Streaming chat ───────────────────────────────────────────

    def _run_agent(self) -> None:
        self.voice.stop()
        self.query_one(Orb).set_state("thinking")
        self._set_input_enabled(False)
        self.run_worker(self._stream_response, thread=True, group="chat")

    def _stream_response(self) -> None:
        worker = get_current_worker()
        self.call_from_thread(self._show_thinking)
        tokens: list[str] = []

        for tok in agent.stream_chat(self.conv):
            if worker.is_cancelled:
                return
            if not tokens:
                self.call_from_thread(self._start_reply_stream)
            tokens.append(tok)
            self.call_from_thread(self._append_reply_token, tok)

        reply = "".join(tokens).strip()
        if reply:
            self.conv.add_assistant(reply)
        self.call_from_thread(self._finalize_response)

        if reply and not worker.is_cancelled:
            self.voice.speak(reply)

    def _show_thinking(self) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        indicator = ThinkingIndicator()
        chat_scroll.mount(indicator)
        chat_scroll.scroll_end(animate=False)

    def _start_reply_stream(self) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        for t in chat_scroll.query(ThinkingIndicator):
            t.remove()
        self._streaming_widget = StreamingMessage()
        chat_scroll.mount(self._streaming_widget)
        chat_scroll.scroll_end(animate=False)

    def _append_reply_token(self, token: str) -> None:
        if self._streaming_widget:
            self._streaming_widget.append_token(token)
            chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
            chat_scroll.scroll_end(animate=False)

    def _finalize_response(self) -> None:
        for t in self.query_one("#chat-scroll", VerticalScroll).query(ThinkingIndicator):
            t.remove()

        if self._streaming_widget:
            self._streaming_widget = None

        self.query_one(Orb).set_state("idle")
        self._update_context_info()
        self._set_input_enabled(True)

    # ── Voice callbacks (invoked from the audio thread) ──────────

    def _on_audio_level(self, level: float, bands) -> None:
        try:
            self.query_one(Orb).push_audio(level, bands)
        except Exception:
            pass

    def _on_speaking(self, speaking: bool) -> None:
        try:
            self.query_one(Orb).set_state("speaking" if speaking else "idle")
        except Exception:
            pass

    # ── UI helpers ───────────────────────────────────────────────

    def _add_chat(self, role: str, content: str) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        msg = ChatMessage(content, role=role)
        chat_scroll.mount(msg)
        chat_scroll.scroll_end(animate=False)

    def _set_input_enabled(self, enabled: bool) -> None:
        field = self.query_one("#input-field", Input)
        field.disabled = not enabled
        if enabled:
            field.focus()

    def _update_context_info(self) -> None:
        pct = self.conv.context_pct
        tok_str = f"{self.conv.prompt_tokens}/{self.conv.num_ctx}"
        status = self.query_one(StatusBar)
        if pct < 60:
            status.context_info = f"[#A3BE8C]{tok_str} ({pct}%)[/]"
        elif pct < 85:
            status.context_info = f"[#EBCB8B]{tok_str} ({pct}%)[/]"
        else:
            status.context_info = f"[#BF616A]{tok_str} ({pct}%)[/]"

    def action_clear(self) -> None:
        self._handle_slash("/clear")

    def on_unmount(self) -> None:
        self.voice.stop()
        agent.unload_all(timeout=2.0)

    def exit(self, *args, **kwargs) -> None:
        self.voice.stop()
        agent.unload_all(timeout=2.0)
        super().exit(*args, **kwargs)
