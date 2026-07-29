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

from memory.memory_manager import MemoryManager

from tools.registry import ToolRegistry
from tools.router import ToolRouter
from tools.browser import BrowserTool

from ui.status import set_status, clear_status


from utils.logger import setup_logger



load_dotenv()


logger = setup_logger(__name__)




class NexusAssistant:



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
    # START LOOP
    # ==========================================

    def start(self):


        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        while True:


            try:


                user_input = input(
                    "You: "
                )


                if user_input.lower() in [

                    "exit",

                    "quit"

                ]:


                    print(
                        "Goodbye 👋"
                    )


                    break



                if not user_input.strip():

                    continue



                response = self.process_input(

                    user_input

                )


                print(

                    "\nNEXUS:",

                    response,

                    "\n"

                )



            except KeyboardInterrupt:


                print(
                    "\nGoodbye 👋"
                )


                break



    # ==========================================
    # STATUS
    # ==========================================

    def get_status(self):

        return self.status




    # ==========================================
    # PROCESS INPUT
    # ==========================================

    def process_input(
        self,
        user_input
    ):


        if not user_input:

            return "Please enter something."



        user_input = user_input.strip()



        self.status = "PROCESSING"



        set_status(
            "Processing"
        )



        logger.info(

            f"User: {user_input}"

        )



        try:


            # ==========================
            # MEMORY DETECTION
            # ==========================


            self.memory.process_memory(

                user_input

            )



            # ==========================
            # TOOLS
            # ==========================


            tool_result = self.tool_router.execute(

                user_input

            )


            if tool_result.success:


                return tool_result.message



            # ==========================
            # CONTEXT
            # ==========================


            memory_context = (

                self.memory.get_memory_context()

            )


            conversation_context = (

                self.memory.get_context()

            )



            context = [

                {

                    "role": "system",

                    "content":
                    f"User facts: {memory_context}"

                }

            ]



            for item in conversation_context:


                context.append(

                    {

                        "role": "user",

                        "content": item[1]

                    }

                )



            # ==========================
            # AI RESPONSE
            # ==========================


            set_status(
                "Thinking"
            )


            response = self.llm.generate_response(

                user_input,

                context

            )



            # ==========================
            # SAVE CHAT
            # ==========================


            self.memory.save_conversation(

                user_input,

                response

            )



            return response



        except Exception as e:


            logger.error(

                f"NEXUS error: {e}"

            )


            return f"Error: {e}"



        finally:


            self.status = "READY"


            clear_status()
