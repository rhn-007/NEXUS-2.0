"""
NEXUS Input Manager

Handles voice and keyboard input modes.
Voice mode is the default.
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



            # Handle system commands

            if self.check_mode_command(text):

                continue



            return text





    def voice_input(self):


        try:


            text = self.listener.listen()


            if text:


                print(

                    f"\nYou: {text}"

                )


            return text



        except Exception as e:


            logger.error(

                f"Voice input error: {e}"

            )


            return ""






    def keyboard_input(self):


        return input(

            "\nYou: "

        )






    def check_mode_command(self, text):


        command = text.lower().strip()



        if command == "keyboard mode":


            self.mode = "keyboard"


            print(

                "\nNEXUS: Keyboard mode enabled."

            )


            return True





        elif command == "voice mode":


            self.mode = "voice"


            print(

                "\nNEXUS: Voice mode enabled."

            )


            return True




        return False
