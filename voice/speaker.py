"""
NEXUS Piper Voice System

Handles natural offline speech.
"""


from pathlib import Path
import subprocess
import tempfile
import threading
import os

from utils.logger import setup_logger


logger = setup_logger(__name__)




class NexusSpeaker:


    def __init__(self):


        self.base_path = Path(__file__).parent.parent


        self.piper = (

            self.base_path
            /
            "piper"
            /
            "piper.exe"

        )


        self.model = (

            self.base_path
            /
            "voice"
            /
            "models"
            /
            "en_US-ryan-high.onnx"

        )


        self.lock = threading.Lock()



        if not self.piper.exists():

            raise FileNotFoundError(

                "Piper executable missing."

            )



        if not self.model.exists():

            raise FileNotFoundError(

                "Piper voice model missing."

            )



        logger.info(
            "NEXUS Piper voice ready."
        )





    def speak(self, text):


        if not text:

            return



        with self.lock:


            try:


                output = tempfile.NamedTemporaryFile(

                    suffix=".wav",

                    delete=False

                )


                output.close()



                subprocess.run(

                    [

                        str(self.piper),

                        "--model",

                        str(self.model),

                        "--output_file",

                        output.name

                    ],

                    input=text,

                    text=True,

                    check=True

                )



                os.startfile(

                    output.name

                )



            except Exception as e:


                logger.error(

                    f"Piper error: {e}"

                )





speaker = NexusSpeaker()
