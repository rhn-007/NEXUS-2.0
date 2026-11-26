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
from core.followups import MEDIA_HELP, MEETING_HELP, FollowUps
from core.intent import BUILTIN_ACTIONS, Step
from tools.meet import looks_like_code_attempt, parse_meet_code
from tools.router import ToolResult
from tools.system_info import describe_explanation, describe_summary
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
        history=None,
        task_manager=None
    ):

        self.router = router
        self.fast = fast
        self.planner = planner
        self.run_builtin = run_builtin
        self.observer = observer
        self.history = history
        self.task_manager = task_manager

        # Set after NEXUS asks for a meeting code, so the next message
        # is read as the code.
        self.pending = None

        # What the last answer was about, so "anything else?" has meaning.
        self.followups = FollowUps()

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

            follow = self._follow_up(text)

            if follow is not None:

                path = "followup"

                return follow

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

                self.followups.note_text(text)

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

            # Plain conversation: the last feature is no longer the topic.
            self.followups.clear()

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
        spoken_parts = []
        task_id = None
        task_failed = False

        # Keep the current fast path and planner. Only multi-step requests
        # need a durable task record; one-step commands remain lightweight.
        has_missing_meeting_code = any(
            step.action == "join_meeting" and not step.value
            for step in steps
        )
        if self.task_manager and len(steps) > 1 and not has_missing_meeting_code:
            try:
                task_id = self.task_manager.create_task(request, steps)
            except Exception as error:
                logger.warning("Could not create task history: %s", error)

        for position, step in enumerate(steps):

            if step.action == "join_meeting" and not step.value:

                self.pending = {"kind": "meet_code", "tries": 0}
                messages.append("What's the meeting code?")
                spoken_parts.append(messages[-1])

                break

            if task_id:
                try:
                    self.task_manager.start_step(task_id, position)
                except Exception as error:
                    logger.warning("Could not start task step history: %s", error)

            try:
                if step.action not in BUILTIN_ACTIONS:

                    result = self.router.execute(step.command)
                    message = result.message or ""

                    self._remember(request, step.action, step.command, result)

                    if not result.success:

                        if task_id:
                            self.task_manager.finish_step(
                                task_id, position, "failed", message
                            )
                            self.task_manager.skip_remaining(task_id, position)
                            self.task_manager.set_task_status(
                                task_id, "failed", message or "A task step failed."
                            )
                            task_failed = True

                        messages.append(
                            message
                            or f"I couldn't do that ({step.action.replace('_', ' ')})."
                        )
                        spoken_parts.append(messages[-1])

                        break

                    spoken = getattr(result, "spoken", None)
                    self.followups.note_step(step)

                else:

                    message = self.run_builtin(step.action, step.value)
                    spoken = None

                if task_id:
                    self.task_manager.finish_step(
                        task_id, position, "completed", message or "Completed."
                    )

                if message:
                    messages.append(message)
                    spoken_parts.append(spoken or message)

            except Exception as error:
                if task_id:
                    try:
                        self.task_manager.finish_step(
                            task_id, position, "failed", str(error)
                        )
                        self.task_manager.skip_remaining(task_id, position)
                        self.task_manager.set_task_status(
                            task_id, "failed", str(error)
                        )
                    except Exception as history_error:
                        logger.warning(
                            "Could not record task failure: %s", history_error
                        )
                raise

        shown = "\n".join(messages) or "Done."
        said = "\n".join(spoken_parts) or "Done."

        if task_id and not task_failed:
            try:
                self.task_manager.complete_task(task_id, shown)
            except Exception as error:
                logger.warning("Could not complete task history: %s", error)

        return ToolResult(True, shown, said if said != shown else None)

    # ======================================================
    # FOLLOW-UPS ON A FEATURE
    # ======================================================

    def _follow_up(self, text):
        """Answer a short follow-up to the last feature, or return None."""

        match = self.followups.match(text)

        if not match:
            return None

        kind, value = match
        state = self.followups.state

        if kind == "topic":
            return self._run_command(text, f"system info {value}")

        if kind == "else":
            return self._anything_else(text, state)

        if kind == "explain":
            return self._explain(state)

        if kind == "media":
            return self._run_command(text, f"media {value}")

        if kind == "again":
            return self._run_command(text, state.get("command") or "")

        if kind == "meeting":

            return self._run_steps(
                [Step("start_meeting", "", "start meeting", first=True)],
                text
            )

        return None

    def _run_command(self, text, command):

        if not command:
            return None

        result = self.router.execute(command)

        self._remember(text, "followup", command, result)

        if result.success:
            self.followups.note_text(command)

        return result if result.message else None

    def _system_reading(self):
        """(cpu, memory, battery, disks) from the PC, or None."""

        try:

            tool = self.router.registry.get("system")
            reader = tool.reader

            return (
                reader.cpu_percent(), reader.memory(),
                reader.battery(), reader.disks()
            )

        except Exception as error:

            logger.warning("Could not read the PC for a follow-up: %s", error)

            return None

    def _anything_else(self, text, state):

        feature = state["feature"]

        if feature == "media":
            return ToolResult(True, MEDIA_HELP)

        if feature == "meeting":
            return ToolResult(True, MEETING_HELP)

        topic = self.followups.next_pc_topic()

        if topic:
            return self._run_command(text, f"system info {topic}")

        message = "That's everything I can see on your PC."

        reading = self._system_reading()

        if reading:

            summary = describe_summary(*reading)

            if summary.startswith(("Heads up", "Mostly fine")):
                message += " " + summary

        return ToolResult(True, message)

    def _explain(self, state):

        reading = self._system_reading()

        if not reading:
            return None

        return ToolResult(
            True, describe_explanation(state["topic"], *reading)
        )

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
