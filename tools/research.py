"""
NEXUS Internet Research Tool

Uses a visible Playwright-controlled Chromium browser to search the web,
extract readable page content, summarize sources with the configured
language model, and store source material as unverified knowledge.
"""

import ipaddress
import logging
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from tools.base import BaseTool
from tools.response import ToolResponse
from research.pipeline import ResearchPipeline


logger = logging.getLogger(__name__)


class ResearchTool(BaseTool):

    name = "research"

    description = (
        "Researches a topic using a visible browser, extracts information "
        "from webpages, summarizes sources, and stores findings."
    )

    def __init__(self, knowledge_engine, llm):
        self.knowledge = knowledge_engine
        self.llm = llm
        self.research_pipeline = ResearchPipeline(llm)
        self.max_results = 4
        self.max_page_chars = 6000
        self.navigation_timeout = 30000

        # Research runs in Opera with its own profile, keeping the user's
        # normal Opera profile and personal tabs separate.
        self.browser_path = (
            Path.home()
            / "AppData"
            / "Local"
            / "Programs"
            / "Opera"
            / "opera.exe"
        )
        self.browser_profile = (
            Path.home()
            / "AppData"
            / "Local"
            / "NEXUS"
            / "research-opera-profile"
        )
        self.cdp_endpoint = "http://127.0.0.1:9223"

    def can_handle(self, query):
        if not query:
            return False

        text = query.lower().strip()

        prefixes = (
            "research ",
            "research about ",
            "learn about ",
            "find information about ",
            "find out about "
        )

        return text.startswith(prefixes)

    def _extract_topic(self, query):
        text = query.strip()

        prefixes = (
            "research about ",
            "research ",
            "learn about ",
            "find information about ",
            "find out about "
        )

        lowered = text.lower()

        for prefix in prefixes:
            if lowered.startswith(prefix):
                return text[len(prefix):].strip()

        return ""

    def _is_public_http_url(self, url):
        try:
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https"):
                return False

            if not parsed.hostname:
                return False

            host = parsed.hostname.lower()

            if host in ("localhost", "localhost.localdomain"):
                return False

            try:
                address = ipaddress.ip_address(host)
                return address.is_global
            except ValueError:
                pass

            addresses = socket.getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM
            )

            return bool(addresses) and all(
                ipaddress.ip_address(item[4][0]).is_global
                for item in addresses
            )

        except (ValueError, OSError):
            return False

    def _guard_browser_request(self, route):
        """Prevent browser requests to local or non-public network addresses."""
        url = route.request.url
        scheme = urlparse(url).scheme.lower()

        if scheme in ("data", "blob", "about"):
            route.continue_()
            return

        if scheme not in ("http", "https"):
            route.abort()
            return

        if not self._is_public_http_url(url):
            logger.warning("Blocked non-public browser request: %s", url)
            route.abort()
            return

        route.continue_()

    def _looks_like_challenge(self, page):
        try:
            title = page.title().lower()
            body = page.locator("body").inner_text(timeout=5000).lower()
            sample = f"{title} {body[:5000]}"
        except PlaywrightError:
            return False

        indicators = (
            "captcha",
            "verify you are human",
            "unusual traffic",
            "automated queries",
            "security check",
            "are you a robot",
            "access denied"
        )

        return any(indicator in sample for indicator in indicators)

    def _wait_for_manual_verification(self, page):
        print(
            "\nNEXUS research browser needs manual verification. "
            "Complete the check in the Chromium window, then press "
            "Enter here to continue."
        )

        try:
            input("Press Enter after completing verification...")
        except (EOFError, KeyboardInterrupt):
            return False

        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=10000
            )
            page.wait_for_timeout(1000)
        except PlaywrightError:
            pass

        return not self._looks_like_challenge(page)

    def _normalize_result_url(self, url, base_url):
        url = urljoin(base_url, url)
        parsed = urlparse(url)

        if "duckduckgo.com" in (parsed.hostname or ""):
            target = parse_qs(parsed.query).get("uddg")

            if target:
                url = unquote(target[0])

        return url

    def _search_web(self, page, topic):
        search_url = (
            "https://html.duckduckgo.com/html/?q="
            + quote_plus(topic)
        )

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=self.navigation_timeout
        )
        page.wait_for_timeout(1200)

        if self._looks_like_challenge(page):
            if not self._wait_for_manual_verification(page):
                return []

        results = []
        seen_urls = set()
        links = page.locator("a.result__a")

        try:
            links.first.wait_for(
                state="attached",
                timeout=10000
            )
        except PlaywrightTimeoutError:
            return results

        for index in range(min(links.count(), 30)):
            link = links.nth(index)

            href = link.get_attribute("href")
            title = link.inner_text().strip()

            if not href or not title:
                continue

            url = self._normalize_result_url(href, page.url)

            if (
                not self._is_public_http_url(url)
                or url in seen_urls
            ):
                continue

            results.append({
                "title": title,
                "url": url
            })
            seen_urls.add(url)

            if len(results) >= self.max_results:
                break

        return results

    def _extract_page(self, page, url):
        if not self._is_public_http_url(url):
            return None

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.navigation_timeout
        )
        page.wait_for_timeout(700)

        if self._looks_like_challenge(page):
            if not self._wait_for_manual_verification(page):
                return None

        final_url = page.url

        if not self._is_public_http_url(final_url):
            return None

        soup = BeautifulSoup(page.content(), "html.parser")

        for element in soup.select(
            "script, style, nav, footer, header, "
            "form, noscript, svg, iframe, aside"
        ):
            element.decompose()

        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else urlparse(final_url).netloc
        )

        main = soup.find("main") or soup.find("article") or soup.body

        if not main:
            return None

        text = main.get_text(" ", strip=True)
        text = " ".join(text.split())

        if len(text) < 250:
            return None

        return {
            "title": title[:250],
            "url": final_url,
            "source": urlparse(final_url).netloc,
            "content": text[:self.max_page_chars]
        }

    def _connect_to_opera(self, playwright):
        """Connect to the dedicated Opera research instance over CDP."""
        try:
            return playwright.chromium.connect_over_cdp(
                self.cdp_endpoint,
                timeout=3000
            )
        except PlaywrightError:
            pass

        if not self.browser_path.exists():
            raise FileNotFoundError(
                f"Opera was not found at: {self.browser_path}"
            )

        self.browser_profile.mkdir(
            parents=True,
            exist_ok=True
        )

        command = [
            str(self.browser_path),
            "--remote-debugging-port=9223",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.browser_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ]

        subprocess.Popen(command, shell=False)

        last_error = None

        for _ in range(20):
            try:
                return playwright.chromium.connect_over_cdp(
                    self.cdp_endpoint,
                    timeout=3000
                )
            except PlaywrightError as error:
                last_error = error
                time.sleep(0.5)

        raise PlaywrightError(
            f"Could not connect to Opera's debugging endpoint: {last_error}"
        )

    def _collect_pages(self, topic):
        with sync_playwright() as playwright:
            browser = self._connect_to_opera(playwright)

            try:
                if not browser.contexts:
                    raise PlaywrightError(
                        "Opera did not provide a browser context."
                    )

                context = browser.contexts[0]
                page = context.new_page()

                try:
                    # Apply the request guard only to NEXUS's research tab,
                    # not to the user's other tabs in the same Opera instance.
                    page.route(
                        "**/*",
                        self._guard_browser_request
                    )

                    search_results = self._search_web(page, topic)

                    if not search_results:
                        return []

                    pages = []

                    for result in search_results:
                        try:
                            extracted = self._extract_page(
                                page,
                                result["url"]
                            )

                            if extracted:
                                pages.append(extracted)

                        except PlaywrightError as error:
                            logger.warning(
                                "Could not retrieve research page %s: %s",
                                result["url"],
                                error
                            )

                    return pages

                finally:
                    if not page.is_closed():
                        page.close()

            finally:
                # Disconnect Playwright without shutting down Opera.
                browser.close()

    def execute(self, query):
        topic = self._extract_topic(query)

        if not topic or len(topic) > 150:
            return ToolResponse.failure(
                "Please provide a research topic of up to 150 characters."
            )

        try:
            pages = self._collect_pages(topic)

            if not pages:
                return ToolResponse.failure(
                    "I couldn't extract usable research pages. "
                    "A search challenge may need to be completed, or "
                    "the search engine may not have returned results."
                )

            summary, session_id, accepted_count = (
                self.research_pipeline.analyse_and_store(
                    topic=topic,
                    query=query,
                    pages=pages,
                    depth="adaptive"
                )
            )

            if not summary:
                return ToolResponse.failure(
                    "I found webpages, but none produced enough relevant "
                    "evidence for a reliable research summary. The extracted "
                    "pages were not presented as verified findings."
                )

            saved_count = 0

            for page in pages:
                knowledge_id = self.knowledge.save_knowledge(
                    topic=topic,
                    title=page["title"],
                    content=page["content"],
                    source_url=page["url"],
                    source_name=page["source"],
                    confidence=0.0,
                    verification_status="unverified",
                    tags="web research"
                )

                if knowledge_id is not None:
                    saved_count += 1

            result_message = (
                f"Research results for: {topic}\n\n"
                f"{summary}\n\n"
                f"Sources extracted: {len(pages)}\n"
                f"New knowledge entries saved: {saved_count}\n"
                "Saved entries remain UNVERIFIED until reviewed."
            )

            self.knowledge.record_activity(
                activity="web_research_completed",
                topic=topic,
                details=(
                    f"Extracted {len(pages)} sources; "
                    f"saved {saved_count} new entries."
                ),
                status="completed"
            )

            return ToolResponse.success(result_message)

        except PlaywrightError as error:
            logger.error("Internet research browser failed: %s", error)
            self.knowledge.record_activity(
                activity="web_research_failed",
                topic=topic,
                details=str(error),
                status="failed"
            )
            return ToolResponse.failure(
                "Internet research could not complete in Opera. "
                "Check your internet connection and browser installation."
            )

        except Exception as error:
            logger.exception("Internet research failed.")
            self.knowledge.record_activity(
                activity="web_research_failed",
                topic=topic,
                details=str(error),
                status="failed"
            )
            return ToolResponse.failure(
                "I encountered an error while researching that topic."
            )
