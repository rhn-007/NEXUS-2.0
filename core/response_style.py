"""
NEXUS Response Style Controller

Refines AI responses to sound more like
a personal assistant.
"""


from utils.logger import setup_logger


logger = setup_logger(__name__)





class ResponseStyleController:



    def __init__(self):

        logger.info(
            "Response style controller ready"
        )





    def refine(
        self,
        response
    ):


        if not response:

            return response



        response = response.strip()



        # ==========================
        # REMOVE ROBOTIC OPENINGS
        # ==========================


        replacements = {


            "As an AI language model,": "",


            "As an AI,": "",


            "I don't have personal relationships or memories,": "",


            "I don't have feelings, but": "",


            "It seems like": "",


            "It appears that": "",


            "I would be happy to help": "I'll help you with that",


            "Sure!": "",


            "Certainly!": "",


            "Of course!": ""

        }



        for old,new in replacements.items():


            response = response.replace(

                old,

                new

            )





        # ==========================
        # CLEAN SPACING
        # ==========================


        response = response.strip()



        while "\n\n\n" in response:


            response = response.replace(

                "\n\n\n",

                "\n\n"

            )





        # ==========================
        # LIMIT EXCESSIVE LENGTH
        # ==========================


        lines = response.split("\n")



        if len(lines) > 12:


            response = "\n".join(

                lines[:12]

            )



        return response
