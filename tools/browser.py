
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
import os

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

        if text.startswith("spotify search "):
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
    # SPOTIFY SEARCH
    # ======================================================

    def search_spotify(self, search):
        """Clean a Spotify command and open its desktop-app search URI."""

        startfile = getattr(os, "startfile", None)

        if startfile is None:
            return ToolResponse.failure(
                "Spotify app search is only supported on Windows."
            )

        try:
            # Match the old Spotify integration: remove command words from
            # the incoming text before encoding the actual search term.
            # Word boundaries avoid damaging titles such as "Coldplay".
            search = re.sub(
                r"\\b(?:play|open|search|find|spotify)\\b",
                " ",
                str(search or ""),
                flags=re.IGNORECASE
            )
            search = re.sub(r"\\s+on\\s+spotify\\b", " ", search, flags=re.IGNORECASE)
            search = re.sub(r"(?<=\\w)\\+(?=\\w)", " ", search)
            search = re.sub(r"\\s+", " ", search).strip()

            if not search:
                return ToolResponse.failure(
                    "What would you like me to search for on Spotify?"
                )

            # quote() encodes spaces as %20, the expected form for Spotify's
            # spotify:search: URI. Literal symbols remain safely encoded.
            uri = "spotify:search:" + quote(search, safe="")
            startfile(uri)
            return ToolResponse.success(f"Searching Spotify for {search}.")
        except Exception as error:
            logger.error("Spotify search error: %s", error)
            return ToolResponse.failure(
                "I couldn't open that search in the Spotify app."
            )

    # ======================================================
    # EXECUTE REQUEST
    # ======================================================

    def execute(self, query):

        text = query.lower().strip()

        try:

            # Send searches to the installed Spotify desktop application.
            if text.startswith("spotify search "):
                # Pass the complete command so search_spotify applies the
                # same command-word cleanup used by the previous integration.
                return self.search_spotify(query)

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

            # Open direct URLs. An explicit link wins over a site name
            # inside it, so a YouTube search link is not read as "youtube".
            url_match = re.search(
                r"https?://[^\s]+",
                query
            )

            if url_match:
                return self.open_opera(
                    url_match.group(0)
                )

            # Open known websites.
            for name, url in self.websites.items():

                if name in text:
                    return self.open_opera(url)

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
