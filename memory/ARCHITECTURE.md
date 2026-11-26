# NEXUS Memory Architecture

SQLite is the persistent source of truth. The local Ollama model does not
permanently learn personal facts; NEXUS retrieves relevant records and supplies
them as context when generating a response.

## Responsibilities

| Component | Responsibility |
|---|---|
| `memory_manager.py` | Coordinates memory writes, forgetting, and the memory components |
| `recall.py` | Recognises memory questions and retrieves user-authored project history |
| `fact_recall.py` | Answers direct fact questions from the matching saved category |
| `context.py` | Builds bounded, locally ranked personal-memory and conversation context |
| `detector.py` | Extracts clear personal facts and corrections with inexpensive rules |
| `semantic_processor.py` | Handles uncertain personal-fact extraction through the existing local model; validates structured output |
| `database.py` | Provides SQLite persistence for personal facts, relationships, patterns, and the knowledge tables shared with `learning/knowledge_engine.py` |
| `associative_memory.py` | Derives evidence-backed relationships and recurring patterns; never creates or edits source facts |
| `models.py` | Retained for compatibility; the current storage and recall pipeline uses dictionaries and SQLite rows |

The conversation transcript belongs to `core/conversation.py`. Research and
learning workflows belong to `learning/knowledge_engine.py` and the research
store. The shared database class exists because those services use the same
SQLite file; it does not mean that research records are personal facts.

## Write flow

1. The deterministic detector checks the new user message.
2. If it finds no fact, a lightweight gate decides whether semantic extraction
   is appropriate. Ordinary questions and tool requests do not trigger an
   extra model call.
3. Semantic output is accepted only when it is valid structured data, has a
   confidence of at least 0.75, and does not claim an unsupported correction.
4. The manager deduplicates multi-value facts and updates single-value facts.
   Preferences, interests, hobbies, activities, coding facts, and TV-show
   records can have multiple values.
5. The in-session fact index is refreshed after a successful write.
6. Associative relationships and patterns are refreshed separately. Failure in
   this derived layer must not prevent the original fact from being saved.

## Recall flow

1. Explicit, recognisable personal questions are routed to deterministic SQLite
   recall before the general response model.
2. A direct fact question reads only its matching category. Unknown facts are
   reported as unknown rather than guessed.
3. Broad interest questions read saved interests, hobbies, and activities.
   TV-show titles remain separately labelled and are not treated as hobbies.
4. Topic-specific questions return only saved values that match the requested
   topics. A missing topic is reported as missing.
5. Other memory questions receive a bounded context built from saved facts,
   lexical relevance, and relevant user-authored transcript messages.
6. The model may phrase the grounded evidence naturally, but assistant replies
   and suggestions are never treated as user-authored facts.

Ordinary memory retrieval and ranking use local deterministic rules. They do
not make a second Ollama call. The semantic processor retains optional
summarisation and candidate-selection helpers, but those are not required for
the ordinary memory request path.

## Associative memory

- Relationships connect existing personal-fact IDs; they do not create facts.
- Explicit links require literal positive mentions and connecting wording.
- Inferred co-mentions and shared-topic edges are labelled as inferred and must
  never be described as something the user explicitly said. Weak co-mentions
  are not added to response context.
- A shared-topic edge requires at least two distinctive shared terms; one
  coincidental shared word is not enough to establish a connection.
- Patterns require multiple distinct supporting facts or separate user
  messages. Assistant messages are excluded from recurring-topic evidence.
- Forgetting or replacing a fact removes its dependent relationships through
  SQLite foreign-key rules and refreshes derived patterns.
- Associations do not establish causation.

## Data and safety invariants

- SQLite remains authoritative; the in-memory fact index is only a cache.
- Existing database tables and records are preserved. No destructive migration
  is needed for the current memory improvements.
- Forgetting personal facts does not erase conversation history, research
  knowledge, or action history.
- A correction replaces only the exact superseded value in the same category.
- Missing evidence stays missing. NEXUS must not fill gaps with assumptions.
- Context is bounded so a large memory database cannot overwhelm the active
  conversation.

## Scope

This is persistent retrieval-augmented memory, not model fine-tuning. Personal
facts, conversation history, researched knowledge, and action history remain
separate sources with separate owners.
