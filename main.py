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



    try:


        assistant.start()



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


        animation.stop()

        clear_status()






if __name__ == "__main__":


    main()
