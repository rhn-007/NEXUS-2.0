"""
NEXUS Speech Recognition System
Faster-Whisper Listener
"""


from faster_whisper import WhisperModel

import sounddevice as sd
import numpy as np

import scipy.io.wavfile as wav

from pathlib import Path
import tempfile



class Listener:


    def __init__(self):


        print("Loading Whisper model...")


        self.model = WhisperModel(

            "medium.en",

            device="cpu",

            compute_type="int8"

        )


        print("Listener ready.")




    def record_audio(

        self,

        duration=5,

        samplerate=16000

    ):


        print("\nListening...")


        audio = sd.rec(

            int(duration * samplerate),

            samplerate=samplerate,

            channels=1,

            dtype="float32"

        )


        sd.wait()


        print("Processing...")


        return audio.flatten()




    def transcribe(

        self,

        audio,

        samplerate=16000

    ):


        temp_file = Path(

            tempfile.gettempdir()

        ) / "nexus_audio.wav"



        wav.write(

            temp_file,

            samplerate,

            audio

        )



        segments, info = self.model.transcribe(

            str(temp_file)

        )



        text = ""


        for segment in segments:

            text += segment.text



        return text.strip()




    def listen(self):


        audio = self.record_audio()


        text = self.transcribe(

            audio

        )


        return text





if __name__ == "__main__":


    listener = Listener()



    while True:


        text = listener.listen()



        print(

            "\nYou said:",

            text

        )
