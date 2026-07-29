import logging
import sys


def setup_logger(name):

    logger = logging.getLogger(name)


    if logger.handlers:

        return logger


    logger.setLevel(
        logging.INFO
    )


    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


    console = logging.StreamHandler(
        sys.stdout
    )


    console.setFormatter(
        formatter
    )


    logger.addHandler(
        console
    )


    return logger
