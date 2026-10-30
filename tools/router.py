
"""
NEXUS Tool Router

Decides which tool handles a request.
"""

from tools.calculator import CalculatorTool


class ToolResult:

    def __init__(
        self,
        success=False,
        message=""
    ):

        self.success = success
        self.message = message


class ToolRouter:

    def __init__(
        self,
        registry
    ):

        self.registry = registry
        self.calculator = CalculatorTool()

    def execute(
        self,
        text
    ):

        # ==========================
        # CALCULATOR
        # ==========================

        if self.calculator.can_handle(text):

            result = self.calculator.execute(text)

            if result is not None:

                return ToolResult(
                    True,
                    str(result)
                )

        # ==========================
        # APPLICATION CONTROL
        # ==========================

        application_tool = self.registry.get("application")

        if application_tool and application_tool.can_handle(text):

            result = application_tool.execute(text)

            return ToolResult(
                True,
                str(result)
            )

        # ==========================
        # REGISTERED TOOLS
        # ==========================

        for tool in self.registry.all():

            if tool.can_handle(text):

                result = tool.execute(text)

                # ToolResponse objects expose success and message.
                if hasattr(result, "success") and hasattr(result, "message"):

                    return ToolResult(
                        result.success,
                        result.message
                    )

                return ToolResult(
                    True,
                    str(result)
                )

        return ToolResult()
