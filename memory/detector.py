import re



class MemoryDetector:


    def detect(
        self,
        text
    ):

        if not text:

            return None



        text = text.lower().strip()



        patterns = [

            r"remember my (.+?) is (.+)",

            r"my (.+?) is (.+)",

            r"remember that my (.+?) is (.+)"

        ]



        for pattern in patterns:


            match = re.search(
                pattern,
                text
            )


            if match:

                key = match.group(1).strip()

                value = match.group(2).strip()


                return {

                    "key": key,

                    "value": value

                }


        return None
