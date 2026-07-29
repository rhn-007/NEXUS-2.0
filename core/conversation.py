from utils.logger import setup_logger


logger = setup_logger(__name__)



class ConversationManager:


    def __init__(
        self,
        llm
    ):

        self.llm = llm


        self.history = []



        logger.info(
            "Conversation manager initialized"
        )



    def chat(
        self,
        user_input
    ):


        self.history.append(

            {
                "role": "user",
                "content": user_input
            }

        )


        prompt = self.build_prompt()



        response = self.llm.generate(
            prompt
        )


        self.history.append(

            {
                "role": "assistant",
                "content": response
            }

        )


        return response



    def build_prompt(self):


        prompt = """

You are NEXUS, a personal AI assistant.

Respond naturally and helpfully.

Conversation:

"""


        for message in self.history:

            prompt += (

                f"{message['role']}: "
                f"{message['content']}\n"

            )


        prompt += "\nassistant:"


        return prompt
