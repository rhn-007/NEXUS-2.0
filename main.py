"""
NEXUS 2.0
Main Entry Point
"""


from core.assistant import NexusAssistant
from utils.logger import setup_logger
from ui.animation import animation
from ui.status import clear_status


logger = setup_logger(__name__)


def main():

    logger.info(
        "Starting NEXUS..."
    )


    assistant = NexusAssistant()


    animation.start()


    print(
        "\n🤖 N.E.X.U.S 2.0 Online\n"
    )


    try:

        while True:


            user_input = input(
                "You: "
            )


            if user_input.lower() in [
                "exit",
                "quit"
            ]:

                print(
                    "Goodbye 👋"
                )

                break



            if not user_input.strip():

                continue



            response = assistant.process_input(
                user_input
            )


            clear_status()


            print(
                "\nNEXUS:",
                response,
                "\n"
            )



    except KeyboardInterrupt:


        print(
            "\nGoodbye 👋"
        )


    except Exception as e:


        logger.error(
            f"Main loop error: {e}"
        )

        print(
            f"Error: {e}"
        )


    finally:


        clear_status()

        animation.stop()



if __name__ == "__main__":

    main()
