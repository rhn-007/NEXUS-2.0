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

            (
                r"my name is (.+)",
                "name"
            ),

            (
                r"i am (.+)",
                "name"
            ),

            (
                r"i'm (.+)",
                "name"
            ),

            (
                r"i like (.+)",
                "interest"
            ),

            (
                r"i love (.+)",
                "interest"
            ),

            (
                r"my favorite (.+?) is (.+)",
                None
            ),

            (
                r"my favourite (.+?) is (.+)",
                None
            ),

            (
                r"remember that my (.+?) is (.+)",
                None
            ),

            (
                r"my (.+?) is (.+)",
                None
            )

        ]



        for pattern, forced_key in patterns:



            match = re.search(

                pattern,

                text

            )



            if match:



                # Example:
                # my name is rohan

                if forced_key:


                    return {

                        "key": forced_key,

                        "value": match.group(1).strip()

                    }



                # Example:
                # my favourite color is black

                if len(match.groups()) == 2:


                    return {

                        "key": match.group(1).strip(),

                        "value": match.group(2).strip()

                    }



        return None
