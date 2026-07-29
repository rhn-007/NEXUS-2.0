import re



class MemoryDetector:



    def detect(
        self,
        text
    ):


        if not text:

            return []



        text = text.lower().strip()



        memories = []



        # ==========================
        # NAME
        # ==========================

        name_match = re.search(
            r"(?:my name is|i am|i'm)\s+([a-zA-Z]+)",
            text
        )


        if name_match:


            memories.append(

                {
                    "key": "name",

                    "value": name_match.group(1).strip()

                }

            )





        # ==========================
        # LIKES / INTERESTS
        # ==========================


        likes = re.findall(

            r"(?:i like|i love|i enjoy)\s+([^.,]+)",

            text

        )


        for item in likes:


            memories.append(

                {
                    "key": "interest",

                    "value": item.strip()

                }

            )







        # ==========================
        # FAVORITE ANIME / THINGS
        # ==========================


        favourite_matches = re.findall(

            r"(?:my favorite|my favourite)\s+(.+?)\s+is\s+([^.,]+)",

            text

        )


        for key, value in favourite_matches:


            key = key.strip().replace(
                " ",
                "_"
            )


            memories.append(

                {
                    "key": key,

                    "value": value.strip()

                }

            )







        # ==========================
        # CODING / SKILLS
        # ==========================


        coding = re.search(

            r"(?:coding|programming|language).*?(?:python|java|c\+\+|javascript)",

            text

        )


        if coding:


            memories.append(

                {
                    "key": "coding",

                    "value": "Python"

                }

            )







        # ==========================
        # PROJECTS
        # ==========================


        project = re.search(

            r"(?:working on|building|creating)\s+(.+?)(?:\.|,|and|$)",

            text

        )


        if project:


            memories.append(

                {
                    "key": "project",

                    "value": project.group(1).strip()

                }

            )







        # ==========================
        # REMOVE DUPLICATES
        # ==========================


        unique = []


        seen = set()


        for memory in memories:


            identifier = (

                memory["key"],

                memory["value"]

            )


            if identifier not in seen:


                seen.add(identifier)

                unique.append(memory)




        return unique
