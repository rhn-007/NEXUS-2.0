"""
NEXUS Input Manager

Voice-first input system with keyboard fallback.
"""


from voice.listener import Listener

from utils.logger import setup_logger


logger = setup_logger(__name__)





class InputManager:


    def __init__(self):


        self.mode = "voice"

        self.listener = Listener()


        logger.info(
            "Input manager initialized in voice mode"
        )






    def get_input(self):


        while True:



            if self.mode == "voice":

                text = self.voice_input()


            else:

                text = self.keyboard_input()



            if not text:

                continue




            command_handled = self.handle_command(text)



            if command_handled:

                continue



            return text






    def voice_input(self):


        text = self.listener.listen()



        if text:


            print(

                f"\nYou: {text}"

            )



        return text






    def keyboard_input(self):


        return input(

            "\nYou: "

        )







    def handle_command(self, text):


        command = text.lower().strip()



        if command == "keyboard mode":


            self.mode = "keyboard"


            print(

                "\nNEXUS: Keyboard mode enabled."

            )


            return True






        if command == "voice mode":


            self.mode = "voice"


            print(

                "\nNEXUS: Voice mode enabled."

            )


            return True





        return False
