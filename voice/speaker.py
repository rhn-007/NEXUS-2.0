"""
NEXUS Voice Speaker

Handles text-to-speech output.
"""


import pyttsx3

from utils.logger import setup_logger


logger = setup_logger(__name__)





class NexusSpeaker:



    def __init__(self):


        self.engine = pyttsx3.init()


        self.setup_voice()


        logger.info(
            "Voice system ready"
        )





    def setup_voice(self):


        voices = self.engine.getProperty(
            "voices"
        )


        if voices:


            # Try to use a better sounding voice

            self.engine.setProperty(

                "voice",

                voices[0].id

            )



        self.engine.setProperty(

            "rate",

            170

        )


        self.engine.setProperty(

            "volume",

            1.0

        )







    def speak(
        self,
        text
    ):


        if not text:

            return



        try:


            self.engine.say(

                text

            )


            self.engine.runAndWait()



        except Exception as e:


            logger.error(

                f"Speech error: {e}"

            )





speaker = NexusSpeaker()
