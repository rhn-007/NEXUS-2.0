"""
NEXUS Memory Detector

Extracts user facts from messages.
"""

import re



class MemoryDetector:



    def detect(
        self,
        text
    ):


        if not text:

            return []



        text = text.strip()



        memories = []



        patterns = [


            (
                r"my name is (.+)",
                "name"
            ),



            (
                r"i am (.+)",
                "name"
            ),



            (
                r"my favourite colour is (.+)",
                "favorite_colour"
            ),



            (
                r"my favorite colour is (.+)",
                "favorite_colour"
            ),



            (
                r"my favourite color is (.+)",
                "favorite_colour"
            ),



            (
                r"i like (.+)",
                "interest"
            ),



            (
                r"i love (.+)",
                "interest"
            )

        ]



        lower = text.lower()



        for pattern, key in patterns:


            match = re.search(

                pattern,

                lower

            )


            if match:


                value = match.group(1).strip()



                memories.append(

                    {

                        "key": key,

                        "value": value

                    }

                )



        return memories
