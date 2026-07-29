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

            # my name is rohan
            r"my name is (.+)",


            # i am rohan
            r"i am (.+)",


            # i like anime
            r"i like (.+)",


            # i love python
            r"i love (.+)",


            # my favourite colour is black
            r"my favorite (.+?) is (.+)",


            # my favourite colour is black (British spelling)
            r"my favourite (.+?) is (.+)",


            # remember that my hobby is coding
            r"remember (?:that )?my (.+?) is (.+)",


        ]




        for pattern in patterns:


            match = re.search(

                pattern,

                text

            )


            if match:


                groups = match.groups()



                # --------------------------
                # Name
                # --------------------------

                if "name" in pattern:


                    return {

                        "key": "name",

                        "value": groups[0].strip()

                    }



                # --------------------------
                # Likes
                # --------------------------

                if "like" in pattern or "love" in pattern:


                    return {

                        "key": "interest",

                        "value": groups[0].strip()

                    }



                # --------------------------
                # Favourite things
                # --------------------------

                if "favorite" in pattern or "favourite" in pattern:


                    return {

                        "key": groups[0].strip(),

                        "value": groups[1].strip()

                    }



                # --------------------------
                # General memory
                # --------------------------

                if len(groups) == 2:


                    return {

                        "key": groups[0].strip(),

                        "value": groups[1].strip()

                    }



        return None
