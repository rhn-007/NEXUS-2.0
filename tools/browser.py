
"""
NEXUS Browser Tool

Handles:
- Launching Opera
- Opening websites in Opera
- Opening URLs in Opera
- Google searches in Opera
- Opening WhatsApp Web in Opera
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

    description = "Launches Opera and opens websites and performs searches."

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
            "youtube": "https://youtube.com",
            "google": "https://google.com",
            "github": "https://github.com",
            "wikipedia": "https://wikipedia.org",
            "reddit": "https://reddit.com",
            "chatgpt": "https://chatgpt.com",
            "instagram": "https://instagram.com",
            "whatsapp web": "https://web.whatsapp.com"
        }

    # ======================================================
    # DETECT REQUEST
    # ======================================================

    def can_handle(self, query):

        if not query:
            return False

        text = query.lower().strip()

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

        if any(name in text for name in application_names):

            if "whatsapp web" in text:
                return True

            return False

        browser_phrases = [
            "open browser",
            "launch browser",
            "start browser",
            "open website",
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
                    f"Opening {url} in Opera."
                )

            return ToolResponse.success(
                "Opening Opera."
            )

        except Exception as e:

            logger.error(f"Opera launch error: {e}")

            return ToolResponse.failure(
                f"Couldn't open Opera: {e}"
            )

    # ======================================================
    # EXECUTE REQUEST
    # ======================================================

    def execute(self, query):

        text = query.lower().strip()

        try:

            # Open browser without a website.
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
                    "https://web.whatsapp.com"
                )

            # Open known websites.
            for name, url in self.websites.items():

                if name in text:

                    return self.open_opera(url)

            # Open a direct URL.
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

                    if search:

                        url = (
                            "https://www.google.com/search?q="
                            + quote(search)
                        )

                        return self.open_opera(url)

                    return ToolResponse.failure(
                        "What would you like me to search for?"
                    )

            return ToolResponse.failure(
                "I couldn't understand the browser request."
            )

        except Exception as e:

            logger.error(f"Browser error: {e}")

            return ToolResponse.failure(
                f"I couldn't complete the browser request: {e}"
            )
