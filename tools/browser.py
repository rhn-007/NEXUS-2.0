
"""
NEXUS Browser Tool

Handles:
- Opening websites
- Opening URLs
- Google searches
- Opening WhatsApp Web in Opera
"""

import webbrowser
import subprocess
import re
import logging

from urllib.parse import quote

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):

    name = "browser"

    description = (
        "Opens websites, URLs and performs web searches."
    )

    def __init__(self):

        self.websites = {

            "youtube": "https://youtube.com",
            "google": "https://google.com",
            "github": "https://github.com",
            "wikipedia": "https://wikipedia.org",
            "reddit": "https://reddit.com",
            "chatgpt": "https://chatgpt.com",
            "instagram": "https://instagram.com",
            "whatsapp web": "https://web.whatsapp.com"

        }

        self.browser_path = None

    # ======================================================
    # DETECT REQUEST
    # ======================================================

    def can_handle(self, query):

        if not query:

            return False

        text = query.lower().strip()

        # Application commands belong to ApplicationTool.
        application_names = [
            "spotify",
            "calculator",
            "whatsapp",
            "notepad",
            "word",
            "excel",
            "idle",
            "python idle",
            "file explorer"
        ]

        if any(
            name in text
            for name in application_names
        ):

            # Allow explicit WhatsApp Web requests.
            if "whatsapp web" in text:

                return True

            return False

        browser_phrases = [
            "open website",
            "open browser",
            "open url",
            "go to",
            "visit",
            "browse",
            "search",
            "google"
        ]

        return any(
            phrase in text
            for phrase in browser_phrases
        )

    # ======================================================
    # EXECUTE
    # ======================================================

    def execute(self, query):

        text = query.lower().strip()

        try:

            # ==============================================
            # WHATSAPP WEB
            # ==============================================

            if "whatsapp web" in text:

                return self.open_whatsapp_web()

            # ==============================================
            # OPEN KNOWN WEBSITES
            # ==============================================

            for name, url in self.websites.items():

                if name in text:

                    if name == "whatsapp web":
                        continue

                    webbrowser.open(url)

                    logger.info(
                        f"Opened website: {name}"
                    )

                    return ToolResponse.success(
                        f"Opened {name}."
                    )

            # ==============================================
            # EXTRACT URL
            # ==============================================

            url_match = re.search(
                r"https?://[^\s]+",
                query
            )

            if url_match:

                url = url_match.group(0)

                webbrowser.open(url)

                logger.info(
                    f"Opened URL: {url}"
                )

                return ToolResponse.success(
                    f"Opened {url}."
                )

            # ==============================================
            # GOOGLE SEARCH
            # ==============================================

            search = text

            search_prefixes = [
                "search google for",
                "search for",
                "search",
                "look up",
                "google"
            ]

            for phrase in search_prefixes:

                if search.startswith(phrase):

                    search = search[len(phrase):].strip()

                    break

            if search:

                url = (
                    "https://www.google.com/search?q="
                    + quote(search)
                )

                webbrowser.open(url)

                logger.info(
                    f"Google search: {search}"
                )

                return ToolResponse.success(
                    f"Searching Google for {search}."
                )

            return ToolResponse.failure(
                "I couldn't understand the browser request."
            )

        except Exception as e:

            logger.error(
                f"Browser error: {e}"
            )

            return ToolResponse.failure(
                f"I couldn't complete the browser request: {e}"
            )

    # ======================================================
    # OPEN WHATSAPP WEB IN OPERA
    # ======================================================

    def open_whatsapp_web(self):

        try:

            subprocess.Popen(
                [
                    "explorer.exe",
                    "https://web.whatsapp.com"
                ],
                shell=False
            )

            logger.info(
                "Opened WhatsApp Web using Windows URL handler."
            )

            return ToolResponse.success(
                "Opening WhatsApp Web."
            )

        except Exception as e:

            logger.error(
                f"WhatsApp Web launch error: {e}"
            )

            return ToolResponse.failure(
                f"Couldn't open WhatsApp Web: {e}"
            )
