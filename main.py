"""
NEXUS 2.0
Main Entry Point
"""


from core.assistant import NexusAssistant
from utils.logger import setup_logger


logger = setup_logger(__name__)


def main():

    logger.info(
        "Starting NEXUS..."
    )


    assistant = NexusAssistant()


    assistant.start()



if __name__ == "__main__":

    main()
