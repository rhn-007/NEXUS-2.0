"""
NEXUS Intelligent Memory Detector
"""


import re



class MemoryDetector:



    def detect(
        self,
        text
    ):


        memories = []


        if not text:

            return memories



        text = text.strip()



        patterns = [


            (
                r"(?:my name is|i am)\s+([a-zA-Z]+)",
                "name",
                "profile"
            ),



            (
                r"my (?:favorite|favourite) (?:color|colour) is\s+(.+)",
                "favorite_colour",
                "profile"
            ),



            (
                r"(?:i like|i love|i enjoy)\s+(.+)",
                "interest",
                "interest"
            ),



            (
                r"(?:i am building|i am making|working on)\s+(.+)",
                "project",
                "project"
            ),



            (
                r"i use\s+(.+)",
                "technology",
                "interest"
            )


        ]



        for pattern, key, category in patterns:


            match = re.search(

                pattern,

                text,

                re.IGNORECASE

            )


            if match:


                value = match.group(1).strip()


                memories.append(

                    {

                        "key": key,

                        "value": value,

                        "category": category

                    }

                )



        return memories
