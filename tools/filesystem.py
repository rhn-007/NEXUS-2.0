"""Restricted Windows file and folder operations for NEXUS."""

import logging
import re
from pathlib import Path

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


class FileSystemTool(BaseTool):
    name = "filesystem"
    description = (
        "Lists approved folders, finds files by name, reads supported text "
        "files, and creates folders inside Desktop, Documents, or Downloads."
    )

    MAX_READ_BYTES = 100 * 1024
    MAX_SEARCH_RESULTS = 30
    ALLOWED_READ_SUFFIXES = {
        ".txt", ".md", ".csv", ".json", ".py", ".html", ".css", ".js"
    }
    BLOCKED_NAME_PARTS = {
        ".env", "credentials", "token", "password", "secret",
        "id_rsa", "private_key"
    }

    def __init__(self):
        home = Path.home()
        self.roots = {
            "desktop": home / "Desktop",
            "documents": home / "Documents",
            "downloads": home / "Downloads"
        }

    def can_handle(self, query):
        if not query:
            return False

        text = query.lower().strip()
        patterns = (
            r"^(?:list|show) (?:the )?(?:files|folders|contents)",
            r"^(?:find|search for) (?:a )?file\b",
            r"^read (?:the )?(?:text )?file\b",
            r"^create (?:a )?folder\b"
        )
        return any(re.search(pattern, text) for pattern in patterns)

    def _get_root(self, text):
        for name, path in self.roots.items():
            if re.search(r"\b" + name + r"\b", text, flags=re.IGNORECASE):
                return name, path
        return None, None

    @staticmethod
    def _is_within(path, root):
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except (ValueError, OSError):
            return False

    def _safe_target(self, root, relative_name):
        candidate = (root / relative_name).resolve(strict=False)
        if not self._is_within(candidate, root):
            return None
        return candidate

    def execute(self, query):
        text = query.strip()
        lowered = text.lower()

        try:
            if re.match(r"^(?:list|show) ", lowered):
                return self._list_folder(text)

            if re.match(r"^(?:find|search for) ", lowered):
                return self._find_file(text)

            if re.match(r"^read ", lowered):
                return self._read_file(text)

            if re.match(r"^create ", lowered):
                return self._create_folder(text)

            return ToolResponse.failure("I couldn't understand that file request.")

        except Exception as error:
            logger.exception("File-system operation failed")
            return ToolResponse.failure(
                f"I couldn't complete the file operation: {error}"
            )

    def _list_folder(self, query):
        name, root = self._get_root(query)
        if root is None:
            return ToolResponse.failure(
                "Please specify Desktop, Documents, or Downloads."
            )
        if not root.exists():
            return ToolResponse.failure(f"Your {name} folder was not found.")

        entries = sorted(
            root.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower())
        )
        if not entries:
            return ToolResponse.success(f"Your {name} folder is empty.")

        lines = []
        for item in entries[:self.MAX_SEARCH_RESULTS]:
            marker = "[Folder]" if item.is_dir() else "[File]"
            lines.append(f"{marker} {item.name}")

        suffix = ""
        if len(entries) > self.MAX_SEARCH_RESULTS:
            suffix = f"\nShowing first {self.MAX_SEARCH_RESULTS} of {len(entries)} items."

        return ToolResponse.success(
            f"Contents of {name.title()}:\n" + "\n".join(lines) + suffix,
            {"count": len(entries), "folder": name}
        )

    def _find_file(self, query):
        name, root = self._get_root(query)
        if root is None:
            return ToolResponse.failure(
                "Please specify where to search: Desktop, Documents, or Downloads."
            )
        if not root.exists():
            return ToolResponse.failure(f"Your {name} folder was not found.")

        match = re.search(
            r"^(?:find|search for) (?:a )?file\s+(.+?)\s+in\s+(?:my )?"
            + name + r"\s*$",
            query,
            flags=re.IGNORECASE
        )
        if not match:
            return ToolResponse.failure(
                "Use a request such as: find file report.pdf in Documents."
            )

        needle = match.group(1).strip().strip('"').strip("'")
        if not needle or any(part in needle.lower() for part in self.BLOCKED_NAME_PARTS):
            return ToolResponse.failure("That filename search isn't allowed.")

        results = []
        visited = 0
        for item in root.rglob("*"):
            visited += 1
            if visited > 5000:
                break
            try:
                if item.is_file() and needle.lower() in item.name.lower():
                    if self._is_within(item, root):
                        results.append(item)
                        if len(results) >= self.MAX_SEARCH_RESULTS:
                            break
            except OSError:
                continue

        if not results:
            return ToolResponse.success(
                f"I couldn't find a file matching '{needle}' in {name.title()}."
            )

        lines = [str(item.relative_to(root)) for item in results]
        return ToolResponse.success(
            f"Files matching '{needle}' in {name.title()}:\n"
            + "\n".join(lines),
            {"matches": len(results), "folder": name}
        )

    def _read_file(self, query):
        name, root = self._get_root(query)
        if root is None:
            return ToolResponse.failure(
                "Please specify whether the file is in Desktop, Documents, or Downloads."
            )

        match = re.search(
            r"^read (?:the )?(?:text )?file\s+(.+?)\s+in\s+(?:my )?"
            + name + r"\s*$",
            query,
            flags=re.IGNORECASE
        )
        if not match:
            return ToolResponse.failure(
                "Use a request such as: read file notes.txt in Documents."
            )

        relative_name = match.group(1).strip().strip('"').strip("'")
        if any(part in relative_name.lower() for part in self.BLOCKED_NAME_PARTS):
            return ToolResponse.failure("That file cannot be read by NEXUS.")

        target = self._safe_target(root, relative_name)
        if target is None or not target.is_file():
            return ToolResponse.failure("I couldn't find that file in the approved folder.")

        if target.suffix.lower() not in self.ALLOWED_READ_SUFFIXES:
            return ToolResponse.failure(
                "For safety, I can currently read only plain-text formats "
                "such as TXT, MD, CSV, JSON, PY, HTML, CSS, and JS."
            )

        try:
            size = target.stat().st_size
            if size > self.MAX_READ_BYTES:
                return ToolResponse.failure(
                    "That file is larger than the 100 KB reading limit."
                )

            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResponse.failure(
                "That file isn't valid UTF-8 text, so I couldn't read it safely."
            )

        return ToolResponse.success(
            f"Contents of {target.name}:\n{content}",
            {"file": target.name, "bytes": size}
        )

    def _create_folder(self, query):
        name, root = self._get_root(query)
        if root is None:
            return ToolResponse.failure(
                "Please specify Desktop, Documents, or Downloads."
            )

        match = re.search(
            r"^create (?:a )?folder\s+(.+?)\s+in\s+(?:my )?"
            + name + r"\s*$",
            query,
            flags=re.IGNORECASE
        )
        if not match:
            return ToolResponse.failure(
                "Use a request such as: create folder Robotics in Documents."
            )

        folder_name = match.group(1).strip().strip('"').strip("'")
        if (
            not folder_name
            or folder_name in (".", "..")
            or any(char in folder_name for char in '<>:"/\\|?*')
            or folder_name.endswith((".", " "))
            or any(part in folder_name.lower() for part in self.BLOCKED_NAME_PARTS)
        ):
            return ToolResponse.failure("That folder name isn't valid.")

        target = self._safe_target(root, folder_name)
        if target is None:
            return ToolResponse.failure("That folder location isn't allowed.")
        if target.exists():
            return ToolResponse.failure(
                f"A file or folder named '{folder_name}' already exists there."
            )

        target.mkdir(parents=False, exist_ok=False)
        logger.info("Created folder: %s", target)
        return ToolResponse.success(
            f"Created the folder '{folder_name}' in {name.title()}."
        )
