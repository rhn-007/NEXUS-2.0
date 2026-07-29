from utils.logger import setup_logger
from core.config import Config



logger = setup_logger(__name__)



class NexusAssistant:


    def __init__(self):

        self.name = Config.APP_NAME

        self.version = Config.VERSION


        logger.info(
            "NEXUS core initialized"
        )



    def start(self):

        logger.info(
            f"{self.name} {self.version} ready."
        )


        print(
            "\n🤖 N.E.X.U.S 2.0 Online\n"
        )


        print(
            "System foundation loaded successfully."
        )
