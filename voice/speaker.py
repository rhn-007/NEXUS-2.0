import subprocess
import uuid
from pathlib import Path
import winsound

from utils.logger import setup_logger


logger = setup_logger(__name__)


class Speaker:


    def __init__(self):

        self.piper = Path(
            "piper/piper.exe"
        )

        self.model = Path(
            "voice/models/en_GB-alan-medium.onnx"
        )

        logger.info(
            "Voice system ready"
        )



    def fix_pronunciation(
        self,
        text
    ):

        replacements = {

            "Rohan": "Row-hen",

            "rohan": "Row-hen",

            "ROHAN": "Row-hen",

            "NEXUS": "Nexus",

            "Python": "Pie-thon"

        }


        for word, replacement in replacements.items():

            text = text.replace(
                word,
                replacement
            )


        return text




    def speak(
        self,
        text
    ):


        if not text:

            return



        # Fix pronunciation before TTS

        text = self.fix_pronunciation(
            text
        )



        try:


            filename = (
                f"voice_{uuid.uuid4().hex}.wav"
            )


            output = Path(filename)



            command = [

                str(self.piper),

                "--model",
                str(self.model),

                "--output_file",
                str(output),

                "--length_scale",
                "0.90",

                "--noise_scale",
                "0.15",

                "--noise_w",
                "0.3",

                "--sentence_silence",
                "0.2"

            ]



            subprocess.run(

                command,

                input=text,

                text=True,

                check=True

            )



            winsound.PlaySound(

                str(output),

                winsound.SND_FILENAME

            )



            output.unlink()



        except Exception as e:


            logger.error(

                f"Voice error: {e}"

            )
