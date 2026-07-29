"""
NEXUS Core Assistant

Main brain controller.

Responsibilities:
- Manage AI conversation
- Manage memory
- Route tools
- Handle user requests
"""


from dotenv import load_dotenv


from ai.ollama import OllamaClient

from memory.manager import MemoryManager

from tools.registry import ToolRegistry
from tools.router import ToolRouter
from tools.browser import BrowserTool


from utils.logger import setup_logger



load_dotenv()



logger = setup_logger(__name__)





class PersonalAssistant:



    def __init__(self):


        logger.info(
            "Initializing NEXUS..."
        )


        # ==========================
        # MEMORY
        # ==========================


        self.memory = MemoryManager()



        # ==========================
        # AI MODEL
        # ==========================


        self.llm = OllamaClient()



        # ==========================
        # TOOLS
        # ==========================


        self.tool_registry = ToolRegistry()


        self.register_tools()



        self.tool_router = ToolRouter(

            self.tool_registry

        )



        # ==========================
        # STATUS
        # ==========================


        self.status = "READY"



        logger.info(
            "NEXUS initialized successfully."
        )





    # ==========================================
    # TOOL REGISTRATION
    # ==========================================


    def register_tools(self):


        self.tool_registry.register(

            BrowserTool()

        )


        logger.info(
            "Tools loaded."
        )





    # ==========================================
    # GET STATUS
    # ==========================================


    def get_status(self):


        return self.status





    # ==========================================
    # MEMORY SAVE
    # ==========================================


    def remember(
        self,
        text
    ):


        try:


            self.memory.save_memory(

                text

            )


        except Exception as e:


            logger.error(

                f"Memory save failed: {e}"

            )





    # ==========================================
    # PROCESS USER INPUT
    # ==========================================


    def process_input(
        self,
        user_input
    ):


        if not user_input:


            return (
                "Please enter something."
            )



        user_input = user_input.strip()



        self.status = "PROCESSING"



        logger.info(

            f"User: {user_input}"

        )



        try:


            # --------------------------
            # MEMORY
            # --------------------------


            self.remember(

                user_input

            )



            # --------------------------
            # TOOL ROUTING
            # --------------------------


            tool_result = self.tool_router.execute(

                user_input

            )



            if tool_result.success:


                self.status = "READY"


                return tool_result.message





            # --------------------------
            # AI RESPONSE
            # --------------------------


            context = self.memory.get_context()



            response = self.llm.generate_response(

                user_input,

                context

            )



            self.memory.save_conversation(

                user_input,

                response

            )



            self.status = "READY"



            return response





        except Exception as e:



            logger.error(

                f"NEXUS processing error: {e}"

            )



            self.status = "ERROR"



            return (

                f"Error: {e}"

            )



        finally:


            if self.status != "ERROR":

                self.status = "READY"
