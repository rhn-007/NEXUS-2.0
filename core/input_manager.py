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


        """
        Gets user input based on current mode.
        """


        if self.mode == "voice":


            return self.voice_input()



        else:


            return self.keyboard_input()






    def voice_input(self):


        """
        Listen through microphone.
        """


        try:


            text = self.listener.listen()



            if not text:


                return ""



            print(

                f"\nYou: {text}"

            )



            # Check for mode switching commands

            self.check_mode_command(text)



            return text



        except Exception as e:


            logger.error(

                f"Voice input error: {e}"

            )


            return ""







    def keyboard_input(self):


        """
        Normal terminal input.
        """


        text = input(

            "\nYou: "

        )



        self.check_mode_command(text)



        return text







    def check_mode_command(self, text):


        """
        Switch between voice and keyboard.
        """


        command = text.lower().strip()



        if command == "keyboard mode":


            self.mode = "keyboard"



            print(

                "\nNEXUS: Keyboard mode enabled."

            )



        elif command == "voice mode":


            self.mode = "voice"



            print(

                "\nNEXUS: Voice mode enabled."

            )
