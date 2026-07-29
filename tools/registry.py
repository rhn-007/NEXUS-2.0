"""
NEXUS Tool Registry

Stores and manages all available tools.
"""



import logging


logger = logging.getLogger(__name__)




class ToolRegistry:



    def __init__(self):

        self.tools = {}



    # ==========================================
    # REGISTER TOOL
    # ==========================================

    def register(
        self,
        tool
    ):


        if not tool:

            return



        name = getattr(
            tool,
            "name",
            None
        )


        if not name:

            logger.warning(
                "Tool missing name."
            )

            return



        self.tools[name] = tool



        logger.info(

            f"Registered tool: {name}"

        )



    # ==========================================
    # GET TOOL
    # ==========================================

    def get(
        self,
        name
    ):

        return self.tools.get(
            name
        )



    # ==========================================
    # LIST TOOLS
    # ==========================================

    def list_tools(self):

        return list(
            self.tools.keys()
        )



    # ==========================================
    # ALL TOOLS
    # ==========================================

    def all(self):

        return self.tools.values()
