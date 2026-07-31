"""
NEXUS Input Manager

Handles voice and keyboard input modes.
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





            if self.handle_command(text):


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


        try:


            return input(

                "\nYou: "

            )



        except Exception as e:


            logger.error(

                f"Keyboard input error: {e}"

            )


            return ""








    def handle_command(self, text):


        command = text.lower().strip()






        # ==========================
        # Keyboard mode
        # ==========================


        keyboard_phrases = [


            "keyboard mode",

            "switch to keyboard",

            "go to keyboard",

            "use keyboard",

            "turn on keyboard mode"

        ]



        if any(

            phrase in command

            for phrase in keyboard_phrases

        ):


            self.mode = "keyboard"



            print(

                "\nNEXUS: Keyboard mode enabled."

            )



            return True








        # ==========================
        # Voice mode
        # ==========================


        voice_phrases = [


            "voice mode",

            "switch to voice",

            "go to voice",

            "use voice",

            "turn on voice mode"

        ]



        if any(

            phrase in command

            for phrase in voice_phrases

        ):


            self.mode = "voice"



            print(

                "\nNEXUS: Voice mode enabled."

            )



            return True







        # ==========================
        # Cancel commands
        # ==========================


        cancel_phrases = [


            "cancel",

            "never mind",

            "forget it",

            "stop"

        ]



        if any(

            phrase in command

            for phrase in cancel_phrases

        ):


            print(

                "\nNEXUS: Cancelled."

            )



            return True






        return False
