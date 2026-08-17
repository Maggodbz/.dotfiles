"""Kaya TUI application — streaming local-LLM chat with voice."""

from __future__ import annotations

import os
import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Static
from textual.worker import get_current_worker

from . import agent
from .cymatics import Cymatics
from .listen import Listener
from .render import Visualizer
from .voice import Voice
from .wave import Wave
from .widgets import (
    ActivityEvent,
    ChatMessage,
    FooterBar,
    StatusBar,
    StreamingMessage,
    ThinkingIndicator,
)

VISUALIZERS = {"wave": Wave, "plate": Cymatics}

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
    "/viz wave|plate     — switch visualiser\n"
    "/talk               — start/stop recording     (ctrl+r)\n"
    "/activity           — toggle activity panel    (ctrl+b)\n"
    "/memory             — toggle memory panel      (ctrl+t)\n"
    "/help               — this help\n"
    "q                   — quit"
)


class KayaApp(App):
    CSS_PATH = "kaya.tcss"
    TITLE = "Kaya"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("ctrl+r", "talk", "Talk"),
        ("ctrl+b", "toggle_activity", "Activity"),
        ("ctrl+t", "toggle_memory", "Memory"),
        ("escape", "escape", "Stop / Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.conv = agent.Conversation()
        self._streaming_widget: StreamingMessage | None = None
        self.voice = Voice(on_level=self._on_audio_level, on_state=self._on_speaking)
        self.listener = Listener(on_level=self._on_audio_level)

        self._recording = False
        self._rec_stop = threading.Event()
        self._rec_cancel = threading.Event()
        self._pulse_timer = None

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-area"):
            with Vertical(id="activity-panel", classes="side-panel"):
                with Horizontal(classes="panel-header"):
                    yield Static("ACTIVITY", classes="panel-title")
                    yield Static("^B", classes="panel-hint")
                yield VerticalScroll(id="activity-scroll")
                yield Static("0 events", id="activity-count", classes="panel-count")
            with Vertical(id="center-column"):
                yield Wave(id="viz")
                with Horizontal(id="input-bar"):
                    yield Static("›", id="input-prompt")
                    yield Input(placeholder="Message Kaya…", id="input-field")
                    yield Static("", id="listening-bar")
            with Vertical(id="memory-panel", classes="side-panel"):
                with Horizontal(classes="panel-header"):
                    yield Static("MEMORY", classes="panel-title")
                    yield Static("^T", classes="panel-hint")
                yield VerticalScroll(id="memory-scroll")
                yield Static("0 messages", id="memory-count", classes="panel-count")
        yield FooterBar(id="footer-bar")

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()

        status = self.query_one(StatusBar)
        status.model_name = self.conv.model
        status.status = "LOADING"

        self._add_event("action", "Loading model", self.conv.model)
        self.run_worker(self._warmup_worker, thread=True, group="warmup")
        self.run_worker(self._voice_warmup_worker, thread=True, group="voice-warmup")
        self.run_worker(self._listen_warmup_worker, thread=True, group="listen-warmup")

        if os.environ.get("KAYA_TALK") and self.listener.available:
            self.call_after_refresh(self.action_talk)

    def _voice_warmup_worker(self) -> None:
        if self.voice.load():
            self.call_from_thread(
                self._add_event, "complete", "Voice ready", self.voice.voice_name
            )
        else:
            self.call_from_thread(
                self._add_event, "warning", "Voice unavailable", self.voice.status
            )

    def _listen_warmup_worker(self) -> None:
        if self.listener.available and self.listener.load():
            self.call_from_thread(
                self._add_event, "complete", "Hearing ready", self.listener.model_size
            )

    def _warmup_worker(self) -> None:
        if not agent.check_ollama():
            self.call_from_thread(
                self._add_event, "warning", "Ollama unreachable", "start: ollama serve"
            )
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
        self._add_event("complete", "Model ready", self.conv.model)
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
                self._add_event("action", "Context resized", str(self.conv.num_ctx))
                self._add_chat("assistant", f"Context set to {self.conv.num_ctx}.")
            else:
                self._add_chat(
                    "assistant",
                    f"Context: {self.conv.num_ctx}. Usage: `/ctx <number>`",
                )
        elif verb == "/clear":
            self.conv.clear()
            self.query_one("#memory-scroll", VerticalScroll).remove_children()
            self._add_event("action", "Conversation cleared")
            self._update_context_info()
            # Removal is asynchronous; recount once the DOM has settled.
            self.call_after_refresh(self._update_counts)
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
        elif verb == "/viz":
            self._handle_viz_cmd(arg)
        elif verb == "/talk":
            self.action_talk()
        elif verb == "/activity":
            self.action_toggle_activity()
        elif verb == "/memory":
            self.action_toggle_memory()
        elif verb == "/help":
            self._add_chat("assistant", HELP_TEXT)
        else:
            self._add_chat(
                "assistant",
                f"Unknown command: `{verb}`\nType `/help` for available commands.",
            )

    def _handle_viz_cmd(self, arg: str) -> None:
        name = arg.strip().lower()
        current = self.query_one("#viz", Visualizer)
        if name not in VISUALIZERS:
            active = next(
                k for k, cls in VISUALIZERS.items() if isinstance(current, cls)
            )
            self._add_chat(
                "assistant",
                f"Visualiser: {active}\nUsage: `/viz {'|'.join(VISUALIZERS)}`",
            )
            return
        if isinstance(current, VISUALIZERS[name]):
            self._add_chat("assistant", f"Already showing {name}.")
            return
        self.run_worker(self._swap_viz(current, name))

    async def _swap_viz(self, current: Visualizer, name: str) -> None:
        state = current.state
        await current.remove()
        replacement = VISUALIZERS[name](id="viz")
        await self.query_one("#center-column", Vertical).mount(replacement, before=0)
        replacement.set_state(state)
        self._add_event("action", "Visualiser changed", name)

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
            self._add_event("action", f"Voice {state}")
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
            self._add_event("action", "Voice changed", self.voice.voice_name)
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
        self._add_event("action", "Switching model", chosen)
        self.run_worker(
            lambda: self._swap_model_worker(previous), thread=True, group="warmup",
        )

    def _swap_model_worker(self, previous: str) -> None:
        agent.unload_model(previous)
        self._warmup_worker()

    # ── Streaming chat ───────────────────────────────────────────

    def _run_agent(self) -> None:
        self.voice.stop()
        self.query_one("#viz", Visualizer).set_state("thinking")
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
        memory = self.query_one("#memory-scroll", VerticalScroll)
        memory.mount(ThinkingIndicator())
        memory.scroll_end(animate=False)

    def _start_reply_stream(self) -> None:
        memory = self.query_one("#memory-scroll", VerticalScroll)
        for t in memory.query(ThinkingIndicator):
            t.remove()
        self._streaming_widget = StreamingMessage()
        memory.mount(self._streaming_widget)
        memory.scroll_end(animate=False)

    def _append_reply_token(self, token: str) -> None:
        if self._streaming_widget:
            self._streaming_widget.append_token(token)
            self.query_one("#memory-scroll", VerticalScroll).scroll_end(animate=False)

    def _finalize_response(self) -> None:
        memory = self.query_one("#memory-scroll", VerticalScroll)
        for t in memory.query(ThinkingIndicator):
            t.remove()

        if self._streaming_widget:
            self._streaming_widget = None

        self._update_context_info()
        self._update_counts()

        # A turn finishing while the mic is open must not steal the visualiser
        # or focus a hidden input — recording owns both until it ends.
        if not self._recording:
            self.query_one("#viz", Visualizer).set_state("idle")
            self._set_input_enabled(True)

    # ── Voice callbacks (invoked from the audio thread) ──────────

    def _on_audio_level(self, level: float, bands) -> None:
        try:
            self.query_one("#viz", Visualizer).push_audio(level, bands)
        except Exception:
            pass

    def _on_speaking(self, speaking: bool) -> None:
        # While recording, the mic owns the visualiser. Muting playback fires
        # this callback, which would otherwise reset it out of "listening".
        if self._recording:
            return
        try:
            self.query_one("#viz", Visualizer).set_state(
                "speaking" if speaking else "idle"
            )
        except Exception:
            pass

    # ── UI helpers ───────────────────────────────────────────────

    def _add_chat(self, role: str, content: str) -> None:
        memory = self.query_one("#memory-scroll", VerticalScroll)
        if not memory.children:
            memory.mount(Static("Today", classes="section-label"))
        memory.mount(ChatMessage(content, role=role))
        memory.scroll_end(animate=False)
        self._update_counts()

    def _add_event(self, kind: str, title: str, detail: str = "") -> None:
        ledger = self.query_one("#activity-scroll", VerticalScroll)
        ledger.mount(ActivityEvent(kind, title, detail))
        ledger.scroll_end(animate=False)
        self._update_counts()

    def _update_counts(self) -> None:
        events = len(self.query_one("#activity-scroll").children)
        messages = len(
            self.query_one("#memory-scroll").query("ChatMessage, StreamingMessage")
        )
        self.query_one("#activity-count", Static).update(f"{events} events")
        self.query_one("#memory-count", Static).update(f"{messages} messages")

    def _set_input_enabled(self, enabled: bool) -> None:
        field = self.query_one("#input-field", Input)
        field.disabled = not enabled
        if enabled:
            field.focus()

    def _update_context_info(self) -> None:
        self.query_one(StatusBar).context_pct = float(self.conv.context_pct)

    def action_clear(self) -> None:
        self._handle_slash("/clear")

    # ── Talk mode (push Ctrl+R to start, again to stop) ──────────

    def action_talk(self) -> None:
        problem = self.listener._missing()
        if problem:
            self._add_chat("assistant", f"Talk mode unavailable — {problem}")
            return
        if self._recording:
            self._finish_recording()
        else:
            self._start_recording()

    def action_escape(self) -> None:
        if self._recording:
            self._cancel_recording()
        else:
            self.exit()

    def _start_recording(self) -> None:
        self._recording = True
        self._rec_stop.clear()
        self._rec_cancel.clear()
        # Cut her off the instant the mic opens — otherwise she talks into it.
        # This silences speech only; the reply itself keeps generating until
        # the second press decides to discard it.
        self.voice.mute()

        self.query_one("#input-prompt", Static).display = False
        self.query_one("#input-field", Input).display = False
        self.query_one("#listening-bar", Static).display = True

        self._pulse_timer = self.set_interval(0.5, self._pulse_listening)
        self._pulse_listening()
        self.query_one("#viz", Visualizer).set_state("listening")
        self._add_event("action", "Listening…")
        self.run_worker(self._record_worker, thread=True, group="record")

    def _finish_recording(self) -> None:
        """Second Ctrl+R: interrupt whatever Kaya is doing, then submit."""
        if not self._recording:
            return
        self._recording = False
        self._interrupt_generation()
        self._set_transcribing_ui()
        self._rec_stop.set()

    def _cancel_recording(self) -> None:
        """ESC: throw the recording away without submitting."""
        if not self._recording:
            return
        self._recording = False
        self._rec_cancel.set()
        self._rec_stop.set()
        self._end_recording_ui()
        self._add_event("observation", "Recording cancelled")

    def _record_worker(self) -> None:
        worker = get_current_worker()
        if not self.listener.load():
            self.call_from_thread(
                self._add_chat, "assistant",
                f"Talk mode unavailable — {self.listener.status}",
            )
            self.call_from_thread(self._end_recording_ui)
            return

        audio = self.listener.record_until(self._rec_stop, self._rec_cancel)
        if worker.is_cancelled or self._rec_cancel.is_set():
            return
        if audio is None:
            self.call_from_thread(self._end_recording_ui)
            self.call_from_thread(self._add_event, "observation", "Heard nothing")
            return

        text = self.listener.transcribe(audio).strip()
        if text:
            self.call_from_thread(self._submit_voice_text, text)
        else:
            self.call_from_thread(self._end_recording_ui)
            self.call_from_thread(self._add_event, "observation", "Heard nothing")

    def _interrupt_generation(self) -> None:
        """Stop any in-flight reply and speech so a new turn can take over."""
        self.voice.stop()
        try:
            self.workers.cancel_group(self, "chat")
        except Exception:
            pass
        self._streaming_widget = None
        for t in self.query_one("#memory-scroll", VerticalScroll).query(
            ThinkingIndicator
        ):
            t.remove()

    def _pulse_listening(self, dot: list[bool] = [True]) -> None:
        dot[0] = not dot[0]
        glyph = "●" if dot[0] else "○"
        self.query_one("#listening-bar", Static).update(
            f"[#D9A75F]{glyph} LISTENING[/]   "
            f"[#33475C]^R to send · ESC to cancel[/]"
        )

    def _set_transcribing_ui(self) -> None:
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None
        self.query_one("#viz", Visualizer).set_state("thinking")
        self.query_one("#listening-bar", Static).update("[#66D9EF]◌ transcribing…[/]")

    def _end_recording_ui(self) -> None:
        self.voice.unmute()
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None
        self.query_one("#listening-bar", Static).display = False
        self.query_one("#input-prompt", Static).display = True
        field = self.query_one("#input-field", Input)
        field.display = True
        field.focus()
        if self.query_one("#viz", Visualizer).state in ("listening", "thinking"):
            self.query_one("#viz", Visualizer).set_state("idle")

    def _submit_voice_text(self, text: str) -> None:
        self._end_recording_ui()
        self._add_chat("user", text)
        self.conv.add_user(text)
        self._run_agent()

    def _toggle_panel(self, selector: str) -> None:
        panel = self.query_one(selector)
        panel.display = not panel.display
        # Keep typing possible after a toggle; focus can land on the hidden panel.
        self.query_one("#input-field", Input).focus()

    def action_toggle_activity(self) -> None:
        self._toggle_panel("#activity-panel")

    def action_toggle_memory(self) -> None:
        self._toggle_panel("#memory-panel")

    def on_unmount(self) -> None:
        self._recording = False
        self._rec_cancel.set()
        self._rec_stop.set()
        self.voice.stop()
        agent.unload_all(timeout=2.0)

    def exit(self, *args, **kwargs) -> None:
        self._recording = False
        self._rec_cancel.set()
        self._rec_stop.set()
        self.voice.stop()
        agent.unload_all(timeout=2.0)
        super().exit(*args, **kwargs)
