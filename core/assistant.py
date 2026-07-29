"""
NEXUS Core Assistant

Main brain controller.
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


        # MEMORY

        self.memory = MemoryManager()



        # AI

        self.llm = OllamaClient()



        # TOOLS

        self.tool_registry = ToolRegistry()

        self.register_tools()


        self.tool_router = ToolRouter(

            self.tool_registry

        )



        self.status = "READY"



        logger.info(
            "NEXUS initialized successfully."
        )






    # =====================================
    # START
    # =====================================


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







    # =====================================
    # TOOLS
    # =====================================


    def register_tools(self):


        self.tool_registry.register(

            BrowserTool()

        )






    # =====================================
    # STATUS
    # =====================================


    def get_status(self):

        return self.status







    # =====================================
    # MAIN PROCESSOR
    # =====================================


    def process_input(

        self,

        user_input

    ):


        if not user_input.strip():


            return (

                "Please enter something."

            )



        logger.info(

            f"User: {user_input}"

        )



        self.status = "PROCESSING"



        set_status(

            "Thinking"

        )



        try:



            # --------------------------------
            # STORE MEMORY
            # --------------------------------


            learned = self.memory.process_memory(

                user_input

            )



            if learned:


                return self.memory_confirmation(

                    user_input

                )







            # --------------------------------
            # MEMORY QUESTIONS
            # --------------------------------


            memory_response = self.memory.handle_memory_query(

                user_input

            )


            if memory_response:


                return memory_response







            # --------------------------------
            # TOOLS
            # --------------------------------


            tool_result = self.tool_router.execute(

                user_input

            )


            if tool_result.success:


                return tool_result.message







            # --------------------------------
            # AI RESPONSE
            # --------------------------------


            context = self.memory.get_context()



            personality = """

You are NEXUS, a personal AI assistant.

Personality:
- Calm
- Intelligent
- Professional
- Slightly witty when appropriate
- Helpful and concise

Speak naturally like a personal assistant.

Do not say:
- "I am just an AI"
- "I don't have memories"
- "This is our first conversation"

If user information exists in context, use it naturally.

"""



            full_context = {

                "personality": personality,

                "memory": context

            }




            response = self.llm.generate_response(

                user_input,

                full_context

            )



            self.memory.save_conversation(

                user_input,

                response

            )



            return response






        except Exception as e:


            logger.error(

                f"NEXUS error: {e}"

            )


            return (

                f"Error: {e}"

            )



        finally:


            self.status = "READY"


            clear_status()







    # =====================================
    # MEMORY ACKNOWLEDGEMENT
    # =====================================


    def memory_confirmation(

        self,

        text

    ):


        lower = text.lower()



        if "name" in lower:


            return (

                "Nice to meet you. "

                "I'll remember your name."

            )



        if "like" in lower or "love" in lower:


            return (

                "Got it. "

                "I'll remember that."

            )



        return (

            "Understood. "

            "I'll keep that in mind."

        )
