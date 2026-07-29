import pyttsx3


engine = pyttsx3.init()


voices = engine.getProperty("voices")


# Select Hazel

for voice in voices:

    if "Hazel" in voice.name:

        engine.setProperty(
            "voice",
            voice.id
        )

        break



engine.setProperty(
    "rate",
    155
)


engine.setProperty(
    "volume",
    1.0
)



engine.say(
    "Hello Rohan. I am NEXUS. Voice systems are now online."
)


engine.runAndWait()
