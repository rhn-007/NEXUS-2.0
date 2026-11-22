# NEXUS Memory Architecture

NEXUS uses SQLite as its persistent source of truth. The local Ollama model does
not retain private memory in its weights between requests; NEXUS prepares a
small context packet and supplies it with each generation request.

## Memory layers

| Layer | Owner | Purpose |
|---|---|---|
| Working | `core/conversation.py` | Current session's bounded message window, restored from the persistent transcript at startup |
| Personal | `memory/memory_manager.py` | User facts, interests, projects, and communication preferences |
| Episodic | `conversation_messages` in `nexus_memory.db` | Earlier user/assistant exchanges, retrieved only when they match the current request |
| Semantic | `learning/knowledge_engine.py` and the research store | Researched topics, source information, verification status, and reusable reference material |
| Procedural | `core/action_history.py`, `learning/personal_language.py`, and the intent/tool layers | Reported past actions, learned vocabulary/corrections, and the assistant's available workflows |

These layers reuse the project's existing stores and services. The redesign
does not copy the conversation transcript or research database into a second
memory database. 

The authoritative transcript is `conversation_messages`, owned by
`core/conversation.py`. The legacy `memories` table remains available for
existing historical rows, but new assistant exchanges are not copied into it.
`MemoryManager.save_conversation()` is retained as a compatibility shim and
does not write duplicate transcript rows.

## Request-time retrieval

1. Restore the latest bounded conversation window.
2. Load personal facts into a compact in-process index at startup.
3. Keep identity, active project, and communication preferences available.
4. Rank remaining personal facts by lexical overlap with the current request.
5. Search the recent persistent transcript and include at most two relevant
   exchanges, excluding turns already present in the active conversation window.
6. Include the bounded rolling digest for older archived exchanges.
7. Retrieve matching semantic/research knowledge through the existing knowledge
   and research retrieval paths.
8. Add the selected context as system reference material for Ollama.

The context builder has a character budget. If a memory source is unavailable,
NEXUS continues with the remaining context rather than failing the response.

## Learning and maintenance

- SQLite remains authoritative; the in-memory personal index is a cache.
- Writes through `MemoryManager` refresh the cache.
- External writes can call `invalidate_session_memory()`; the next retrieval
  rebuilds the cache from SQLite.
- Single-value facts keep their latest value; preference, interest, and coding
  facts can retain multiple values.
- Explicit forgetting removes personal facts only. It does not silently erase
  conversation transcripts, researched knowledge, or action history.
- Once enough messages leave the active context window, older completed turns
  are compacted into a bounded rolling extractive digest in
  `conversation_summaries`. This is deterministic and does not make an extra
  Ollama request; the original transcript remains intact.
- The summary table is upgraded in place with an archive cursor when needed;
  existing summaries are preserved.
- No destructive rewrite of existing memory records is required.

## Important limitation

This is retrieval-augmented session memory, not model fine-tuning. Ollama
receives the selected memory on every request; the model itself does not
permanently absorb the facts into its weights.
