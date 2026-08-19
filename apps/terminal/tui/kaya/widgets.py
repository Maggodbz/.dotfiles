"""Custom Textual widgets for the Kaya TUI.

Design rule: Kaya is a console, not a dashboard. Panels are quiet raised
surfaces on a near-black background; colour is reserved for meaning.
"""

from __future__ import annotations

import time
from datetime import datetime

from rich.markup import escape
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

TEXT = "#D9E2E8"
DIM = "#6F8190"
CYAN = "#66D9EF"
BLUE = "#4D8FC8"
AMBER = "#D9A75F"
GREEN = "#71C48D"
RED = "#D86F6F"


def _clock() -> str:
    return datetime.now().strftime("%H:%M")


class StatusBar(Widget):
    """Thin system strip: identity, model, context load, uptime."""

    model_name: reactive[str] = reactive("loading…")
    status: reactive[str] = reactive("LOADING")
    context_pct: reactive[float] = reactive(0.0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._started = time.monotonic()

    def compose(self) -> ComposeResult:
        yield Static(id="status-brand")
        yield Static(id="status-model")
        yield Static(id="status-context")
        yield Static(id="status-uptime")

    def on_mount(self) -> None:
        self._render_brand()
        self._render_model()
        self._render_context()
        self._render_uptime()
        self.set_interval(1.0, self._render_uptime)

    def watch_status(self, _: str) -> None:
        if self.is_mounted:
            self._render_brand()

    def watch_model_name(self, _: str) -> None:
        if self.is_mounted:
            self._render_model()

    def watch_context_pct(self, _: float) -> None:
        if self.is_mounted:
            self._render_context()

    def _render_brand(self) -> None:
        dot = GREEN if self.status == "ONLINE" else AMBER
        self.query_one("#status-brand", Static).update(
            f"[bold {CYAN}]K A Y A[/]   [{dot}]● {self.status}[/]"
        )

    def _render_model(self) -> None:
        self.query_one("#status-model", Static).update(
            f"[{DIM}]LOCAL[/]  [{TEXT}]{self.model_name}[/]"
        )

    def _render_context(self) -> None:
        pct = self.context_pct
        color = GREEN if pct < 60 else AMBER if pct < 85 else RED
        filled = round(pct / 100 * 8)
        bar = "█" * filled + "░" * (8 - filled)
        self.query_one("#status-context", Static).update(
            f"[{DIM}]CONTEXT[/]  [{color}]{pct:.1f}%[/] [{DIM}]{bar}[/]"
        )

    def _render_uptime(self) -> None:
        s = int(time.monotonic() - self._started)
        self.query_one("#status-uptime", Static).update(
            f"[{DIM}]UPTIME[/]  [{TEXT}]{s // 3600:02}:{s % 3600 // 60:02}:{s % 60:02}[/]"
        )


class FooterBar(Widget):
    """Bottom hint strip."""

    def compose(self) -> ComposeResult:
        yield Static(f"[{DIM}]/help  commands[/]", id="footer-left")
        yield Static(
            f"[{DIM}]^R talk   ·   ^B activity   ·   ^T memory   ·   ^L clear[/]",
            id="footer-center",
        )
        yield Static(f"[{DIM}]ESC quit[/]", id="footer-right")


class ChatMessage(Static):
    """One entry in Kaya's memory: a role header and the message body."""

    def __init__(self, content: str, role: str = "assistant", **kwargs) -> None:
        name = "You" if role == "user" else "Kaya"
        body_color = TEXT if role == "user" else "#B9C6CE"
        super().__init__(
            f"[bold {CYAN}]{name}[/] [{DIM}]{_clock()}[/]\n"
            f"[{body_color}]{escape(content)}[/]",
            classes="chat-msg",
            **kwargs,
        )


class StreamingMessage(Static):
    """A Kaya message that grows as tokens stream in."""

    def __init__(self, **kwargs) -> None:
        super().__init__("", classes="chat-msg", **kwargs)
        self._tokens: list[str] = []
        self._header = f"[bold {CYAN}]Kaya[/] [{DIM}]{_clock()}[/]"
        self.update(self._header)

    def append_token(self, token: str) -> None:
        self._tokens.append(token)
        self.update(f"{self._header}\n[#B9C6CE]{escape(self.full_text)}[/]")

    @property
    def full_text(self) -> str:
        return "".join(self._tokens)


class ThinkingIndicator(Static):
    """Pulsing thinking indicator."""

    def __init__(self, **kwargs) -> None:
        super().__init__(f"[{DIM}]◌ thinking…[/]", classes="thinking-msg", **kwargs)


class ActivityEvent(Static):
    """One entry in the activity ledger."""

    KINDS = {
        "observation": ("◇", AMBER),
        "action": ("◆", CYAN),
        "complete": ("✓", GREEN),
        "warning": ("!", RED),
    }

    def __init__(self, kind: str, title: str, detail: str = "", **kwargs) -> None:
        glyph, color = self.KINDS.get(kind, ("◇", DIM))
        stamp = datetime.now().strftime("%H:%M:%S")
        pad = " " * (len(stamp) + 1)
        lines = [
            f"[{DIM}]{stamp}[/] [{color}]{glyph} {kind.upper()}[/]",
            f"{pad}[{TEXT}]{escape(title)}[/]",
        ]
        if detail:
            lines.append(f"{pad}[{DIM}]└ {escape(detail)}[/]")
        super().__init__("\n".join(lines), classes="activity-event", **kwargs)
