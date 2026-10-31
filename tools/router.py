"""Routes user requests to the appropriate NEXUS tool."""

from tools.calculator import CalculatorTool


class ToolResult:
    def __init__(self, success=False, message="", handled=False, data=None):
        self.success = success
        self.message = message
        self.handled = handled
        self.data = data or {}


class ToolRouter:
    def __init__(self, registry):
        self.registry = registry
        self.calculator = CalculatorTool()

    @staticmethod
    def _normalise_result(result):
        if hasattr(result, "success") and hasattr(result, "message"):
            return ToolResult(
                success=bool(result.success),
                message=str(result.message),
                handled=True,
                data=getattr(result, "data", {})
            )

        if result is None:
            return ToolResult(
                success=False,
                message="The tool could not complete the request.",
                handled=True
            )

        return ToolResult(
            success=True,
            message=str(result),
            handled=True
        )

    def can_handle_request(self, text):
        """Check whether an installed tool recognises a command."""
        if not text or not text.strip():
            return False

        query = text.lower().strip()

        if self.calculator.can_handle(text):
            return True

        browser_tool = self.registry.get("browser")
        browser_commands = (
            "open browser",
            "launch browser",
            "start browser",
            "open website",
            "open youtube",
            "open google",
            "open github",
            "open wikipedia",
            "open reddit",
            "open chatgpt",
            "open instagram",
            "open whatsapp web",
            "go to",
            "visit",
            "browse",
            "search",
            "google"
        )

        if (
            browser_tool
            and any(command in query for command in browser_commands)
            and browser_tool.can_handle(text)
        ):
            return True

        application_tool = self.registry.get("application")
        if application_tool and application_tool.can_handle(text):
            return True

        for tool in self.registry.all():
            if tool.name in ("browser", "application"):
                continue
            if tool.can_handle(text):
                return True

        return False

    def describe_tools(self):
        descriptions = [
            "calculator: evaluates simple arithmetic expressions"
        ]

        for tool in self.registry.all():
            descriptions.append(
                f"{tool.name}: {tool.description}"
            )

        return descriptions

    def execute(self, text):
        if not text or not text.strip():
            return ToolResult()

        query = text.lower().strip()

        if self.calculator.can_handle(text):
            result = self.calculator.execute(text)

            if result is None:
                return ToolResult(
                    success=False,
                    message=(
                        "I recognised this as a calculation, but couldn't "
                        "evaluate the expression. Please check it and try again."
                    ),
                    handled=True
                )

            return ToolResult(
                success=True,
                message=str(result),
                handled=True
            )

        browser_tool = self.registry.get("browser")
        browser_commands = (
            "open browser",
            "launch browser",
            "start browser",
            "open website",
            "open youtube",
            "open google",
            "open github",
            "open wikipedia",
            "open reddit",
            "open chatgpt",
            "open instagram",
            "open whatsapp web",
            "go to",
            "visit",
            "browse",
            "search",
            "google"
        )

        if (
            browser_tool
            and any(command in query for command in browser_commands)
            and browser_tool.can_handle(text)
        ):
            return self._normalise_result(
                browser_tool.execute(text)
            )

        application_tool = self.registry.get("application")
        if application_tool and application_tool.can_handle(text):
            return self._normalise_result(
                application_tool.execute(text)
            )

        for tool in self.registry.all():
            if tool.name in ("browser", "application"):
                continue
            if tool.can_handle(text):
                return self._normalise_result(
                    tool.execute(text)
                )

        return ToolResult()

    def execute_plan(self, steps):
        """Execute a prevalidated plan in order and stop on the first failure."""
        if not isinstance(steps, list) or not 2 <= len(steps) <= 5:
            return ToolResult(
                success=False,
                message="The action plan was invalid.",
                handled=True
            )

        # Validate every step before performing the first action.
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, str) or not self.can_handle_request(step):
                return ToolResult(
                    success=False,
                    message=(
                        f"I couldn't safely execute the plan. "
                        f"Step {index} is not supported by the installed tools."
                    ),
                    handled=True
                )

        completed = []

        for index, step in enumerate(steps, start=1):
            result = self.execute(step)

            if not result.handled or not result.success:
                details = "\n".join(
                    f"{number}. {item}"
                    for number, item in enumerate(completed, start=1)
                )

                message = (
                    f"The plan stopped at step {index}: {result.message}"
                )

                if details:
                    message += "\nCompleted steps:\n" + details

                return ToolResult(
                    success=False,
                    message=message,
                    handled=True,
                    data={"completed": completed, "failed_step": index}
                )

            completed.append(result.message)

        summary = "\n".join(
            f"{number}. {item}"
            for number, item in enumerate(completed, start=1)
        )

        return ToolResult(
            success=True,
            message="Completed the requested steps:\n" + summary,
            handled=True,
            data={"completed": completed}
        )
