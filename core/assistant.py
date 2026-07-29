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



        keywords = [

            "my name",

            "my favourite",

            "my favorite",

            "what do you know",

            "what do u know",

            "recall",

            "remember",

            "previous conversation",

            "earlier"

        ]



        if not any(

            word in text

            for word in keywords

        ):

            return None




        memories = self.memory.get_memory_context()



        if not memories:

            return None




        for key, value in memories:


            if key.replace(

                "_",

                " "

            ) in text:


                return (

                    f"Your {key.replace('_',' ')} is {value}."

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
