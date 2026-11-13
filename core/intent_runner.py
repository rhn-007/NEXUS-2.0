"""
NEXUS Intent Runner

Decides how a message is carried out, in this order:
  1. a clear multi-step request (fast path),
  2. the existing tool router, exactly as before,
  3. a clear single request in other words (fast path),
  4. the model planner, only for messages that look like requests.
Anything left over is normal conversation.
"""

import time

from core.capabilities import answer as capability_answer
from core.intent import BUILTIN_ACTIONS, Step
from tools.meet import looks_like_code_attempt, parse_meet_code
from tools.router import ToolResult
from utils.logger import setup_logger


logger = setup_logger(__name__)


class IntentRunner:

    def __init__(
        self,
        router,
        fast,
        planner,
        run_builtin,
        observer=None,
        history=None
    ):

        self.router = router
        self.fast = fast
        self.planner = planner
        self.run_builtin = run_builtin
        self.observer = observer
        self.history = history

        # Set after NEXUS asks for a meeting code, so the next message
        # is read as the code.
        self.pending = None

    # ======================================================
    # RESOLVE
    # ======================================================

    def resolve(self, text, recent=None):
        """Return a ToolResult. success=False means: just chat."""

        started = time.perf_counter()
        path = "none"
        actions = []
        decision = None
        planner_ms = None

        try:

            if self.pending:

                answered = self._answer_pending(text)

                if answered is not None:

                    path = "pending"

                    return answered

            about_me = capability_answer(text)

            if about_me:

                path = "capabilities"

                return ToolResult(True, about_me)

            if self.history:

                past = self.history.answer(text)

                if past:

                    path = "history"

                    return ToolResult(True, past)

            steps = self.fast.fast_steps(text)

            if len(steps) > 1:

                path = "fast_multi"
                actions = [step.action for step in steps]

                return self._run_steps(steps, text)

            if steps and steps[0].first:

                # The router would read this sentence differently.
                path = "fast"
                actions = [step.action for step in steps]

                return self._run_steps(steps, text)

            result = self.router.execute(text)

            if result.success:

                path = "router"

                self._remember(text, "command", text, result)

                return result

            if steps:

                path = "fast"
                actions = [step.action for step in steps]

                return self._run_steps(steps, text)

            if self.fast.looks_like_request(text):

                plan = self.planner.plan(text, recent)

                path = "planner"
                decision = plan.kind if plan.valid else "invalid"
                planner_ms = plan.planner_ms

                if plan.kind == "ask":

                    if plan.expects:
                        self.pending = {"kind": plan.expects, "tries": 0}

                    return ToolResult(True, plan.question)

                if plan.kind == "act":

                    actions = [step.action for step in plan.steps]

                    return self._run_steps(plan.steps, text)

            return result

        except Exception as error:

            logger.error("Intent resolution error: %s", error)

            return ToolResult()

        finally:

            if path not in ("none", "router") or decision:

                self._record(path, actions, decision, planner_ms, started)

    # ======================================================
    # FOLLOW-UP: THE MEETING CODE
    # ======================================================

    CANCEL_WORDS = ("cancel", "never mind", "nevermind", "forget it", "stop")

    def _answer_pending(self, text):
        """
        NEXUS just asked for a meeting code. Return a ToolResult if this
        message answers it, or None to treat it as an ordinary request.
        """

        state = self.pending

        lowered = str(text or "").lower().strip(" .!?")

        if lowered in self.CANCEL_WORDS:

            self.pending = None

            return ToolResult(True, "Okay, cancelled.")

        code = parse_meet_code(text)

        if code:

            self.pending = None

            return self._run_steps(
                [Step("join_meeting", code, f"join meeting {code}")],
                text
            )

        state["tries"] += 1

        if (
            state["tries"] <= 2
            and not self.fast.fast_steps(text)
            and looks_like_code_attempt(text)
        ):

            return ToolResult(
                True,
                "I didn't catch the code clearly. Say it again, or spell "
                "it with words like alpha, bravo, charlie."
            )

        self.pending = None

        return None

    # ======================================================
    # RUN STEPS
    # ======================================================

    def _run_steps(self, steps, request=""):

        messages = []

        for step in steps:

            if step.action == "join_meeting" and not step.value:

                self.pending = {"kind": "meet_code", "tries": 0}
                messages.append("What's the meeting code?")

                break

            if step.action not in BUILTIN_ACTIONS:

                result = self.router.execute(step.command)

                message = result.message or ""

                self._remember(request, step.action, step.command, result)

                if not result.success:

                    messages.append(
                        message
                        or f"I couldn't do that ({step.action.replace('_', ' ')})."
                    )

                    break

            else:

                message = self.run_builtin(step.action, step.value)

            if message:
                messages.append(message)

        return ToolResult(True, "\n".join(messages) or "Done.")

    # ======================================================
    # ACTION HISTORY
    # ======================================================

    def _remember(self, request, action, command, result):

        if not self.history:
            return

        self.history.record(
            request,
            action,
            command,
            result.success,
            result.message
        )

    # ======================================================
    # OBSERVATION
    # ======================================================

    def _record(self, path, actions, decision, planner_ms, started):

        if not self.observer:
            return

        metadata = {"path": path, "actions": actions}

        if decision:
            metadata["decision"] = decision

        if planner_ms is not None:
            metadata["planner_ms"] = planner_ms

        try:

            self.observer.record_event(
                event_type="intent_resolution",
                status="completed",
                duration_ms=(time.perf_counter() - started) * 1000,
                metadata=metadata
            )

        except Exception as error:

            logger.warning("Could not record intent metrics: %s", error)
