from __future__ import annotations

import uuid
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Footer, Header, Input, Markdown, RichLog, Static

from logger import logger
from run_registry import record_run_id
from settings import settings
from workflow import get_run_state_async, run_agent_workflow_async


def format_plan_markdown(plan: Any) -> str:
    if plan is None:
        return "No plan available."
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump()
    if not isinstance(plan, dict):
        return str(plan)

    lines: list[str] = []
    lines.append("# Plan Review")
    title = plan.get("title")
    if title:
        lines.append(f"- Title: {title}")
    locale = plan.get("locale")
    if locale:
        lines.append(f"- Locale: {locale}")
    lines.append(f"- Has enough context: {plan.get('has_enough_context')}")
    lines.append(f"- Finish plan: {plan.get('finish_plan')}")
    thought = plan.get("thought")
    if thought:
        lines.append("")
        lines.append("## Thought")
        lines.append(thought)
    lines.append("")
    lines.append("## Steps")
    steps = plan.get("steps") or []
    if not steps:
        lines.append("No steps found.")
        return "\n".join(lines)

    for idx, step in enumerate(steps, start=1):
        if hasattr(step, "model_dump"):
            step = step.model_dump()
        if not isinstance(step, dict):
            lines.append(f"{idx}. {step}")
            continue
        step_type = step.get("step_type", "unknown")
        title = step.get("title", "")
        target = step.get("target", "")
        description = step.get("description", "")
        stage = step.get("stage")
        depends_on = step.get("depends_on") or []
        lines.append(f"### {idx}. {title}")
        lines.append(f"- Type: `{step_type}`")
        if target:
            lines.append(f"- Target: `{target}`")
        if stage is not None:
            lines.append(f"- Stage: {stage}")
        if depends_on:
            deps = ", ".join(depends_on)
            lines.append(f"- Depends on: {deps}")
        if description:
            lines.append("")
            lines.append(description)
        lines.append("")

    return "\n".join(lines)


class PlanApprovalScreen(ModalScreen[bool]):
    def __init__(self, run_id: str, plan: Any) -> None:
        super().__init__()
        self._run_id = run_id
        self._plan = plan

    def compose(self) -> ComposeResult:
        plan_md = format_plan_markdown(self._plan)
        yield Vertical(
            Static(f"Plan approval for run: {self._run_id}", id="plan-title"),
            VerticalScroll(Markdown(plan_md), id="plan-body"),
            Input(placeholder="Comment (optional)", id="plan-comment"),
            Horizontal(
                Button("Approve", id="plan-approve", variant="success"),
                Button("Reject", id="plan-reject", variant="error"),
                Button("Cancel", id="plan-cancel"),
                id="plan-actions",
            ),
            id="plan-modal",
        )

    @on(Button.Pressed)
    async def handle_plan_action(self, event: Button.Pressed) -> None:
        if event.button.id == "plan-cancel":
            self.dismiss(False)
            return
        if event.button.id not in {"plan-approve", "plan-reject"}:
            return

        comment = self.query_one("#plan-comment", Input).value.strip() or None
        approved = event.button.id == "plan-approve"
        self.app.handle_plan_feedback(self._run_id, approved, comment)
        self.dismiss(True)


class VulnGraphApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        layout: horizontal;
        height: 1fr;
    }

    #sidebar {
        width: 28;
        padding: 1;
        border: round $primary;
        background: $surface;
    }

    #main {
        layout: vertical;
        width: 1fr;
        padding: 1;
    }

    #output-log {
        height: 1fr;
        border: round $primary;
    }

    #input-row {
        height: auto;
        margin-top: 1;
    }

    #query {
        width: 1fr;
    }

    #status {
        height: auto;
        margin-top: 1;
    }

    #debug-collapsible {
        margin-top: 1;
    }

    #debug-log {
        height: 12;
        border: round $secondary;
    }

    PlanApprovalScreen {
        align: center middle;
    }

    #plan-modal {
        width: 80%;
        height: 80%;
        padding: 1;
        border: round $primary;
        background: $panel;
        layout: vertical;
    }

    #plan-body {
        height: 1fr;
        border: round $secondary;
        padding: 1;
        margin-bottom: 1;
    }

    #plan-title {
        margin-bottom: 1;
    }

    #plan-actions {
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._current_run_id: str | None = None
        self._pending_run_id: str | None = None
        self._pending_plan: Any | None = None
        self._output_log_widget: RichLog | None = None
        self._debug_log_widget: RichLog | None = None
        self._status_widget: Static | None = None
        self._logger_handler_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Vertical(
                Static("Run Status", id="sidebar-title"),
                Static("Idle", id="sidebar-status"),
                Static("HITL: enabled" if settings.enable_hitl else "HITL: disabled", id="sidebar-hitl"),
                Button("Review Plan", id="review-plan", disabled=True),
                Button("Toggle Logs", id="toggle-logs"),
                id="sidebar",
            ),
            Vertical(
                Static("Model Output", id="output-title"),
                RichLog(id="output-log", highlight=True),
                Horizontal(
                    Input(placeholder="Describe the asset or CVE to analyze...", id="query"),
                    Button("Run", id="run"),
                    id="input-row",
                ),
                Static("Ready", id="status"),
                Collapsible(
                    RichLog(id="debug-log", highlight=True),
                    title="Logs",
                    id="debug-collapsible",
                    collapsed=True,
                ),
                id="main",
            ),
            id="body",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._output_log_widget = self.query_one("#output-log", RichLog)
        self._debug_log_widget = self.query_one("#debug-log", RichLog)
        self._status_widget = self.query_one("#status", Static)
        self._configure_logger()
        self._update_status("Ready")

    def _configure_logger(self) -> None:
        logger.remove()
        level = "DEBUG" if settings.debug else "INFO"
        self._logger_handler_id = logger.add(self._log_sink, level=level, colorize=False)

    def _log_sink(self, message: Any) -> None:
        text = str(message).rstrip()
        self._emit_debug(text)

    def _emit_output(self, renderable: Any) -> None:
        if not self._output_log_widget:
            return
        if isinstance(renderable, str):
            if "[red]" in renderable or "[green]" in renderable or "[yellow]" in renderable:
                renderable = Text.from_markup(renderable)
            else:
                renderable = Text(renderable)
        self.call_later(self._output_log_widget.write, renderable)

    def _emit_debug(self, renderable: Any) -> None:
        if not self._debug_log_widget:
            return
        if isinstance(renderable, str):
            renderable = Text(renderable)
        self.call_later(self._debug_log_widget.write, renderable)

    def _update_status(self, message: str) -> None:
        if not self._status_widget:
            return
        self._status_widget.update(message)
        sidebar_status = self.query_one("#sidebar-status", Static)
        sidebar_status.update(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.query_one("#run", Button).disabled = busy
        self.query_one("#query", Input).disabled = busy

    def _set_pending_plan(self, run_id: str | None, plan: Any | None) -> None:
        self._pending_run_id = run_id
        self._pending_plan = plan
        self.query_one("#review-plan", Button).disabled = plan is None

    @on(Input.Submitted, "#query")
    def handle_query_submit(self) -> None:
        self._start_run()

    @on(Button.Pressed, "#run")
    def handle_run_pressed(self) -> None:
        self._start_run()

    @on(Button.Pressed, "#review-plan")
    def handle_review_plan(self) -> None:
        if not self._pending_run_id or self._pending_plan is None:
            return
        self.push_screen(PlanApprovalScreen(self._pending_run_id, self._pending_plan))

    @on(Button.Pressed, "#toggle-logs")
    def handle_toggle_logs(self) -> None:
        collapsible = self.query_one("#debug-collapsible", Collapsible)
        collapsible.collapsed = not collapsible.collapsed

    def _start_run(self) -> None:
        if self._busy:
            return
        query = self.query_one("#query", Input).value.strip()
        if not query:
            self._update_status("Enter a query to start.")
            return
        run_id = uuid.uuid4().hex
        self._current_run_id = run_id
        self._set_pending_plan(None, None)
        self.query_one("#query", Input).value = ""
        self._set_busy(True)
        self._update_status(f"Running {run_id}")
        self._emit_debug(f"Starting run {run_id}")
        self.run_worker(self._run_workflow(run_id, query), name=f"run-{run_id}")

    async def _run_workflow(self, run_id: str, query: str) -> None:
        try:
            await run_agent_workflow_async(
                user_input=query,
                run_id=run_id,
                debug=settings.debug,
                max_plan_iterations=settings.max_plan_iterations,
                max_step_num=settings.max_step_num,
                enable_background_investigation=settings.enable_background_investigation,
                enable_clarification=settings.enable_clarification,
                max_clarification_rounds=settings.max_clarification_rounds,
                event_sink=self._emit_output,
            )
            record_run_id(run_id, query)
            await self._maybe_prompt_plan(run_id)
        except Exception as exc:
            self._emit_debug(f"Run failed: {exc}")
            self._update_status("Run failed.")
            self._set_busy(False)

    async def _maybe_prompt_plan(self, run_id: str) -> None:
        state = await get_run_state_async(run_id)
        if not state:
            self._update_status("No state found for run.")
            self._set_busy(False)
            return
        if state.get("plan_review_status") == "pending":
            self._update_status("Waiting for plan approval.")
            plan = state.get("plan")
            self._set_pending_plan(run_id, plan)
            self.push_screen(PlanApprovalScreen(run_id, plan))
            return
        self._set_pending_plan(None, None)
        self._update_status("Run finished.")
        self._set_busy(False)

    def handle_plan_feedback(
        self,
        run_id: str,
        approved: bool,
        comment: str | None,
    ) -> None:
        self._update_status("Resuming with plan feedback.")
        self.run_worker(
            self._resume_with_feedback(run_id, approved, comment),
            name=f"resume-{run_id}",
        )

    async def _resume_with_feedback(
        self,
        run_id: str,
        approved: bool,
        comment: str | None,
    ) -> None:
        try:
            await run_agent_workflow_async(
                user_input="",
                run_id=run_id,
                debug=settings.debug,
                max_plan_iterations=settings.max_plan_iterations,
                max_step_num=settings.max_step_num,
                enable_background_investigation=settings.enable_background_investigation,
                enable_clarification=settings.enable_clarification,
                max_clarification_rounds=settings.max_clarification_rounds,
                resume_value={"approved": approved, "comment": comment},
                event_sink=self._emit_output,
            )
            await self._maybe_prompt_plan(run_id)
        except Exception as exc:
            self._emit_debug(f"Resume failed: {exc}")
            self._update_status("Resume failed.")
            self._set_busy(False)


def main() -> None:
    app = VulnGraphApp()
    app.run()


if __name__ == "__main__":
    main()
