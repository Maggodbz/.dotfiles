"""Custom Textual widgets for the Kaya TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Top bar showing model, title, and context info."""

    model_name: reactive[str] = reactive("loading...")
    context_info: reactive[str] = reactive("")
    status: reactive[str] = reactive("OFFLINE")

    def compose(self) -> ComposeResult:
        yield Static(id="status-model")
        yield Static(id="status-title")
        yield Static(id="status-info")

    def watch_model_name(self, value: str) -> None:
        try:
            self.query_one("#status-model", Static).update(f"◈ {value}")
        except Exception:
            pass

    def watch_status(self, value: str) -> None:
        try:
            color = "green" if value == "ONLINE" else "yellow"
            self.query_one("#status-title", Static).update(
                f"[bold]◆ Kaya ◆[/]  [{color}]● {value}[/]"
            )
        except Exception:
            pass

    def watch_context_info(self, value: str) -> None:
        try:
            self.query_one("#status-info", Static).update(value)
        except Exception:
            pass


class ChatMessage(Static):
    """A single message in the chat log."""

    def __init__(self, content: str, role: str = "assistant", **kwargs) -> None:
        prefix = "▶ " if role == "user" else ""
        css_class = "user-msg" if role == "user" else "assistant-msg"
        super().__init__(f"{prefix}{content}", classes=css_class, **kwargs)


class ThinkingIndicator(Static):
    """Pulsing thinking indicator."""

    def __init__(self, **kwargs) -> None:
        super().__init__("◌ thinking...", classes="thinking-msg", **kwargs)


class StreamingMessage(Static):
    """A message that gets tokens appended as they stream in."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", classes="assistant-msg", **kwargs)
        self._tokens: list[str] = []

    def append_token(self, token: str) -> None:
        self._tokens.append(token)
        self.update("".join(self._tokens))

    @property
    def full_text(self) -> str:
        return "".join(self._tokens)
