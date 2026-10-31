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
        """Convert a tool response or plain result into a ToolResult."""
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

    def execute(self, text):
        if not text or not text.strip():
            return ToolResult()

        query = text.lower().strip()

        # Calculator requests have priority over general language handling.
        if self.calculator.can_handle(text):
            result = self.calculator.execute(text)

            if result is None:
                return ToolResult(
                    success=False,
                    message="I recognised this as a calculation, but couldn't evaluate the expression. Please check the expression and try again.",
                    handled=True
                )

            return ToolResult(
                success=True,
                message=str(result),
                handled=True
            )

        # Browser requests.
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

        is_browser_command = any(
            command in query for command in browser_commands
        )

        if (
            browser_tool
            and is_browser_command
            and browser_tool.can_handle(text)
        ):
            return self._normalise_result(
                browser_tool.execute(text)
            )

        # Registered application launcher.
        application_tool = self.registry.get("application")

        if application_tool and application_tool.can_handle(text):
            return self._normalise_result(
                application_tool.execute(text)
            )

        # Any additional registered tools.
        for tool in self.registry.all():
            if tool.name in ("browser", "application"):
                continue

            if tool.can_handle(text):
                return self._normalise_result(
                    tool.execute(text)
                )

        return ToolResult()
