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

from core.intent import BUILTIN_ACTIONS
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
        observer=None
    ):

        self.router = router
        self.fast = fast
        self.planner = planner
        self.run_builtin = run_builtin
        self.observer = observer

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

            steps = self.fast.fast_steps(text)

            if len(steps) > 1:

                path = "fast_multi"
                actions = [step.action for step in steps]

                return self._run_steps(steps)

            if steps and steps[0].first:

                # The router would read this sentence differently.
                path = "fast"
                actions = [step.action for step in steps]

                return self._run_steps(steps)

            result = self.router.execute(text)

            if result.success:

                path = "router"

                return result

            if steps:

                path = "fast"
                actions = [step.action for step in steps]

                return self._run_steps(steps)

            if self.fast.looks_like_request(text):

                plan = self.planner.plan(text, recent)

                path = "planner"
                decision = plan.kind if plan.valid else "invalid"
                planner_ms = plan.planner_ms

                if plan.kind == "ask":

                    return ToolResult(True, plan.question)

                if plan.kind == "act":

                    actions = [step.action for step in plan.steps]

                    return self._run_steps(plan.steps)

            return result

        except Exception as error:

            logger.error("Intent resolution error: %s", error)

            return ToolResult()

        finally:

            if path not in ("none", "router") or decision:

                self._record(path, actions, decision, planner_ms, started)

    # ======================================================
    # RUN STEPS
    # ======================================================

    def _run_steps(self, steps):

        messages = []

        for step in steps:

            if step.action not in BUILTIN_ACTIONS:

                result = self.router.execute(step.command)

                message = result.message or ""

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
