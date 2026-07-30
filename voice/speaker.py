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
            "voice/models/en_GB-northern_english_male-medium.onnx"
        )

        logger.info(
            "Voice system ready"
        )

    def fix_pronunciation(self, text):

        replacements = {
    
            "Rohan": "Row-han",
    
            "ROHAN": "Row-han",
    
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
            text = self.fix_pronunciation(text)



        try:


            # Create temporary audio file

            filename = (
                f"voice_{uuid.uuid4().hex}.wav"
            )


            output = Path(filename)



            # Piper settings

            command = [

                str(self.piper),

                "--model",
                str(self.model),

                "--output_file",
                str(output),

                "--length_scale",
                "1.1",

                "--noise_scale",
                "0.25",

                "--sentence_silence",
                "0.4"

                "--noise_w",
                "0.5",

            ]



            subprocess.run(

                command,

                input=text,

                text=True,

                check=True

            )



            # Play audio

            winsound.PlaySound(

                str(output),

                winsound.SND_FILENAME

            )



            # Delete file

            output.unlink()



        except Exception as e:


            logger.error(

                f"Voice error: {e}"

            )
