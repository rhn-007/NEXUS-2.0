"""
NEXUS Core Assistant

Main brain controller.
"""


from dotenv import load_dotenv


from ai.ollama import OllamaClient

from memory.memory_manager import MemoryManager

from core.conversation import ConversationManager

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
        # CONVERSATION
        # ==========================

        self.conversation = ConversationManager()



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






    def start(self):


        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        while True:


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






    def register_tools(self):


        self.tool_registry.register(

            BrowserTool()

        )






    def process_input(

        self,

        user_input

    ):



        if not user_input.strip():

            return "Please enter something."



        self.status = "PROCESSING"


        set_status(
            "Thinking"
        )


        logger.info(

            f"User: {user_input}"

        )



        try:


            # ======================
            # ADD USER MESSAGE
            # ======================

            self.conversation.add_user_message(

                user_input

            )



            # ======================
            # SAVE MEMORY
            # ======================

            self.memory.process_memory(

                user_input

            )



            # ======================
            # CHECK MEMORY
            # ======================

            memory_response = self.check_memory(

                user_input

            )


            if memory_response:


                self.conversation.add_assistant_message(

                    memory_response

                )


                return memory_response





            # ======================
            # TOOLS
            # ======================

            tool_result = self.tool_router.execute(

                user_input

            )


            if tool_result.success:


                self.conversation.add_assistant_message(

                    tool_result.message

                )


                return tool_result.message






            # ======================
            # AI RESPONSE
            # ======================


            context = self.conversation.get_context()



            response = self.llm.generate_response(

                user_input,

                context

            )



            self.conversation.add_assistant_message(

                response

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


            return f"Error: {e}"



        finally:


            self.status = "READY"

            clear_status()





    def check_memory(
            self,
            user_input
    ):
    
    
        text = user_input.lower()
    
    
    
        profile_keywords = [
    
            "what do you know about me",
    
            "what do u know about me",
    
            "tell me about myself",
    
            "who am i",
    
            "my profile",
    
            "my details"
    
        ]
    
    
    
        if any(
    
            keyword in text
    
            for keyword in profile_keywords
    
        ):
    
    
            memories = self.memory.get_memory_context()
    
    
    
            if not memories:
    
    
                return (
                    "I don't have any stored information about you yet."
                )
    
    
    
            profile = []
    
    
    
            for item in memories:
    
    
                try:
    
    
                    key = item[0]
    
                    value = item[1]
    
                    category = item[2]
    
    
    
                    if category != "conversation":
    
    
                        profile.append(
    
                            f"• {key.replace('_',' ').title()}: {value}"
    
                        )
    
    
                except Exception:
    
    
                    continue
    
    
    
    
    
            if profile:
    
    
                return (
    
                    "Here's what I know about you:\n\n"
    
                    +
    
                    "\n".join(profile)
    
                )
    
    
    
            return (
    
                "I have memories stored, but no personal details about you yet."
    
            )
    
    
    
    
    
        return None
