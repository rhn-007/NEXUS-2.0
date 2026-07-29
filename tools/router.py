"""
NEXUS Tool Router

Finds the correct tool for a user request.
"""



import logging


from tools.response import ToolResponse



logger = logging.getLogger(__name__)




class ToolRouter:



    def __init__(
        self,
        registry
    ):

        self.registry = registry



    # ==========================================
    # FIND TOOL
    # ==========================================

    def find_tool(
        self,
        query
    ):


        if not query:

            return None



        for tool in self.registry.all():


            try:


                if tool.can_handle(
                    query
                ):

                    return tool



            except Exception as e:


                logger.error(

                    f"Tool detection error: {e}"

                )



        return None




    # ==========================================
    # EXECUTE
    # ==========================================

    def execute(
        self,
        query
    ):


        tool = self.find_tool(
            query
        )



        if not tool:


            return ToolResponse.failure(

                "No matching tool found."

            )



        try:


            result = tool.execute(
                query
            )



            if isinstance(
                result,
                ToolResponse
            ):

                return result



            return ToolResponse.success(

                str(result)

            )



        except Exception as e:


            logger.error(

                f"Tool execution failed: {e}"

            )


            return ToolResponse.failure(

                str(e)

            )
