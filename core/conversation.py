"""
NEXUS Conversation Manager

Handles:
- Conversation history
- System personality
- Context building
"""


from utils.logger import setup_logger

from prompts.system_prompt import SYSTEM_PROMPT



logger = setup_logger(__name__)





class ConversationManager:



    def __init__(self):

        self.history = []


        logger.info(
            "Conversation manager ready"
        )





    def add_user_message(
        self,
        message
    ):


        self.history.append(

            {
                "role": "user",

                "content": message
            }

        )





    def add_assistant_message(
        self,
        message
    ):


        self.history.append(

            {
                "role": "assistant",

                "content": message
            }

        )





    def get_context(
        self
    ):


        messages = [

            {
                "role": "system",

                "content": SYSTEM_PROMPT

            }

        ]


        messages.extend(

            self.history[-20:]

        )


        return messages





    def clear(
        self
    ):


        self.history.clear()
