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

        name = re.search(
            r"(?:my name is|i am|i'm)\s+([a-z]+)",
            text
        )


        if name:


            value = name.group(1)


            if value not in [

                "currently",
                "working",
                "a",
                "the"

            ]:


                memories.append(

                    {
                        "key": "name",

                        "value": value

                    }

                )







        # ==========================
        # INTERESTS
        # ==========================

        interests = re.findall(

            r"(?:i like|i love|i enjoy)\s+([^.,]+)",

            text

        )


        for item in interests:


            memories.append(

                {
                    "key": "interest",

                    "value": item.strip()

                }

            )







        # ==========================
        # FAVORITES
        # ==========================

        favorites = re.findall(

            r"my favorite ([a-z ]+) is ([^.,]+)",

            text

        )


        for key,value in favorites:


            memories.append(

                {
                    "key": key.strip().replace(
                        " ",
                        "_"
                    ),

                    "value": value.strip()

                }

            )







        # ==========================
        # CODING
        # ==========================

        if re.search(

            r"coding|programming|python",

            text

        ):


            if "python" in text:


                memories.append(

                    {
                        "key": "coding",

                        "value": "python"

                    }

                )







        # ==========================
        # PROJECT
        # ==========================

        if re.search(

            r"working on a project|working on my project",

            text

        ):


            memories.append(

                {
                    "key": "project",

                    "value": "a personal project"

                }

            )







        # ==========================
        # REMOVE DUPLICATES
        # ==========================

        result = []

        seen = set()


        for memory in memories:


            check = (

                memory["key"],

                memory["value"]

            )


            if check not in seen:


                seen.add(check)

                result.append(memory)



        return result
