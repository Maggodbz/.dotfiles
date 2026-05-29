"""Custom Textual widgets for the Jarvis TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


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
                f"[bold]◆ J.A.R.V.I.S ◆[/]  [{color}]● {value}[/]"
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


class CommandBlock(Widget):
    """Interactive command block with run/skip actions."""

    class Approved(Message):
        def __init__(self, block: CommandBlock) -> None:
            super().__init__()
            self.block = block

    class Skipped(Message):
        def __init__(self, block: CommandBlock) -> None:
            super().__init__()
            self.block = block

    def __init__(
        self, cmd: str, description: str, step: int, total: int,
        auto_run: bool = False, **kwargs,
    ) -> None:
        super().__init__(classes="cmd-block pending", **kwargs)
        self.cmd = cmd
        self.description = description
        self.step = step
        self.total = total
        self.auto_run = auto_run
        self._output: str = ""

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]▸ [{self.step}/{self.total}] {self.description}[/]",
            classes="cmd-label",
        )
        yield Static(f"  {self.cmd}", classes="cmd-text")
        if not self.auto_run:
            with Horizontal(classes="cmd-actions"):
                yield Button("⏎ Run", id="run-cmd", classes="action-btn run-btn")
                yield Button("Skip", id="skip-cmd", classes="action-btn skip-btn")

    def on_mount(self) -> None:
        if self.auto_run:
            self.post_message(self.Approved(self))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "run-cmd":
            self.post_message(self.Approved(self))
        elif event.button.id == "skip-cmd":
            self.post_message(self.Skipped(self))

    def mark_running(self) -> None:
        self.remove_class("pending")
        self.add_class("running")
        self._hide_buttons()

    def mark_success(self, output: str = "") -> None:
        self.remove_class("pending", "running")
        self.add_class("success")
        self._output = output
        self._hide_buttons()
        if output:
            self.mount(Static(
                self._format_output(output, ok=True), classes="cmd-output",
            ))

    def mark_failed(self, output: str = "") -> None:
        self.remove_class("pending", "running")
        self.add_class("failed")
        self._output = output
        self._hide_buttons()
        if output:
            self.mount(Static(
                self._format_output(output, ok=False), classes="cmd-output",
            ))

    def mark_skipped(self) -> None:
        self.remove_class("pending")
        self.add_class("skipped")
        self._hide_buttons()
        self.mount(Static("[dim]skipped[/]", classes="cmd-output"))

    def _hide_buttons(self) -> None:
        for btn in self.query(Button):
            btn.remove()
        for row in self.query(".cmd-actions"):
            row.remove()

    @staticmethod
    def _format_output(output: str, ok: bool) -> str:
        lines = output.split("\n")
        max_lines = 15
        truncated = len(lines) > max_lines
        display = lines[:max_lines]
        color = "#A3BE8C" if ok else "#BF616A"
        parts = [f"[{color}]┌{'─' * 50}[/]"]
        for line in display:
            parts.append(f"[{color}]│[/] {line[:100]}")
        if truncated:
            parts.append(f"[dim]│ ... ({len(lines) - max_lines} more lines)[/]")
        parts.append(f"[{color}]└{'─' * 50}[/]")
        return "\n".join(parts)


class TerminalLine(Static):
    """A single line in the terminal output panel."""

    def __init__(self, content: str, level: str = "normal", **kwargs) -> None:
        css_class = "terminal-line"
        if level == "error":
            css_class += " error"
        elif level == "info":
            css_class += " info"
        prefix = {"normal": "$ ", "error": "✗ ", "info": "› "}[level]
        super().__init__(f"{prefix}{content}", classes=css_class, **kwargs)
