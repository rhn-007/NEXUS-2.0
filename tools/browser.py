"""
NEXUS Browser Tool

Handles:
- Opening websites
- Opening URLs
- Web searches
"""


import webbrowser
from urllib.parse import quote

import re

from tools.base import BaseTool
from tools.response import ToolResponse



class BrowserTool(BaseTool):


    name = "browser"


    description = (
        "Opens websites and performs web searches."
    )



    def __init__(self):

        self.websites = {

            "youtube":
                "https://youtube.com",

            "google":
                "https://google.com",

            "github":
                "https://github.com",

            "wikipedia":
                "https://wikipedia.org",

            "reddit":
                "https://reddit.com",

            "chatgpt":
                "https://chatgpt.com",

            "instagram":
                "https://instagram.com"

        }



    # =====================================
    # DETECT REQUEST
    # =====================================

    def can_handle(
        self,
        query
    ):


        if not query:

            return False



        text = query.lower()



        keywords = [

            "open",

            "go to",

            "visit",

            "browse",

            "search",

            "google"

        ]



        return any(

            word in text

            for word in keywords

        )



    # =====================================
    # EXECUTE
    # =====================================

    def execute(
        self,
        query
    ):


        text = query.lower().strip()



        # Open known websites

        for name, url in self.websites.items():


            if name in text:


                webbrowser.open(
                    url
                )


                return ToolResponse.success(

                    f"Opened {name}."

                )



        # Extract URL


        url_match = re.search(

            r"https?://[^\s]+",

            text

        )



        if url_match:


            url = url_match.group(0)


            webbrowser.open(
                url
            )


            return ToolResponse.success(

                f"Opened {url}"

            )



        # Search


        search_words = [

            "search",

            "google",

            "look up"

        ]



        search = text


        for word in search_words:

            search = search.replace(
                word,
                ""
            )



        search = search.strip()



        if search:


            url = (

                "https://www.google.com/search?q="

                + quote(search)

            )


            webbrowser.open(
                url
            )


            return ToolResponse.success(

                f"Searching for {search}"

            )



        return ToolResponse.failure(

            "I could not understand the browser request."

        )
