# AGENTS.md — NeoRecall

## What we're building

**NeoRecall** — a **read-only MCP server** for NeoSapien / NeoCore memories.
Parity with the official Neo Sapien MCP **plus** local synthesis (briefs, triage,
quality ranking, people digests, period compare, decision log, graph, quote search).
**No write/edit/delete tools, ever.**

## Hard rules

1. **Read-only.** Only allowed POST: `securetoken.googleapis.com` (token refresh).
2. Firebase project `neo-app-prod`; memories at `users/{uid}/memories`.
3. Tokens in OS keychain / encrypted fallback — never log tokens. Prefer
   `neo-recall-auth --google` for capture.
4. Firestore `integerValue` is a **string** — parse it.
5. Light by default; transcript/MOM on demand.
6. `get_profile` returns only display_name / email / subscription_status.
7. Run `python probe.py` before trusting transcript/MOM field names from Firestore.

## Layout

`auth/` (incl. `google_login.py`) `client/` `models/` `enrich/` `cache/` `tools/` `server.py`
