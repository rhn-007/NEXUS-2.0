from utils.logger import setup_logger

from core.config import Config

from ai.llm import OllamaClient

from core.conversation import ConversationManager


logger = setup_logger(__name__)



class NexusAssistant:


    def __init__(self):


        self.name = Config.APP_NAME

        self.version = Config.VERSION



        self.llm = OllamaClient()


        self.conversation = ConversationManager(
            self.llm
        )


        logger.info(
            "NEXUS core initialized"
        )



    def start(self):


        logger.info(
            f"{self.name} {self.version} ready."
        )


        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        self.chat_loop()



    def chat_loop(self):


        while True:


            try:

                user = input(
                    "You: "
                )


                if user.lower() in [

                    "exit",

                    "quit"

                ]:

                    print(
                        "Goodbye 👋"
                    )

                    break



                response = self.conversation.chat(
                    user
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
