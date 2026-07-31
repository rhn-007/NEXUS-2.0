"""
NEXUS Speech Recognition System
Faster-Whisper Listener with Voice Activity Detection
"""


from faster_whisper import WhisperModel

import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav

import webrtcvad

from pathlib import Path
import tempfile
import time



class Listener:


    def __init__(self):


        print("Loading Whisper model...")


        self.model = WhisperModel(

            "medium.en",

            device="cpu",

            compute_type="int8"

        )


        self.vad = webrtcvad.Vad()

        self.vad.set_mode(2)


        self.sample_rate = 16000

        self.frame_duration = 30

        self.frame_size = int(

            self.sample_rate * self.frame_duration / 1000

        )


        print("Listener ready.")




    def is_speech(self, frame):


        return self.vad.is_speech(

            frame,

            self.sample_rate

        )




    def record_until_silence(self):


        print("\nWaiting...")


        audio_frames = []

        silence_count = 0

        speech_started = False



        stream = sd.RawInputStream(

            samplerate=self.sample_rate,

            blocksize=self.frame_size,

            dtype="int16",

            channels=1

        )



        with stream:


            while True:


                frame, overflow = stream.read(

                    self.frame_size

                )


                frame_bytes = bytes(frame)



                speech = self.is_speech(

                    frame_bytes

                )



                if speech:


                    speech_started = True

                    silence_count = 0

                    audio_frames.append(frame)



                elif speech_started:


                    silence_count += 1

                    audio_frames.append(frame)



                    # roughly 1 second silence

                    if silence_count > 33:

                        break



        print("Processing...")


        audio = np.frombuffer(

            b"".join(audio_frames),

            dtype=np.int16

        )


        return audio




    def transcribe(self, audio):


        temp_file = Path(

            tempfile.gettempdir()

        ) / "nexus_audio.wav"



        wav.write(

            temp_file,

            self.sample_rate,

            audio

        )



        segments, info = self.model.transcribe(

            str(temp_file),

            beam_size=5,

            language="en",

            vad_filter=True

        )



        text = ""



        for segment in segments:

            text += segment.text + " "



        text = text.strip()



        # =========================
        # NEXUS Vocabulary Fixes
        # =========================


        replacements = {


            "rowan": "Rohan",

            "rohan": "Rohan",


            "lexus": "NEXUS",

            "lexis": "NEXUS",
        
            "nexus": "NEXUS",
        
            "nex us": "NEXUS",
        
            "next us": "NEXUS",
        
            "nextus": "NEXUS",
        
            "nexis": "NEXUS",
        
            "nexis": "NEXUS",

            


            "ollama": "Ollama",

            "python": "Python"


        }



        for wrong, correct in replacements.items():


            text = text.replace(

                wrong,

                correct

            )



        return text




    def listen(self):


        audio = self.record_until_silence()


        if len(audio) == 0:

            return ""



        return self.transcribe(audio)






if __name__ == "__main__":


    listener = Listener()



    while True:


        text = listener.listen()



        if text:


            print(

                "\nYou said:",

                text

            )
