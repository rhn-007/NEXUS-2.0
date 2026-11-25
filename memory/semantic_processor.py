"""Local-LLM-assisted semantic memory extraction and retrieval.

The processor is deliberately gated: ordinary messages do not create an
additional Ollama request. It only extracts from likely personal statements
and only ranks memories for explicit personal-memory questions.
"""

import json
import logging
import re


logger = logging.getLogger(__name__)


class SemanticMemoryProcessor:
    MIN_CONFIDENCE = 0.75
    MAX_EXTRACTED_MEMORIES = 8
    MAX_RETRIEVAL_CANDIDATES = 40
    MAX_EXISTING_MEMORIES = 40
    MAX_RETRIEVAL_RESULTS = 4

    _EXPLICIT_MEMORY_REQUEST = re.compile(
        r"^(?:(?:please\s+)?(?:remember|keep in mind)\b|"
        r"i (?:want|need) you to remember\b|"
        r"i would like (?:you|nexus) to remember\b)",
        re.IGNORECASE
    )
    _SELF_REFERENCE = re.compile(
        r"\b(?:i|i'm|i am|my|me|mine|we|our)\b",
        re.IGNORECASE
    )
    _QUESTION_START = re.compile(
        r"^(?:what|who|why|how|when|where|which|do|does|did|can|could|"
        r"would|should|is|are|will)\b",
        re.IGNORECASE
    )
    _NON_MEMORY_REQUEST = re.compile(
        r"^(?:i (?:do not|don't) remember|i have a question|i need help|i want to know|"
        r"i was wondering|i'm wondering|i am wondering|"
        r"i want you to|i need you to|i would like you to|"
        r"i'd like you to|i want to (?:open|launch|start|close|run|search|"
        r"find|show|calculate|play|stop|turn|set|change|check|download|"
        r"install|visit|browse)|i need to (?:open|launch|start|close|run|search|"
        r"find|show|calculate|play|stop|turn|set|change|check|download|"
        r"install|visit|browse)|i'd like to (?:open|launch|start|close|run|"
        r"search|find|show|calculate|play|stop|turn|set|change|check|download|"
        r"install|visit|browse))\b",
        re.IGNORECASE
    )
    _MEMORY_QUERY_PATTERNS = (
        re.compile(
            r"\bwhat\s+(?:do i|am i|have i|did i|was i)\b.*"
            r"\b(?:like|love|enjoy|prefer|interested|into|passionate|"
            r"usually|told|said|mentioned|learn|study|work)\b",
            re.IGNORECASE
        ),
        re.compile(
            r"\bwhat\s+(?:kind|type|sort)\s+of\b.*"
            r"\b(?:for me|do i|am i)\b",
            re.IGNORECASE
        ),
        re.compile(
            r"\bwhat\b.*\b(?:suits|works well for|works best for|is right for)\s+me\b",
            re.IGNORECASE
        ),
        re.compile(
            r"\bwhat\s+(?:are|is)\s+my\s+"
            r"(?:interests|hobbies|preferences|goals|plans|projects)\b",
            re.IGNORECASE
        ),
        re.compile(
            r"\bwhat\s+do\s+you\s+remember\s+about\s+me\b|"
            r"\bwhat\s+have\s+i\s+told\s+you\s+about\b|"
            r"\bwhat\s+did\s+i\s+say\s+about\b|"
            r"\bremind\s+me\s+(?:what|which|how)\b",
            re.IGNORECASE
        ),
        re.compile(
            r"\b(?:what|who|which|how)\b.{0,70}\b(?:my|me|i|we|our)\b"
            r".{0,70}\b(?:remember|told|said|mentioned|prefer|preference|"
            r"learning|study|studying|favourite|favorite|hobbies|interests|"
            r"goals|projects|discussed|talked)\b|"
            r"\bwhat\s+do\s+you\s+know\s+about\s+my\b",
            re.IGNORECASE
        ),
    )

    def __init__(self, llm=None):
        self.llm = llm

    def set_llm(self, llm):
        """Attach the existing local Ollama client; no new model is created."""
        self.llm = llm

    @classmethod
    def is_extraction_candidate(cls, text):
        """Cheap gate to avoid asking Ollama to inspect ordinary messages."""
        value = str(text or "").strip()
        if not value:
            return False

        if cls._EXPLICIT_MEMORY_REQUEST.search(value):
            return not value.endswith("?")

        if value.endswith("?") or cls._QUESTION_START.match(value):
            return False

        if cls._NON_MEMORY_REQUEST.match(value):
            return False

        words = re.findall(r"[a-z0-9']+", value.lower())
        return len(words) >= 4 and bool(cls._SELF_REFERENCE.search(value))

    @classmethod
    def is_memory_query(cls, query):
        value = str(query or "").strip()
        return any(pattern.search(value) for pattern in cls._MEMORY_QUERY_PATTERNS)

    @staticmethod
    def _parse_json(response):
        if not isinstance(response, str):
            return None

        value = response.strip()
        if not value:
            return None

        value = re.sub(r"^\s*```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```\s*$", "", value)

        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            return None

        try:
            parsed = json.loads(value[start:end + 1])
        except (TypeError, ValueError):
            return None

        return parsed if isinstance(parsed, dict) else None

    def _ask(self, prompt, instruction):
        if self.llm is None:
            return None

        try:
            return self.llm.generate_response(
                prompt,
                context=[{"role": "system", "content": instruction}]
            )
        except Exception as error:
            logger.warning("Semantic memory model request failed: %s", error)
            return None

    @staticmethod
    def _existing_pairs(existing_memories):
        pairs = set()
        for item in existing_memories or []:
            if isinstance(item, dict):
                key, value = item.get("key"), item.get("value")
            else:
                try:
                    key, value = item[0], item[1]
                except (TypeError, IndexError):
                    continue
            if key is not None and value is not None:
                pairs.add((str(key).strip().casefold(),
                           str(value).strip().casefold()))
        return pairs

    def extract(self, user_message, existing_memories=None):
        """Extract explicit personal facts from one user message only."""
        if self.llm is None or not self.is_extraction_candidate(user_message):
            return []

        existing = []
        for item in list(existing_memories or [])[-self.MAX_EXISTING_MEMORIES:]:
            if isinstance(item, dict):
                key, value = item.get("key"), item.get("value")
            else:
                try:
                    key, value = item[0], item[1]
                except (TypeError, IndexError):
                    continue
            if key is not None and value is not None:
                existing.append({
                    "key": str(key).strip(),
                    "value": str(value).strip()
                })

        instruction = (
            "You are NEXUS's private memory extraction component. Read only the "
            "single new USER message supplied in the request. Extract only stable, "
            "useful facts or preferences that the user explicitly states about "
            "themselves. Do not infer facts from questions, hypotheticals, jokes, "
            "assistant text, or system text. Do not save sensitive personal data. "
            "Do not invent, embellish, or turn an intention into a completed fact. "
            "Compare with existing memories and set 'replaces' only when the user "
            "clearly corrects or supersedes that exact existing value. If nothing "
            "should be saved, return {\"memories\": []}. Return JSON only, with "
            "this schema: {\"memories\":[{\"key\":\"snake_case_category\","
            "\"value\":\"short standalone fact\",\"confidence\":0.0,"
            "\"replaces\":null}]}. Confidence must be between 0 and 1."
        )
        prompt = (
            "NEW USER MESSAGE (the only source of new facts):\n"
            + str(user_message).strip()
            + "\n\nEXISTING USER MEMORIES (comparison only):\n"
            + json.dumps(existing, ensure_ascii=False)
            + "\n\nExtract only explicitly stated user facts. Return JSON."
        )

        parsed = self._parse_json(self._ask(prompt, instruction))
        raw_memories = parsed.get("memories", []) if parsed else []
        if not isinstance(raw_memories, list):
            return []

        existing_pairs = self._existing_pairs(existing)
        results = []
        seen = set()

        for item in raw_memories[:self.MAX_EXTRACTED_MEMORIES]:
            if not isinstance(item, dict):
                continue

            key = str(item.get("key") or "").strip().lower()
            value = str(item.get("value") or "").strip()
            try:
                confidence = float(item.get("confidence", 0))
            except (TypeError, ValueError):
                continue

            if (
                not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key)
                or not value
                or len(value) > 160
                or confidence < self.MIN_CONFIDENCE
                or confidence > 1
            ):
                continue

            marker = (key, value.casefold())
            if marker in seen:
                continue
            seen.add(marker)

            memory = {"key": key, "value": value}
            replaces = str(item.get("replaces") or "").strip()
            if replaces and (key, replaces.casefold()) in existing_pairs:
                memory["replaces"] = replaces

            results.append(memory)

        return results

    def summarize_conversation(self, messages):
        """Summarize a recent exchange as its main topic in one or two sentences.

        This is called only for explicit conversation-recall requests, so normal
        conversation does not incur an additional model request.
        """
        if self.llm is None or not messages:
            return None

        transcript = []
        for role, content in messages[-8:]:
            role = str(role or "").strip().lower()
            content = " ".join(str(content or "").split())
            if role in {"user", "assistant"} and content:
                transcript.append(f"{role}: {content[:1200]}")

        if not transcript:
            return None

        instruction = (
            "You are NEXUS's conversation-recall summarizer. Identify the main "
            "subject the user and assistant were discussing. Reply naturally as "
            "a direct answer to 'What were we talking about?'. Give one or two "
            "short sentences describing the topic and the important point. "
            "Synthesize the exchange; do not list messages, quote the transcript, "
            "use labels such as 'You asked' or 'I replied', or merely repeat the "
            "last user message. Use only information in the supplied transcript. "
            "Do not add suggestions or ask a follow-up question."
        )
        prompt = (
            "RECENT CONVERSATION (oldest first):\n"
            + "\n".join(transcript)
            + "\n\nSummarize the main topic naturally."
        )
        response = self._ask(prompt, instruction)
        if not isinstance(response, str):
            return None

        summary = " ".join(response.strip().split())
        summary = re.sub(r"^(?:NEXUS:\s*)", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"^(?:[-*•]+\s*)", "", summary)
        if not summary or len(summary) > 500:
            return None
        if re.search(r"\b(?:you asked|i replied|user:|assistant:)\b", summary, re.IGNORECASE):
            return None
        sentences = [
            sentence for sentence in re.split(r"(?<=[.!?])\s+", summary)
            if sentence.strip()
        ]
        if len(sentences) > 2:
            return None
        return summary

    def select_relevant(self, query, memories):
        """Select existing memory records by meaning, returning only source rows."""
        if (
            self.llm is None
            or not self.is_memory_query(query)
            or not memories
        ):
            return []

        candidates = []
        for item in memories[:self.MAX_RETRIEVAL_CANDIDATES]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if key and value:
                candidates.append({"key": key, "value": value})

        if not candidates:
            return []

        instruction = (
            "You are a strict memory retrieval ranker. Select only memories that "
            "directly help answer the user's personal-memory question. Judge meaning, "
            "not just shared words. Never invent or rewrite a memory. Return JSON "
            "only in this form: {\"relevant\":[0,2]}. The numbers must be zero-based "
            "indices from the supplied candidate list. Return an empty list when "
            "nothing is relevant. Select at most four."
        )
        prompt = (
            "PERSONAL-MEMORY QUESTION:\n"
            + str(query).strip()
            + "\n\nEXISTING MEMORY CANDIDATES:\n"
            + json.dumps(candidates, ensure_ascii=False)
            + "\n\nReturn the indices of relevant existing memories as JSON."
        )

        parsed = self._parse_json(self._ask(prompt, instruction))
        indices = parsed.get("relevant", []) if parsed else []
        if not isinstance(indices, list):
            return []

        selected = []
        seen = set()
        for index in indices:
            if type(index) is not int or index < 0 or index >= len(candidates):
                continue
            if index in seen:
                continue
            seen.add(index)
            selected.append(candidates[index])
            if len(selected) >= self.MAX_RETRIEVAL_RESULTS:
                break

        return selected
