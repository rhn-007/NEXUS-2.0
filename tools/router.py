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


        if self.calculator.can_handle(
            text
        ):


            result = self.calculator.execute(
                text
            )


            if result is not None:


                return ToolResult(

                    True,

                    result

                )



        # ==========================
        # REGISTERED TOOLS
        # ==========================


        for tool in self.registry.tools:


            if tool.can_handle(
                text
            ):


                result = tool.execute(
                    text
                )


                return ToolResult(

                    True,

                    result

                )



        return ToolResult()
