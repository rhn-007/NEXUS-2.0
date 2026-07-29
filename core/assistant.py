from utils.logger import setup_logger

from ai.ollama import OllamaClient

from core.conversation import ConversationManager


logger = setup_logger(__name__)



class NexusAssistant:


    def __init__(self):

        logger.info(
            "Starting NEXUS core..."
        )


        self.llm = OllamaClient()


        self.conversation = ConversationManager()


        logger.info(
            "NEXUS core initialized"
        )



    def start(self):

        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        self.chat_loop()



    def process(
        self,
        user_input
    ):


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
