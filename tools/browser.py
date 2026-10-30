
"""
NEXUS Browser Tool

Handles:
- Launching Opera
- Opening websites and URLs
- Google searches
- Opening WhatsApp Web
"""

import subprocess
import re
import logging

from pathlib import Path
from urllib.parse import quote

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):

    name = "browser"

    description = "Launches Opera, opens websites and performs searches."

    def __init__(self):

        self.browser_path = (
            Path.home()
            / "AppData"
            / "Local"
            / "Programs"
            / "Opera"
            / "opera.exe"
        )

        self.websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "wikipedia": "https://www.wikipedia.org",
            "reddit": "https://www.reddit.com",
            "chatgpt": "https://chatgpt.com",
            "instagram": "https://www.instagram.com",
            "whatsapp web": "https://web.whatsapp.com"
        }

    # ======================================================
    # DETECT REQUEST
    # ======================================================

    def can_handle(self, query):

        if not query:
            return False

        text = query.lower().strip()

        if "whatsapp web" in text:
            return True

        if text in [
            "open browser",
            "launch browser",
            "start browser",
            "open opera",
            "launch opera",
            "start opera"
        ]:
            return True

        if any(
            phrase in text
            for phrase in [
                "open youtube",
                "open google",
                "open github",
                "open wikipedia",
                "open reddit",
                "open chatgpt",
                "open instagram"
            ]
        ):
            return True

        if re.search(r"https?://[^\s]+", text):
            return True

        if text.startswith((
            "search ",
            "search for ",
            "search google for ",
            "look up ",
            "google "
        )):
            return True

        if text.startswith(("go to ", "visit ", "browse ")):
            return True

        return False

    # ======================================================
    # OPEN OPERA
    # ======================================================

    def open_opera(self, url=None):

        if not self.browser_path.exists():

            return ToolResponse.failure(
                "I couldn't find Opera on your computer."
            )

        try:

            command = [str(self.browser_path)]

            if url:
                command.append(url)

            subprocess.Popen(command, shell=False)

            if url:
                return ToolResponse.success(
                    "Opening the website in Opera."
                )

            return ToolResponse.success(
                "Opening Opera."
            )

        except Exception as e:

            logger.error(f"Opera launch error: {e}")

            return ToolResponse.failure(
                "I couldn't open Opera."
            )

    # ======================================================
    # EXECUTE REQUEST
    # ======================================================

    def execute(self, query):

        text = query.lower().strip()

        try:

            # Open Opera.
            if text in [
                "open browser",
                "launch browser",
                "start browser",
                "open opera",
                "launch opera",
                "start opera"
            ]:
                return self.open_opera()

            # Open WhatsApp Web.
            if "whatsapp web" in text:
                return self.open_opera(
                    self.websites["whatsapp web"]
                )

            # Open known websites.
            for name, url in self.websites.items():

                if name in text:
                    return self.open_opera(url)

            # Open direct URLs.
            url_match = re.search(
                r"https?://[^\s]+",
                query
            )

            if url_match:
                return self.open_opera(
                    url_match.group(0)
                )

            # Google search.
            search_prefixes = [
                "search google for",
                "search for",
                "search",
                "look up",
                "google"
            ]

            for phrase in search_prefixes:

                if text.startswith(phrase):

                    search = text[len(phrase):].strip()

                    if not search:
                        return ToolResponse.failure(
                            "What would you like me to search for?"
                        )

                    url = (
                        "https://www.google.com/search?q="
                        + quote(search)
                    )

                    result = self.open_opera(url)

                    if result.success:
                        return ToolResponse.success(
                            f"Searching Google for {search}."
                        )

                    return result

            # Go to / visit / browse a website.
            for phrase in ["go to ", "visit ", "browse "]:

                if text.startswith(phrase):

                    website = text[len(phrase):].strip()

                    if website in self.websites:
                        return self.open_opera(
                            self.websites[website]
                        )

                    if website:
                        return self.open_opera(
                            "https://www.google.com/search?q="
                            + quote(website)
                        )

            return ToolResponse.failure(
                "I couldn't understand the browser request."
            )

        except Exception as e:

            logger.error(f"Browser error: {e}")

            return ToolResponse.failure(
                "I couldn't complete the browser request."
            )
