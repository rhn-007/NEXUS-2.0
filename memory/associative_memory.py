"""Evidence-grounded associative memory and recurring-pattern discovery.

This module deliberately uses deterministic local rules. It never invents
facts, never edits source memories, and does not call Ollama during ordinary
conversation. The response model can reason over the bounded graph context
that this module supplies.
"""

from collections import defaultdict
from itertools import combinations
import re
import sqlite3


class AssociativeMemory:
    MAX_FACTS = 500
    MAX_DISCOVERED_PAIRS = 1200
    MAX_CONTEXT_RELATIONSHIPS = 5
    MAX_CONTEXT_PATTERNS = 4

    _STOPWORDS = {
        "about", "after", "again", "also", "and", "are", "because", "been",
        "being", "can", "could", "did", "does", "doing", "for", "from",
        "have", "into", "just", "like", "make", "more", "most", "much",
        "need", "not", "only", "other", "our", "really", "some", "such",
        "than", "that", "their", "them", "then", "there", "these", "they",
        "this", "those", "through", "very", "want", "what", "when", "where",
        "which", "who", "with", "would", "your", "user", "interest",
        "interests", "project", "projects", "favourite", "favorite"
    }

    _INTEREST_KEYS = {
        "interest", "hobby", "sport", "coding", "programming_language",
        "tv_show", "activity"
    }
    _GOAL_PROJECT_KEYS = {
        "project", "goal", "career_goal", "education_goal", "plan"
    }
    _LEARNING_KEYS = {
        "learning_preference", "learning_approach", "learning_style",
        "study_method"
    }

    def __init__(self, database):
        self.db = database

    @classmethod
    def _tokens(cls, text):
        tokens = re.findall(r"[a-z0-9]+", str(text or "").casefold())
        return {
            token for token in tokens
            if len(token) >= 5 and token not in cls._STOPWORDS
        }

    @staticmethod
    def _positive_span(text, value):
        """Return a positive literal mention span, excluding obvious negation."""
        value = " ".join(str(value or "").split()).strip()
        if len(value) < 3:
            return None
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])",
            re.IGNORECASE
        )
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 55):match.start()]
            after = text[match.end():match.end() + 55]
            if re.search(
                r"\b(?:not|never|don't|do not|doesn't|does not|"
                r"didn't|did not|no longer|not interested in|"
                r"not one of my interests)\s*(?:(?:really|particularly)\s+)?"
                r"(?:like|love|enjoy|watch|watching|follow|following|"
                r"interested in|into)?\s*$",
                before,
                re.IGNORECASE
            ):
                continue
            if re.match(
                r"\s+(?:(?:is|was|are)\s+not|isn't|aren't|wasn't)\s+"
                r"(?:one of|an? interest|something i|something that i|for me)",
                after,
                re.IGNORECASE
            ):
                continue
            return match.span()
        return None

    @classmethod
    def _positive_mention(cls, text, value):
        return cls._positive_span(text, value) is not None

    @staticmethod
    def _explicit_connector(text, first_span, second_span):
        """Check whether the user explicitly described a relationship."""
        left, right = sorted((first_span, second_span), key=lambda span: span[0])
        between = text[left[1]:right[0]]
        return bool(re.search(
            r"\b(?:is|are|was|were|has been|have been)?\s*"
            r"(?:closely\s+)?(?:related to|connected to|associated with|"
            r"linked to|part of|built around|based on|focused on|"
            r"focuses on|centred on|centered on|supports|involves)\b|"
            r"\bconnects?\s+(?:it|this|that|them)?\s*(?:to|with)\b",
            between,
            re.IGNORECASE
        ))

    def discover_from_statement(self, statement, explicit_only=False):
        """Persist explicit links or cautious co-mentions grounded in one statement."""
        text = " ".join(str(statement or "").split()).strip()
        if not text:
            return 0

        records = self.db.get_fact_records(limit=self.MAX_FACTS)
        mentioned = []
        for item in records:
            span = self._positive_span(text, item.get("value", ""))
            if span:
                mentioned.append((item, span))

        created = 0
        for (first, first_span), (second, second_span) in combinations(mentioned, 2):
            if created >= 30:
                break
            if first["id"] == second["id"]:
                continue
            if str(first["value"]).casefold().strip() == str(second["value"]).casefold().strip():
                continue

            explicit = self._explicit_connector(text, first_span, second_span)
            if explicit:
                relation_type = "related_to"
                confidence = 0.92
                origin = "explicit"
                evidence = "The user explicitly connected these facts in: " + text[:300]
            elif explicit_only:
                continue
            else:
                relation_type = "co_mentioned"
                confidence = 0.72
                origin = "inferred"
                evidence = "Both stored facts were positively mentioned in: " + text[:300]

            self.db.create_memory_relationship(
                first["id"], second["id"], relation_type,
                confidence=confidence, origin=origin, evidence=evidence
            )
            created += 1
        return created

    def discover_shared_topics(self):
        """Link facts only when their stored descriptions share a distinctive term."""
        records = self.db.get_fact_records(limit=self.MAX_FACTS)
        token_index = defaultdict(list)
        for item in records:
            for token in self._tokens(item.get("value", "")):
                token_index[token].append(item)

        existing_pairs = {
            tuple(sorted((int(row["source_memory_id"]), int(row["target_memory_id"]))))
            for row in self.db.connection.execute(
                "SELECT source_memory_id, target_memory_id FROM memory_relationships"
            ).fetchall()
        }
        candidates = {}
        for token, items in token_index.items():
            for first, second in combinations(items, 2):
                if first["id"] == second["id"] or first["key"] == second["key"]:
                    continue
                if str(first["value"]).casefold().strip() == str(second["value"]).casefold().strip():
                    continue
                pair = tuple(sorted((int(first["id"]), int(second["id"]))))
                if pair in existing_pairs:
                    continue
                candidates.setdefault(pair, set()).add(token)
                if len(candidates) >= self.MAX_DISCOVERED_PAIRS:
                    break
            if len(candidates) >= self.MAX_DISCOVERED_PAIRS:
                break

        created = 0
        by_id = {int(item["id"]): item for item in records}
        for (first_id, second_id), shared in candidates.items():
            first = by_id[first_id]
            second = by_id[second_id]
            # One distinctive shared word is enough for a cautious topical
            # association; two or more provide stronger evidence.
            confidence = min(0.88, 0.70 + 0.07 * min(len(shared), 2))
            evidence = "Shared descriptive term(s): " + ", ".join(sorted(shared))
            self.db.create_memory_relationship(
                first_id,
                second_id,
                "shares_topic",
                confidence=confidence,
                origin="inferred",
                evidence=evidence
            )
            created += 1
        return created

    def rebuild_patterns(self):
        """Rebuild compact pattern summaries from existing facts only."""
        records = self.db.get_fact_records(limit=self.MAX_FACTS)
        patterns = []

        token_records = defaultdict(list)
        for item in records:
            for token in self._tokens(item.get("value", "")):
                token_records[token].append(item)

        for token, items in token_records.items():
            unique_items = {int(item["id"]): item for item in items}
            unique_keys = {str(item["key"]) for item in unique_items.values()}
            if len(unique_items) < 2 or len(unique_keys) < 2:
                continue
            ordered = sorted(unique_items.values(), key=lambda item: int(item["id"]))
            key_names = sorted(unique_keys)
            label = "Recurring theme: " + token
            summary = (
                "The theme '" + token + "' appears in "
                + str(len(ordered)) + " saved facts across "
                + ", ".join(key_names) + "."
            )
            patterns.append({
                "pattern_key": "theme:" + token,
                "pattern_type": "shared_theme",
                "label": label,
                "summary": summary,
                "confidence": min(0.90, 0.68 + 0.05 * (len(ordered) - 1)),
                "evidence_count": len(ordered),
                "evidence_memory_ids": [int(item["id"]) for item in ordered]
            })

        clusters = (
            ("interest_cluster", self._INTEREST_KEYS, "Interest cluster",
             "You have explicitly shared several interests: "),
            ("goal_project_cluster", self._GOAL_PROJECT_KEYS, "Goals and projects",
             "You have shared several goals or projects: "),
            ("learning_cluster", self._LEARNING_KEYS, "Learning preferences",
             "You have shared several details about how you learn: ")
        )
        for pattern_key, allowed_keys, label, prefix in clusters:
            selected = [
                item for item in records
                if str(item["key"]).casefold() in allowed_keys
            ]
            unique = []
            seen = set()
            for item in selected:
                marker = str(item["value"]).casefold().strip()
                if marker and marker not in seen:
                    seen.add(marker)
                    unique.append(item)
            if len(unique) < 3:
                continue
            shown = [str(item["value"]).strip() for item in unique[:5]]
            if len(shown) > 1:
                description = ", ".join(shown[:-1]) + " and " + shown[-1]
            else:
                description = shown[0]
            patterns.append({
                "pattern_key": pattern_key,
                "pattern_type": "fact_cluster",
                "label": label,
                "summary": prefix + description + ".",
                "confidence": min(0.90, 0.70 + 0.04 * (len(unique) - 3)),
                "evidence_count": len(unique),
                "evidence_memory_ids": [int(item["id"]) for item in unique]
            })

        # Recurring topics are counted from separate USER messages only.
        # Assistant responses are excluded so model-generated text cannot
        # manufacture a supposed user interest.
        try:
            message_rows = self.db.connection.execute("""
                SELECT id, content
                FROM conversation_messages
                WHERE conversation_id = 'default' AND role = 'user'
                ORDER BY id DESC
                LIMIT 500
            """).fetchall()
        except sqlite3.Error:
            message_rows = []

        token_messages = defaultdict(list)
        for row in message_rows:
            message_id = int(row["id"])
            for token in self._tokens(row["content"]):
                token_messages[token].append(message_id)

        for token, message_ids in token_messages.items():
            distinct_ids = sorted(set(message_ids))
            if len(distinct_ids) < 3:
                continue
            patterns.append({
                "pattern_key": "conversation_theme:" + token,
                "pattern_type": "recurring_conversation_theme",
                "label": "Recurring conversation topic: " + token,
                "summary": (
                    "You have brought up the topic '" + token + "' in "
                    + str(len(distinct_ids)) + " separate user messages."
                ),
                "confidence": min(0.88, 0.68 + 0.04 * (len(distinct_ids) - 3)),
                "evidence_count": len(distinct_ids),
                "evidence_memory_ids": [],
                "evidence_message_ids": distinct_ids[:50]
            })

        patterns.sort(
            key=lambda item: (
                -float(item["confidence"]),
                -int(item["evidence_count"]),
                item["pattern_key"]
            )
        )
        self.db.replace_memory_patterns(patterns[:30])
        return patterns[:30]

    def update(self, statement=None):
        """Refresh associations and derived patterns after a personal-memory write."""
        if statement:
            self.discover_from_statement(statement)
        self.discover_shared_topics()
        return self.rebuild_patterns()

    def get_patterns(self, limit=20):
        return self.db.get_memory_patterns(active_only=True, limit=limit)

    def get_relationships(self, min_confidence=0.68, limit=100):
        return self.db.get_memory_relationships(
            min_confidence=min_confidence,
            limit=limit
        )

    def build_context(self, query, memory_request=False):
        """Return a bounded graph/pattern context relevant to the current query."""
        records = self.db.get_fact_records(limit=self.MAX_FACTS)
        query_tokens = self._tokens(query)
        scored = []
        for item in records:
            value_tokens = self._tokens(
                str(item.get("key", "")) + " " + str(item.get("value", ""))
            )
            overlap = query_tokens.intersection(value_tokens)
            if overlap:
                scored.append((len(overlap), int(item["id"])))
        scored.sort(key=lambda pair: (-pair[0], -pair[1]))

        seed_ids = [memory_id for _, memory_id in scored[:5]]
        if memory_request and not seed_ids:
            seed_ids = [int(item["id"]) for item in records[-5:]]

        edges = {}
        for memory_id in seed_ids:
            for edge in self.db.get_memory_relationships(
                memory_id=memory_id,
                min_confidence=0.68,
                limit=20
            ):
                edges[int(edge["id"])] = edge

        relationship_lines = []
        for edge in sorted(
            edges.values(),
            key=lambda item: (-float(item["confidence"]), -int(item["id"]))
        ):
            if edge["origin"] == "explicit" and edge["relation_type"] == "related_to":
                description = "were explicitly connected by the user"
                evidence_label = "explicit user-stated link"
            elif edge["relation_type"] == "co_mentioned":
                description = "were positively mentioned together"
                evidence_label = "inferred co-mention"
            else:
                description = "share a distinctive descriptive topic"
                evidence_label = "inferred topical association"
            relationship_lines.append(
                f'{edge["source_key"]}: {edge["source_value"]} and '
                f'{edge["target_key"]}: {edge["target_value"]} {description} '
                f'({evidence_label}, confidence {float(edge["confidence"]):.2f})'
            )
            if len(relationship_lines) >= self.MAX_CONTEXT_RELATIONSHIPS:
                break

        patterns = self.get_patterns(limit=20)
        relevant_patterns = []
        for item in patterns:
            pattern_tokens = self._tokens(
                item.get("label", "") + " " + item.get("summary", "")
            )
            if memory_request or query_tokens.intersection(pattern_tokens):
                relevant_patterns.append(item)
            if len(relevant_patterns) >= self.MAX_CONTEXT_PATTERNS:
                break

        sections = []
        if relationship_lines:
            sections.append(
                "Connected personal memories (these are evidence-backed associations, "
                "not proof of causation or additional user-stated facts): "
                + "; ".join(relationship_lines) + "."
            )
        if relevant_patterns:
            pattern_lines = [
                f'{item["summary"]} (derived from {item["evidence_count"]} saved facts; '
                f'confidence {float(item["confidence"]):.2f})'
                for item in relevant_patterns
            ]
            sections.append(
                "Recurring memory patterns (derived summaries, not verbatim user statements): "
                + " ".join(pattern_lines)
            )
        return "\n".join(sections) if sections else None
