from utils.logger import setup_logger

from ai.ollama import OllamaClient

from core.conversation import ConversationManager

from memory.memory_manager import MemoryManager
from memory.detector import MemoryDetector


logger = setup_logger(__name__)



class NexusAssistant:


    def __init__(self):

        logger.info(
            "Starting NEXUS core..."
        )


        # AI MODEL

        self.llm = OllamaClient()



        # CONVERSATION MEMORY

        self.conversation = ConversationManager()



        # LONG TERM MEMORY

        self.memory = MemoryManager()


        self.memory_detector = MemoryDetector()



        logger.info(
            "NEXUS core initialized"
        )



    # =====================================================
    # START ASSISTANT
    # =====================================================

    def start(self):

        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        self.chat_loop()



    # =====================================================
    # PROCESS USER INPUT
    # =====================================================

    def process(
        self,
        user_input
    ):


        if not user_input:

            return (
                "Please enter something."
            )



        user_input = user_input.strip()



        # =================================================
        # MEMORY SAVE DETECTION
        # =================================================

        memory = self.memory_detector.detect(
            user_input
        )



        if memory:


            self.memory.remember(

                memory["key"],

                memory["value"]

            )


            logger.info(

                f"Memory saved: "
                f"{memory['key']} = {memory['value']}"

            )


            return (

                f"I will remember that your "
                f"{memory['key']} is "
                f"{memory['value']}."

            )



        # =================================================
        # MEMORY RECALL
        # =================================================

        lower_input = user_input.lower()



        if (

            "what is my" in lower_input

            or

            "what's my" in lower_input

        ):


            key = (

                lower_input

                .replace(
                    "what is my",
                    ""
                )

                .replace(
                    "what's my",
                    ""
                )

                .replace(
                    "?",
                    ""
                )

                .strip()

            )



            result = self.memory.recall(
                key
            )



            if result:


                logger.info(

                    f"Memory recalled: "
                    f"{key} = {result}"

                )


                return (

                    f"Your {key} is {result}."

                )



        # =================================================
        # NORMAL AI CHAT
        # =================================================


        self.conversation.add_user_message(
            user_input
        )



        context = self.conversation.get_context()



        response = self.llm.generate(
            context
        )



        self.conversation.add_assistant_message(
            response
        )



        return response




    # =====================================================
    # CHAT LOOP
    # =====================================================

    def chat_loop(self):


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



                response = self.process(
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



            except Exception as e:


                logger.error(

                    f"Assistant error: {e}"

                )


                print(

                    "Error:",

                    e

                )
