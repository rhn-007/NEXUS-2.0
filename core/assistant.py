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


        self.memory = MemoryManager()


        self.llm = OllamaClient()



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






    def get_status(self):

        return self.status







    # ==================================
    # MEMORY ROUTING
    # ==================================



    def check_memory(
        self,
        user_input
    ):
    
    
        text = user_input.lower()
    
    
    
        # Normalize spelling
    
        text = text.replace(
            "colour",
            "color"
        )
    
    
    
        # ==========================
        # PROFILE MEMORY
        # ==========================
    
    
        profile_keywords = [
    
            "what do you know",
    
            "what do u know",
    
            "tell me about myself",
    
            "tell me about me",
    
            "what can you tell me about myself",
    
            "what do you remember about me",
    
            "what do u remember about me",
    
            "describe me",
    
            "who am i",
    
            "do you know me",
    
            "how well do you know me",
    
            "what information do you have about me",
    
            "what facts do you know about me",
    
            "summarize me",
    
            "give me my profile",
    
            "show my profile",
    
            "my profile",
    
            "my details",
    
            "my information",
    
            "recall my details"
    
        ]
    
    
    
        if any(
    
            word in text
    
            for word in profile_keywords
    
        ):
    
    
    
            memories = self.memory.get_memory_context()
    
    
    
            profile = []
    
    
    
            for key, value, category in memories:
    
    
                if category != "conversation":
    
    
                    profile.append(
    
                        f"{key.replace('_',' ')}: {value}"
    
                    )
    
    
    
            if profile:
    
    
                return (
    
                    "Here is what I know about you:\n\n"
    
                    +
    
                    "\n".join(profile)
    
                )
    
    
    
    
    
        # ==========================
        # CONVERSATION RECALL
        # ==========================
    
    
        recall_keywords = [
    
            "recall",
    
            "remember",
    
            "do you remember",
    
            "what do you remember",
    
            "what did we talk about",
    
            "what did we discuss",
    
            "what have we discussed",
    
            "what was our conversation about",
    
            "summarize our conversation",
    
            "conversation summary",
    
            "chat summary",
    
            "previous chat",
    
            "old chat",
    
            "past conversation",
    
            "earlier conversation",
    
            "our previous conversation",
    
            "our last conversation",
    
            "what happened before",
    
            "what did i tell you",
    
            "what have i told you",
    
            "what information did i give you",
    
            "continue from where we left",
    
            "where did we stop",
    
            "what were we talking about"
    
        ]
    
    
    
        if any(
    
            word in text
    
            for word in recall_keywords
    
        ):
    
    
    
            conversations = self.memory.get_context()
    
    
    
            if conversations:
    
    
                response = [
    
                    "Here is what I remember from our previous conversation:\n"
    
                ]
    
    
    
                for key, value, category in conversations[-10:]:
    
    
                    if key == "user":
    
    
                        response.append(
    
                            f"You: {value}"
    
                        )
    
    
                    elif key == "assistant":
    
    
                        response.append(
    
                            f"NEXUS: {value}"
    
                        )
    
    
    
                return "\n".join(response)
    
    
    
            else:
    
    
                return (
    
                    "I don't have any previous conversation stored yet."
    
                )
    
    
    
    
    
        # ==========================
        # SPECIFIC MEMORY SEARCH
        # ==========================
    
    
        memories = self.memory.get_memory_context()
    
    
    
        for key, value, category in memories:
    
    
    
            key_text = key.replace(
    
                "_",
    
                " "
    
            )
    
    
    
            if key_text in text:
    
    
                return (
    
                    f"Your {key_text} is {value}."
    
                )
    
    
    
        return None
        



    def process_input(

        self,

        user_input

    ):



        if not user_input:

            return "Please enter something."



        self.status = "PROCESSING"


        set_status(

            "Processing"

        )


        logger.info(

            f"User: {user_input}"

        )



        try:



            # ======================
            # SAVE MEMORY
            # ======================


            self.memory.process_memory(

                user_input

            )




            # ======================
            # MEMORY LOOKUP
            # ======================


            memory_answer = self.check_memory(

                user_input

            )


            if memory_answer:


                return memory_answer





            # ======================
            # TOOLS
            # ======================


            tool_result = self.tool_router.execute(

                user_input

            )



            if tool_result.success:


                return tool_result.message





            # ======================
            # AI RESPONSE
            # ======================


            context = self.memory.get_context()



            response = self.llm.generate_response(

                user_input,

                context

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
