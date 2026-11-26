from memory.database import MemoryDatabase
from memory.associative_memory import AssociativeMemory
import re
import sqlite3

from memory.detector import MemoryDetector, _looks_like_name
from memory.semantic_processor import SemanticMemoryProcessor
from memory.context import MemoryContextMixin
from memory.fact_recall import FactRecallMixin
from memory.recall import (
    MemoryRecallMixin,
    _join,
    _matches_interest_retraction,
    _norm,
)



# Facts that can hold several values; every other key keeps its latest.
MULTI_VALUE_KEYS = {"preference", "interest", "hobby", "activity", "coding", "tv_show"}

class MemoryManager(MemoryRecallMixin, FactRecallMixin, MemoryContextMixin):

    @staticmethod
    def is_memory_request(text):
        """Identify personal-memory requests before action/capability routing."""
        value = " ".join(
            re.sub(r"[?.!,]", " ", str(text or "").lower()).split()
        )
        if not value:
            return False

        # Project-history questions must enter the memory retrieval path even
        # when their wording does not match the older generic memory-query
        # patterns (for example, "what projects have I actually built?").
        project_history_question = re.search(
            r"\bwhat projects have i (?:actually )?(?:told you|built|worked on|developed)\b|"
            r"\bwhat do you remember about my .{0,50}project\b|"
            r"\bwhat have i told you about my .{0,50}project\b",
            value
        )
        if project_history_question or re.search(
            r"\bwhat connections (?:do you see|have you found) between my\b",
            value
        ):
            return True

        explicit = (
            "what do you know about me",
            "what do you know about my",
            "what do you remember about me",
            "what do you remember about my",
            "what have i told you",
            "what did i tell you",
            "what did i say about",
            "what have we discussed",
            "what have we talked about",
            "what were we discussing",
            "what were we talking about",
            "tell me about myself",
            "describe me",
            "my profile",
            "my details",
            "what patterns have you noticed about me",
            "what patterns have you noticed",
            "what patterns do you see in my interests",
            "what themes keep coming up",
            "what have you noticed about my interests",
            "what connections have you found between my memories",
            "what connections do you see between my interests and goals",
            "what connections have you found between my interests and goals",
            "how are my interests connected",
            "what is the relationship between my interests and goals",
            "connect my memories",
            "analyse my memories",
            "analyze my memories",
        )
        if any(phrase in value for phrase in explicit):
            return True
        return SemanticMemoryProcessor.is_memory_query(value)

    def __init__(self):

        self.db = MemoryDatabase()
        self.associative_memory = AssociativeMemory(self.db)

        self.detector = MemoryDetector()
        self.semantic_processor = SemanticMemoryProcessor()

        # A compact personal-memory snapshot is prepared once at startup.
        # SQLite remains authoritative; writes through this manager refresh it.
        self._session_facts_context = None
        self.load_session_memory()
        try:
            # Build the initial graph from existing SQLite facts so older
            # memories participate immediately after an upgrade.
            self.associative_memory.update()
        except Exception:
            pass

    def set_llm(self, llm):
        """Use NEXUS's existing local model for gated semantic memory tasks."""
        self.semantic_processor.set_llm(llm)

    def load_session_memory(self):
        """Refresh the in-session fact index and its compact compatibility snapshot."""
        self._session_facts = self._facts_by_key()
        self._session_facts_context = self._build_facts_context()
        return self._session_facts_context

    def invalidate_session_memory(self):
        """Mark both cached personal-memory views stale after an external write."""
        self._session_facts_context = None
        self._session_facts = None





    # =====================================
    # PROCESS USER MEMORY
    # =====================================

    def _previous_user_message(self):
        """
        Return the user message immediately before the current one from the
        persistent conversation transcript. NEXUS records the current input
        before asking MemoryManager to save facts.
        """
        try:
            rows = self.db.connection.execute(
                """
                SELECT content FROM conversation_messages
                WHERE conversation_id = 'default' AND role = 'user'
                ORDER BY id DESC
                LIMIT 2
                """
            ).fetchall()
        except sqlite3.Error:
            return None

        return rows[1]["content"] if len(rows) >= 2 else None

    def process_memory(
        self,
        text
    ):

        memories = self.detector.detect(text)

        # Use semantic extraction only when the deterministic detector found
        # nothing and the message looks like a personal statement or an
        # explicit remember request. Ordinary conversation stays model-free.
        if not memories:
            existing_memories = [
                {"key": key, "value": value}
                for key, value, _memory_type in self.get_memory_context()
            ]
            memories = self.semantic_processor.extract(
                text,
                existing_memories=existing_memories
            )

        # Also inspect the previous question even when this message contains
        # another detectable fact. For example, "It's badminton. I like
        # badminton." expresses both a favourite sport and an interest.
        previous_question = self._previous_user_message()
        answer_memories = self.detector.detect_answer(text, previous_question)
        memories.extend(answer_memories)

        # Remove duplicates produced by overlapping detectors.
        unique_memories = []
        seen_memories = set()
        for memory in memories:
            pair = (memory["key"].lower(), memory["value"].lower())
            if pair not in seen_memories:
                seen_memories.add(pair)
                unique_memories.append(memory)
        memories = unique_memories

        if not memories:
            # An explicit relationship can be stated after both endpoint facts
            # already exist, without introducing a new fact of its own. Refresh
            # transcript-derived patterns on every turn using user messages only.
            try:
                linked = self.associative_memory.discover_from_statement(
                    text,
                    explicit_only=True
                )
                self.associative_memory.rebuild_patterns()
                return bool(linked)
            except Exception:
                return False
    
    
    
        # Multi-value facts are deduplicated across their history. For
        # single-value facts, compare against the current value only: a user
        # must be able to change a fact back to something they said earlier.
        known = self._facts_by_key()
        stored = False

        for memory in memories:
            key = str(memory["key"]).strip().lower()
            value = str(memory["value"]).strip()
            current_values = known.get(key, [])
            replaces = str(memory.get("replaces", "")).strip()

            # An explicit "not one of my interests" statement removes only
            # the named item. Check dedicated TV-show rows and legacy interest
            # fragments so old representations cannot leak back into recall.
            if memory.get("remove") and key == "interest":
                for existing_key, existing_value in self.db.get_facts():
                    if existing_key not in {"interest", "tv_show"}:
                        continue
                    if _matches_interest_retraction(existing_value, value):
                        deleted = self.db.delete_memories(
                            key=existing_key,
                            value=existing_value,
                            memory_type="fact"
                        )
                        stored = stored or bool(deleted)
                continue

            # Apply explicit corrections before duplicate checks. The new value
            # may already exist as an older preference; the correction must
            # still remove the superseded value without creating a duplicate.
            if replaces:
                self.db.replace_memory(
                    key,
                    replaces,
                    value,
                    memory_type="fact"
                )
                remaining = [
                    existing for existing in current_values
                    if _norm(existing) != _norm(replaces)
                ]
                if not any(_norm(existing) == _norm(value) for existing in remaining):
                    remaining.append(value)
                known[key] = remaining
                stored = True
                continue

            if key in MULTI_VALUE_KEYS:
                if any(_norm(existing) == _norm(value) for existing in current_values):
                    continue
            elif current_values and _norm(current_values[-1]) == _norm(value):
                continue

            self.db.insert(key, value, "fact")

            if key in MULTI_VALUE_KEYS:
                known.setdefault(key, []).append(value)
            else:
                known[key] = [value]

            stored = True

        if stored:
            self.load_session_memory()
            try:
                self.associative_memory.update(text)
            except Exception:
                # Memory extraction must remain reliable even if the derived
                # association layer is temporarily unavailable.
                pass
        else:
            # A relationship can be explicitly clarified using facts already
            # in SQLite, even when the statement adds no new personal fact.
            try:
                linked = self.associative_memory.discover_from_statement(
                    text,
                    explicit_only=True
                )
                self.associative_memory.rebuild_patterns()
                stored = bool(linked)
            except Exception:
                pass

        return stored





    # =====================================
    # NATURAL MEMORY RESPONSE
    # =====================================

    def answer_conversation_recall(self, current_query=None, limit=10):
        """Answer a recent-conversation question from the stored transcript.

        The current question is already persisted before memory routing, so
        remove it before selecting the latest substantive user/assistant turn.
        """
        chats = self._recent_conversation_messages(limit=limit)
        if not chats:
            return "I don't have any earlier conversation messages stored yet."

        query_norm = _norm(re.sub(r"[?.!,]", " ", str(current_query or "")))
        if chats and chats[-1][0] == "user" and _norm(
            re.sub(r"[?.!,]", " ", chats[-1][1])
        ) == query_norm:
            chats = chats[:-1]

        latest_user_index = None
        for index in range(len(chats) - 1, -1, -1):
            if chats[index][0] == "user" and chats[index][1].strip():
                latest_user_index = index
                break

        if latest_user_index is None:
            return "I couldn't find an earlier user message in the recent conversation."

        user_text = chats[latest_user_index][1].strip()

        # Build a compact recall context locally. Ollama will turn this
        # grounded transcript material into the final natural-language reply,
        # avoiding a second model request just to summarise the same exchange.
        recent_exchange = chats[max(0, latest_user_index - 5):]
        summary = self._recent_conversation_summary()
        excerpts = []
        for role, content in recent_exchange[-6:]:
            excerpt = self._sentence_excerpt(content, max_chars=220)
            if excerpt:
                excerpts.append(f"{role.title()}: {excerpt}")

        parts = []
        if summary:
            parts.append("Stored conversation summary: " + summary[-700:])
        if excerpts:
            parts.append("Recent exchange:\n" + "\n".join(excerpts))
        if parts:
            return "\n".join(parts)

        user_text = self._sentence_excerpt(user_text, max_chars=240)
        return "The recent conversation was about: " + user_text

    @staticmethod
    def _sentence_excerpt(text, max_chars=500):
        """Return a readable excerpt ending at a sentence boundary when possible."""
        text = " ".join(str(text or "").split())
        if len(text) <= max_chars:
            return text

        sentences = re.split(r"(?<=[.!?])\s+", text)
        excerpt = ""
        for sentence in sentences:
            candidate = (excerpt + " " + sentence).strip()
            if len(candidate) > max_chars:
                break
            excerpt = candidate
        if excerpt:
            return excerpt

        # A single unusually long sentence has no safe sentence boundary.
        shortened = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
        return shortened + "…"

    def handle_memory_query(
        self,
        text
    ):


        text = text.lower()



        # -----------------------------
        # USER PROFILE
        # -----------------------------

        profile_words = [

            "what do you know about me",

            "what do u know about me",

            "tell me about myself",

            "tell me about me",

            "who am i",

            "what can you remember about me",

            "what do you remember about me",

            "describe me",

            "my profile",

            "my details"

        ]



        if any(

            word in text

            for word in profile_words

        ):


            facts = self._facts_by_key()



            if not facts:


                return (

                    "I haven't learned much about you yet."

                )



            response = (

                "From what you've shared with me, "

                "here is what I know about you:\n\n"

            )



            for key, values in facts.items():
                shown = _join(self._show(key, value) for value in values)
                response += f"• Your {key.replace('_', ' ')} is {shown}.\n"


            return response.strip()






        # -----------------------------
        # CONVERSATION RECALL
        # -----------------------------


        recall_words = [

            "what did we talk about",

            "what did we discuss",

            "previous conversation",

            "previous conversations",

            "our last conversation",

            "what do you recall",

            "what do u recall",

            "remember our chat",

            "summarize our conversation",

            "what have i told you"

        ]



        if any(

            word in text

            for word in recall_words

        ):


            chats = self._recent_conversation_messages(limit=10)
            summary = self._recent_conversation_summary()

            if not chats and not summary:
                return "I don't have any previous conversations stored yet."

            response = (
                "From our previous conversations, "
                "I remember that:\n\n"
            )
            if summary:
                response += "Earlier conversation summary: " + summary + "\n\n"

            for role, content in chats:
                response += f"{role}: {content}\n\n"


            return response.strip()



        return None






    def _recent_conversation_summary(self):
        """Return the rolling digest for the default assistant conversation."""
        try:
            row = self.db.connection.execute(
                "SELECT summary FROM conversation_summaries "
                "WHERE conversation_id = 'default'"
            ).fetchone()
        except sqlite3.Error:
            return None
        return str(row["summary"]).strip() if row and row["summary"] else None

    def _recent_conversation_messages(self, limit=10):
        """Read episodic messages from the authoritative conversation table."""
        try:
            rows = self.db.connection.execute(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE conversation_id = 'default'
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),)
            ).fetchall()
        except sqlite3.Error:
            # ConversationManager may not have created the table yet.
            return []

        return [
            (str(row["role"]), str(row["content"]))
            for row in reversed(rows)
        ]


    # =====================================
    # SAVE CONVERSATION
    # =====================================

    def save_conversation(self, user, assistant):
        """Compatibility shim; ConversationManager is the sole transcript owner.

        The assistant already persists both messages through ConversationManager
        before this legacy method is called. Writing them to the old memories
        table would create a second, divergent copy of every conversation.
        Existing legacy rows remain untouched and readable for compatibility.
        """
        return False







    # =====================================
    # SEARCH CONTEXT FOR AI
    # =====================================

    def get_memory_records(self, limit=500):
        """Expose stable IDs for personal facts used by the memory graph."""
        return self.db.get_fact_records(limit=limit)

    def link_memories(
        self, source_memory_id, target_memory_id, relation_type,
        confidence=1.0, origin="inferred", evidence=None
    ):
        """Persist a typed relationship without modifying either fact."""
        return self.db.create_memory_relationship(
            source_memory_id, target_memory_id, relation_type,
            confidence=confidence, origin=origin, evidence=evidence
        )

    def get_memory_relationships(
        self, memory_id=None, min_confidence=0.0, limit=100
    ):
        return self.db.get_memory_relationships(
            memory_id=memory_id, min_confidence=min_confidence, limit=limit
        )

    def get_context(
        self
    ):


        facts = [
            (key, value)
            for key, value, _memory_type in self.get_memory_context()
        ]


        conversations = self._recent_conversation_messages(limit=6)


        context = {
            "facts": facts,
            "recent_conversations": conversations,
            "conversation_summary": self._recent_conversation_summary()
        }


        return context






    # =====================================
    # COMPATIBILITY FUNCTIONS
    # =====================================

    def remember(

        self,

        key,

        value

    ):

        result = self.db.insert(
            key,
            value,
            "fact"
        )
        self.load_session_memory()
        self.associative_memory.update()
        return result




    def forget(self, key=None, value=None):
        """
        Forget personal facts matching a key and/or exact value.

        Calling without filters clears personal facts only. Conversation
        transcripts, researched knowledge, and action history are preserved.
        """
        deleted = self.db.delete_memories(
            key=key,
            value=value,
            memory_type="fact"
        )
        if deleted:
            self.load_session_memory()
            self.associative_memory.rebuild_patterns()
        return deleted

    def recall(

        self,

        key

    ):


        results = self.db.search(

            key

        )


        if results:
            return results[-1][1]


        return None



    def get_memory_context(

        self

    ):
        """
        Return a clean, deduplicated view of personal facts.
        The original SQLite rows are preserved; filtering happens at read time.
        """

        grouped = self._facts_by_key()
        rows = []

        for key, values in grouped.items():
            for value in values:
                rows.append((key, value, "fact"))

        return rows

    # =====================================
    # WHAT NEXUS KNOWS, AS NEXT-TO-USE FACTS
    # =====================================

    def _facts_by_key(self):
        """
        {key: [values]} in the order first told. Keys that hold one value keep
        the latest; preferences, interests and coding keep every value.
        """

        grouped = {}

        for key, value in self.db.get_facts():

            key = str(key)
            value = str(value)

            # Older detector versions could save pronouns or sentence
            # fragments as a name. Ignore those rows without deleting data.
            if key == "name" and not _looks_like_name(value.strip().lower()):
                continue

            values = grouped.setdefault(key, [])

            if key in MULTI_VALUE_KEYS:

                # Coding-language labels use a consistent lowercase form,
                # and surrounding whitespace is never meaningful.
                clean_value = _norm(value) if key == "coding" else value.strip()

                if not any(_norm(existing) == _norm(clean_value) for existing in values):
                    values.append(clean_value)

            else:

                grouped[key] = [value]

        return grouped

    @staticmethod
    def _show(key, value):

        return value.title() if key == "name" else value

    def facts_context(self, max_chars=600):
        """
        Return the session snapshot of personal facts.

        The snapshot is built at startup and refreshed after memory writes.
        A non-default max_chars request is rendered separately so callers can
        request a different budget without changing the shared snapshot.
        """
        if max_chars == 600:
            if self._session_facts_context is None:
                self.load_session_memory()
            return self._session_facts_context

        return self._build_facts_context(max_chars=max_chars)

    def _build_facts_context(self, max_chars=600):
        """Build the compact personal-memory context from authoritative SQLite data."""
        grouped = self._facts_by_key()

        if not grouped:
            return None

        parts = []

        for key, values in grouped.items():

            shown = ", ".join(self._show(key, v) for v in values[-5:])

            parts.append(f"{key.replace('_', ' ')}: {shown}")

        note = (
            "SHARED NEXUS MEMORY CONTEXT. These are authoritative personal "
            "facts the user explicitly shared and persisted conversation records. "
            "Use them as part of your reasoning and response, not as a separate "
            "answer source. The latest stored value for a single-value fact is "
            "the current one. Never contradict stored facts or replace them with "
            "guesses. Do not recite unrelated facts unless asked: "
        )

        for part in parts:

            if len(note) + len(part) + 2 > max_chars:
                break

            note += part + "; "

        return note.rstrip("; ") + "."

