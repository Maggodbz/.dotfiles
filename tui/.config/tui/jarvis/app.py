"""Jarvis TUI application — 3-panel Textual interface with streaming and interactive commands."""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static
from textual.worker import Worker, get_current_worker

from . import agent, executor
from .agent import OLLAMA_URL
from .widgets import (
    ChatMessage,
    CommandBlock,
    StatusBar,
    StreamingMessage,
    TerminalLine,
    ThinkingIndicator,
)


class JarvisApp(App):
    CSS_PATH = "jarvis.tcss"
    TITLE = "J.A.R.V.I.S"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.conv = agent.Conversation()
        self._pending_steps: list[dict] = []
        self._step_num = 0
        self._total_steps = 0
        self._current_block: CommandBlock | None = None
        self._streaming_widget: StreamingMessage | None = None

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-area"):
            with VerticalScroll(id="chat-scroll"):
                yield Static(id="chat-panel")
            with VerticalScroll(id="actions-scroll"):
                yield Static("[dim]No pending actions[/]", id="actions-panel")
        with VerticalScroll(id="terminal-scroll"):
            yield Static(id="terminal-panel")
        with Horizontal(id="input-bar"):
            yield Static("▶ ", id="input-prompt")
            yield Input(placeholder="/ for commands", id="input-field")

    def on_mount(self) -> None:
        self.query_one("#chat-scroll").border_title = "Chat"
        self.query_one("#actions-scroll").border_title = "Actions"
        self.query_one("#terminal-scroll").border_title = "Terminal"
        self.query_one("#input-field", Input).focus()

        status = self.query_one(StatusBar)
        status.model_name = self.conv.model
        status.status = "LOADING"

        self._log_terminal("Initializing Jarvis...", "info")
        self.run_worker(self._warmup_worker, thread=True, group="warmup")

    def _warmup_worker(self) -> None:
        if not agent.check_ollama():
            self.call_from_thread(self._log_terminal, "Ollama not reachable — run: ollama serve", "error")
            return
        self.call_from_thread(self._log_terminal, f"Loading {self.conv.model}...", "info")
        agent.warmup(self.conv)
        self.call_from_thread(self._on_model_ready)

    def _on_model_ready(self) -> None:
        status = self.query_one(StatusBar)
        status.status = "ONLINE"
        status.model_name = self.conv.model
        self._log_terminal(f"{self.conv.model} ready", "info")
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
                self._log_terminal(f"Context set to {self.conv.num_ctx}", "info")
            else:
                self._log_terminal(f"Context: {self.conv.num_ctx}. Usage: /ctx <number>", "info")
        elif verb == "/clear":
            self.conv.clear()
            chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
            for child in list(chat_scroll.children):
                if child.id != "chat-panel":
                    child.remove()
            self._clear_actions()
            self._log_terminal("Conversation cleared", "info")
            self._update_context_info()
        elif verb == "/help":
            self._add_chat("assistant",
                "/model          — select model\n"
                "/model <name>   — switch by name\n"
                "/ctx <N>        — set context size\n"
                "/clear          — reset conversation\n"
                "q               — quit"
            )
        else:
            self._log_terminal(f"Unknown command: {verb}", "error")

    def _handle_model_cmd(self, arg: str) -> None:
        models = agent.fetch_models()
        if arg:
            matches = [m for m in models if arg.lower() in m["name"].lower()]
            if not matches:
                self._log_terminal(f"No model matching '{arg}'", "error")
                return
            chosen = matches[0]["name"]
        else:
            listing = "Available models:\n"
            for i, m in enumerate(models):
                active = " ●" if m["name"] == self.conv.model else ""
                listing += f"  {i+1}. {m['name']} ({m['params']}, {m['quant']}, {m['size_gb']:.1f}GB){active}\n"
            listing += "\nUse /model <name> to switch"
            self._add_chat("assistant", listing)
            return

        if chosen == self.conv.model:
            self._log_terminal(f"Already using {chosen}", "info")
            return

        self.conv.model = chosen
        status = self.query_one(StatusBar)
        status.status = "LOADING"
        status.model_name = chosen
        self._log_terminal(f"Switching to {chosen}...", "info")
        self.run_worker(self._warmup_worker, thread=True, group="warmup")

    # ── Agent loop ───────────────────────────────────────────────

    def _run_agent(self) -> None:
        self.query_one("#input-field", Input).disabled = True
        self.run_worker(self._stream_response, thread=True, group="agent")

    def _stream_response(self) -> None:
        worker = get_current_worker()
        self.call_from_thread(self._show_thinking)

        tokens: list[str] = []
        reply_streaming = False
        reply_buffer: list[str] = []

        for tok in agent.stream_chat(self.conv):
            if worker.is_cancelled:
                return
            tokens.append(tok)
            collected = "".join(tokens)

            if not reply_streaming:
                marker = '"reply":'
                pos = collected.find(marker)
                if pos >= 0:
                    after = collected[pos + len(marker):].lstrip()
                    if after.startswith('"'):
                        reply_streaming = True
                        self.call_from_thread(self._start_reply_stream)
                        tail = after[1:]
                        if tail:
                            cleaned = self._unescape_partial(tail)
                            reply_buffer.append(cleaned)
                            self.call_from_thread(self._append_reply_token, cleaned)
            elif reply_streaming:
                cleaned = self._unescape_partial(tok)
                if '"' in tok:
                    end = tok.find('"')
                    before_quote = self._unescape_partial(tok[:end])
                    if before_quote:
                        reply_buffer.append(before_quote)
                        self.call_from_thread(self._append_reply_token, before_quote)
                    reply_streaming = False
                else:
                    reply_buffer.append(cleaned)
                    self.call_from_thread(self._append_reply_token, cleaned)

        full_text = "".join(tokens)
        self.conv.add_assistant(full_text)
        self.call_from_thread(self._finalize_response, full_text)

    @staticmethod
    def _unescape_partial(s: str) -> str:
        return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

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

    def _finalize_response(self, raw: str) -> None:
        for t in self.query_one("#chat-scroll", VerticalScroll).query(ThinkingIndicator):
            t.remove()

        result = agent.parse_response(raw)
        plan = result.get("plan", [])
        reply = result.get("reply", "")

        if self._streaming_widget:
            streamed = self._streaming_widget.full_text.strip()
            self._streaming_widget.remove()
            self._streaming_widget = None
            if not streamed and reply:
                self._add_chat("assistant", reply)
        elif reply:
            self._add_chat("assistant", reply)

        self._update_context_info()

        if plan:
            self._start_plan(plan)
        else:
            self.query_one("#input-field", Input).disabled = False
            self.query_one("#input-field", Input).focus()

    # ── Plan execution ───────────────────────────────────────────

    def _start_plan(self, plan: list[dict]) -> None:
        self._pending_steps = list(plan)
        self._step_num = 0
        self._total_steps = len(plan)
        self._clear_actions()
        self._execute_next_step()

    def _execute_next_step(self) -> None:
        if not self._pending_steps:
            self._plan_finished()
            return

        if self._step_num >= agent.MAX_STEPS:
            self._add_chat("assistant", "Reached max steps. Use /clear to reset.")
            self._plan_finished()
            return

        step = self._pending_steps.pop(0)
        self._step_num += 1
        cmd = step.get("cmd", "")
        msg = step.get("msg", "")

        if not cmd:
            self._execute_next_step()
            return

        auto = executor.is_safe(cmd)
        block = CommandBlock(
            cmd=cmd, description=msg,
            step=self._step_num, total=self._total_steps,
            auto_run=auto,
        )
        self._current_block = block

        actions_scroll = self.query_one("#actions-scroll", VerticalScroll)
        placeholder = actions_scroll.query_one("#actions-panel", Static)
        placeholder.update("")
        actions_scroll.mount(block)
        actions_scroll.scroll_end(animate=False)

        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        chat_scroll.mount(ChatMessage(
            f"[bold]▸ [{self._step_num}/{self._total_steps}][/] {msg}\n  [dim]{cmd}[/]",
            role="assistant",
        ))
        chat_scroll.scroll_end(animate=False)

    def on_command_block_approved(self, event: CommandBlock.Approved) -> None:
        block = event.block
        block.mark_running()
        self._log_terminal(block.cmd)
        self.run_worker(
            lambda: self._execute_cmd_worker(block),
            thread=True, group="exec",
        )

    def on_command_block_skipped(self, event: CommandBlock.Skipped) -> None:
        block = event.block
        block.mark_skipped()
        self._log_terminal(f"Skipped: {block.cmd}", "info")
        self._feed_step_result(block.cmd, True, "[skipped by user]")

    def _execute_cmd_worker(self, block: CommandBlock) -> None:
        ok, output = executor.run(block.cmd)
        self.call_from_thread(self._on_cmd_done, block, ok, output)

    def _on_cmd_done(self, block: CommandBlock, ok: bool, output: str) -> None:
        if ok:
            block.mark_success(output)
            self._log_terminal(output if output else "✓ done")
        else:
            block.mark_failed(output)
            self._log_terminal(output if output else "✗ failed", "error")

        self._feed_step_result(block.cmd, ok, output)

    def _feed_step_result(self, cmd: str, ok: bool, output: str) -> None:
        status = "exit 0" if ok else "exit non-zero"
        if output and output != "[skipped by user]":
            feedback = f"[Step {self._step_num} ({status})]: {cmd}\nOutput:\n{output}"
        elif ok:
            feedback = (
                f"[Step {self._step_num} ({status})]: {cmd}\n"
                "Command succeeded with no output. If this was a search, "
                "it means NO RESULTS FOUND. Do NOT retry the same command."
            )
        else:
            feedback = f"[Step {self._step_num} ({status})]: {cmd}"

        if self._pending_steps:
            feedback += f"\nRemaining: {json.dumps(self._pending_steps)}"

        self.conv.add_user(feedback)

        if ok and not output and self._pending_steps:
            self._execute_next_step()
            return

        self.run_worker(self._reevaluate_plan, thread=True, group="agent")

    def _reevaluate_plan(self) -> None:
        worker = get_current_worker()
        tokens: list[str] = []
        for tok in agent.stream_chat(self.conv):
            if worker.is_cancelled:
                return
            tokens.append(tok)

        raw = "".join(tokens)
        self.conv.add_assistant(raw)
        self.call_from_thread(self._apply_reevaluation, raw)

    def _apply_reevaluation(self, raw: str) -> None:
        result = agent.parse_response(raw)
        new_plan = result.get("plan", [])
        new_reply = result.get("reply", "")

        self._update_context_info()

        if new_plan and len(new_plan) == 1:
            prev_cmd = self._current_block.cmd if self._current_block else ""
            if new_plan[0].get("cmd", "").strip() == prev_cmd.strip():
                if new_reply:
                    self._add_chat("assistant", new_reply)
                self._plan_finished()
                return

        if new_plan:
            self._pending_steps = new_plan
            self._total_steps = self._step_num + len(new_plan)
            self._execute_next_step()
        else:
            if new_reply:
                self._add_chat("assistant", new_reply)
            self._plan_finished()

    def _plan_finished(self) -> None:
        self._pending_steps = []
        self._current_block = None
        self.query_one("#input-field", Input).disabled = False
        self.query_one("#input-field", Input).focus()

    # ── UI helpers ───────────────────────────────────────────────

    def _add_chat(self, role: str, content: str) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        msg = ChatMessage(content, role=role)
        chat_scroll.mount(msg)
        chat_scroll.scroll_end(animate=False)

    def _log_terminal(self, text: str, level: str = "normal") -> None:
        term_scroll = self.query_one("#terminal-scroll", VerticalScroll)
        line = TerminalLine(text, level=level)
        term_scroll.mount(line)
        term_scroll.scroll_end(animate=False)

    def _clear_actions(self) -> None:
        actions_scroll = self.query_one("#actions-scroll", VerticalScroll)
        for child in list(actions_scroll.children):
            if child.id != "actions-panel":
                child.remove()
        try:
            actions_scroll.query_one("#actions-panel", Static).update("[dim]No pending actions[/]")
        except Exception:
            pass

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

    def _unload_model(self) -> None:
        """Tell Ollama to unload the model on exit to free VRAM."""
        try:
            import urllib.request
            payload = json.dumps({"model": self.conv.model, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate", data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

    def exit(self, *args, **kwargs) -> None:
        self._unload_model()
        super().exit(*args, **kwargs)
