import subprocess
from pathlib import Path


piper = Path("piper/piper.exe")

model = Path(
    "voice/models/en_US-ryan-high.onnx"
)


output = "test_voice.wav"



text = """
Hello Rohan.
I am NEXUS.
All systems are now online.
"""


subprocess.run(

    [

        str(piper),

        "--model",

        str(model),

        "--output_file",

        output

    ],

    input=text,

    text=True,

    check=True

)


print(
    "Voice generated:",
    output
)
