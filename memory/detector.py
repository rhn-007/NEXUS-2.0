"""Detect explicit facts and corrections in user messages."""

import re


class MemoryDetector:
    """Extract facts only when the user states them clearly."""

    def detect(self, text):
        if not text or not text.strip():
            return []

        text = text.strip()
        memories = []

        # Handle corrections first. Without this, "my name is not X.
        # It is Y" can incorrectly store "not" as the user's name.
        name_correction_patterns = [
            r"\bmy name\s+(?:is not|isn't)\b.*?\b(?:but\s+)?(?:it is|it's|it’s)\s+([a-z][a-z'-]*)",
            r"\bmy name is\s+not\s+[^.,;]+[,;]\s*(?:it is|it's|it’s)\s+([a-z][a-z'-]*)",
        ]

        corrected_name = None
        for pattern in name_correction_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                corrected_name = match.group(1)
                break

        if corrected_name:
            memories.append({
                "key": "name",
                "value": corrected_name.capitalize()
            })
        else:
            name_patterns = [
                r"\bmy name is\s+(?!not\b)([a-z][a-z'-]*)",
                r"\bI am\s+(?!not\b)([a-z][a-z'-]*)",
                r"\bI'm\s+(?!not\b)([a-z][a-z'-]*)",
            ]

            for pattern in name_patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = match.group(1)
                    if value.lower() not in {
                        "currently", "working", "a", "an", "the",
                        "not", "just", "trying"
                    }:
                        memories.append({
                            "key": "name",
                            "value": value.capitalize()
                        })
                    break

        # Interests
        interests = re.findall(
            r"\b(?:i like|i love|i enjoy)\s+([^.,;]+)",
            text,
            flags=re.IGNORECASE
        )

        for item in interests:
            value = item.strip()
            if value:
                memories.append({
                    "key": "interest",
                    "value": value
                })

        # Favorites
        favorites = re.findall(
            r"\bmy favorite ([a-z ]+) is ([^.,;]+)",
            text,
            flags=re.IGNORECASE
        )

        for key, value in favorites:
            memories.append({
                "key": key.strip().lower().replace(" ", "_"),
                "value": value.strip()
            })

        # Programming language
        if re.search(r"\bpython\b", text, flags=re.IGNORECASE):
            memories.append({
                "key": "coding",
                "value": "Python"
            })

        # Project
        if re.search(
            r"\bworking on (?:a|my) project\b",
            text,
            flags=re.IGNORECASE
        ):
            memories.append({
                "key": "project",
                "value": "a personal project"
            })

        # Remove duplicate facts while preserving their order.
        result = []
        seen = set()

        for memory in memories:
            key = memory["key"]
            value = memory["value"]
            identity = (key, value.casefold())

            if identity not in seen:
                seen.add(identity)
                result.append(memory)

        return result
