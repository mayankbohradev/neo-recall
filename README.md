# NeoRecall

**NeoRecall** is an [MCP](https://modelcontextprotocol.io) server for [NeoSapien](https://neosapien.ai) memories.

It matches the official Neo Sapien MCP’s read surface, then adds **local synthesis** tools — briefs, triage, quality ranking, people digests, period comparison, decision logs, memory graphs, and quote search — so agents can answer *“what happened this week?”* without dumping fifty raw rows into the chat.

**Read-first, write-carefully.** 29 read tools, plus 3 write tools (`delete_memories`,
`update_memory`, `update_participants`) that are **two-phase**: the first call only ever
returns a preview of what would change and writes nothing — you must confirm before
anything is touched. Deletes are permanent; NeoSapien exposes no archive/undo.

---

## Why NeoRecall

| Need | Official Neo MCP | NeoRecall |
|------|------------------|-----------|
| Search / get / transcript / people | Yes | Yes |
| “What did I do this week?” as one answer | Manual multi-call | `weekly_brief` / `daily_brief` / `export_brief_pack` |
| Cleanup candidates | Manual | `triage_memories`, `duplicate_candidates` |
| Decisions & follow-ups | Manual | `decision_log`, `action_items`, `follow_ups_due` |
| Exact spoken phrase | Transcript fetch + skim | `quote_search` |
| Week-over-week pulse | Manual | `compare_periods`, `habit_signals` |

---

## Install

```bash
git clone git@github.com:mayankbohradev/neo-recall.git
cd neo-recall
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

Binary path (example):

```text
/ABS/PATH/neo-recall/.venv/bin/neo-recall
```

---

## Sign in (once)

```bash
source .venv/bin/activate
neo-recall-auth --google
```

Browser → **Continue with Google** → same account you use for NeoSapien. Tokens live in the OS keychain.

Fallback:

```bash
neo-recall-auth --manual
```

Smoke check:

```bash
python probe.py
```

---

## Connect hosts

Replace `/ABS/PATH/neo-recall` with your install path.

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "neo-recall": {
      "command": "/ABS/PATH/neo-recall/.venv/bin/neo-recall"
    }
  }
}
```

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "neo-recall": {
      "command": "/ABS/PATH/neo-recall/.venv/bin/neo-recall"
    }
  }
}
```

### Claude Code

```bash
claude mcp add neo-recall -s user -- /ABS/PATH/neo-recall/.venv/bin/neo-recall
```

### Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.neo-recall]
command = "/ABS/PATH/neo-recall/.venv/bin/neo-recall"
```

### ChatGPT

ChatGPT expects a **remote** HTTPS MCP. NeoRecall is **stdio on your machine** today — use Cursor / Claude / Codex locally, or host NeoRecall later with OAuth.

---

## Tool catalog

### Core (parity with official read tools)

| Tool | What it does |
|------|----------------|
| `search_memories` | Primary search — query + filters, light rows, paginated |
| `list_memories` | Browse without a query |
| `list_filtered_memories` | Fetch light rows by exact IDs |
| `get_memory` | Full detail for one memory (optional MOM) |
| `get_transcript` | Transcript for one memory |
| `search_people` | Find people / owners |
| `get_latest_by_person` | Latest memories for a person |
| `memory_stats` | Counts, top topics/domains |
| `get_profile` | Display name, email, subscription (no extra PII) |
| `export_memories` | Export selected IDs (json) |

### Write tools (two-phase — preview, then confirm)

| Tool | What it does |
|------|----------------|
| `delete_memories` | **Permanently** remove memories from your NeoSapien profile (no undo) |
| `update_memory` | Fix a memory's title / summary |
| `update_participants` | Add, remove, or replace who was in a conversation |

Every write returns `confirmation_required` with a preview on the first call and performs
**no** write. Re-run with `confirm=true` to apply. Deletes are verified by re-reading your
profile afterwards — a write that didn't take is reported honestly, never as success.

**Read / write classification.** Every tool carries MCP
[`annotations`](https://modelcontextprotocol.io/specification/server/tools#annotations)
so clients (e.g. the Claude connectors UI) can separate reads from writes and flag
destructive actions:

| Class | Count | Hint | Tools |
|-------|------:|------|-------|
| Read-only | 28 | `readOnlyHint: true` | all search / list / brief / stats / digest tools |
| Write | 3 | `readOnlyHint: false` | `update_memory`, `update_participants`, `set_presentation_pref` |
| Destructive | 1 | `destructiveHint: true` | `delete_memories` |

These are presentation/consent hints, not server-side enforcement — the actual
write-safety is the two-phase `confirm` gate. The classification is pinned by tests so a
new tool can't ship unlabelled.

### Synthesis & briefs

| Tool | What it does |
|------|----------------|
| `weekly_brief` | Narrative brief for a week window |
| `daily_brief` | Narrative brief for one day |
| `export_brief_pack` | Brief + people + actions + ids (artifact-ready) |
| `whats_new` | Memories since a cutoff |
| `topic_timeline` | Chronology for a topic |
| `people_digest` | Everything about one person |
| `triage_memories` | Archive / cleanup candidates |
| `rank_by_quality` | Highest-signal conversations first |
| `related_memories` | Neighbors of a seed memory |

### Analytics & extraction

| Tool | What it does |
|------|----------------|
| `compare_periods` | Count / duration / topic / people deltas between two ranges |
| `habit_signals` | Peak hours, weekday load, domain mix |
| `action_items` | Open questions / actions from stored fields |
| `follow_ups_due` | Follow-up cues with dates / “next week” language |
| `decision_log` | Decision chronology (+ revision hints when present) |
| `memory_graph` | Ego graph around a seed (topics / people / domain) |
| `duplicate_candidates` | Near-duplicate pairs for cleanup |
| `quote_search` | Exact phrase hunt across transcripts |
| `set_presentation_pref` / `get_presentation_pref` | `ask` \| `always` \| `never` for rich UI |

---

## Suggested prompts

Copy-paste these into Cursor, Claude, or Codex after NeoRecall is connected. Each tool lists several phrasings that should route to it.

| Tool | Sample prompts |
|------|----------------|
| `search_memories` | Search my memories for “Product Hunt launch”. · Find notes tagged MCP from last month. · Memories about RAG with a teammate. · Show travel-domain memories since June. |
| `list_memories` | Show my latest 20 memories. · List everything I recorded this month. · Browse my most recent notes without a keyword. |
| `list_filtered_memories` | Pull light details for these memory IDs: … · Re-fetch just the ids from the last search. |
| `get_memory` | Open the full memory for id … including MOM. · Give me the detail view of that Product Hunt talk. · Show title, people, topics, and minutes for … |
| `get_transcript` | Get the transcript for memory … · What was said word-for-word in that call? · Pull the speaker turns for id … |
| `search_people` | Who shows up in my memories named Ada? · Search people matching “Grace”. · List people I’ve been talking to lately. |
| `get_latest_by_person` | What’s the latest I have with Ada? · Show recent memories owned by / featuring Grace. · Last 5 notes involving a given colleague. |
| `memory_stats` | How many memories do I have? · What are my top topics and domains? · Give me a corpus overview. |
| `get_profile` | Who am I signed in as? · Confirm my NeoRecall / NeoSapien profile. · What’s my subscription status? |
| `export_memories` | Export these memory ids as JSON. · Dump the last search results to JSON for me. |
| `delete_memories` | Delete that memory about the dashboard — show me what you'll remove first. · Clean up my accidental 10-second recordings from today. · Remove these memory ids permanently. |
| `update_memory` | Fix the title of that memory to “Pricing sync”. · Rewrite the summary of id … to mention the RevenueCat migration. |
| `update_participants` | Add Ada to that memory's participants. · Remove someone from the standup memory — they weren't there. · Set the participants on id … to just me and one colleague. |

### Natural-language questions

Ranking is tuned for questions, not just keywords. These route to `search_memories` and
put the relevant memories at the top rather than returning most of the corpus:

- *What did &lt;person&gt; say about pricing?*
- *When did I talk to &lt;person&gt; about the backend migration?*
- *Who mentioned the funding application?*
- *What are my open questions about hiring?*
- *How much did we decide to charge?*

The person's name plus the topic are treated as a conjunction — memories where that
person is an actual participant **and** the topic appears rank above memories that merely
repeat the topic.
| `weekly_brief` | What did I do this week? · Summarize last week’s recordings. · Give me a week-in-review for the week of June 30. |
| `daily_brief` | What did I do today? · Brief me on yesterday. · Daily summary for 2026-07-10. |
| `export_brief_pack` | Pack my week into one artifact I can paste. · Build a brief pack with people and open actions. · One payload for my weekly review doc. |
| `whats_new` | Anything new since yesterday? · What landed since Monday morning? · Show memories created after 2026-07-09. |
| `topic_timeline` | When did I talk about RAG? · Timeline of MCP decisions. · Chronology of Product Hunt mentions. · Plot my “hiring” topic over time. |
| `people_digest` | Everything about Ada. · Digest all conversations with Grace. · What have I discussed with a given colleague lately? |
| `triage_memories` | What can I archive or clean up? · Find low-value / short notes to triage. · Which memories look safe to archive? |
| `rank_by_quality` | My most important conversations lately. · Rank the highest-signal meetings this month. · Skip the noise — show quality first. |
| `related_memories` | What else is related to memory …? · Find neighbors of that RAG Product Hunt talk. · Memories similar to id … |
| `compare_periods` | Compare this week to last week. · How did June activity compare to May? · Count and duration delta for the last 7 vs prior 7 days. |
| `habit_signals` | When am I usually recording? · What days/hours am I busiest? · Domain mix and peak hours for the last 2 weeks. |
| `action_items` | What open questions do I still have since July 1? · Pull action items from recent meetings. · Unresolved questions in my MCP notes. |
| `follow_ups_due` | What follow-ups are still hanging? · Anything that said “next week” I should chase? · Follow-ups mentioning email or a date. |
| `decision_log` | Log the decisions I made about MCP. · What did we decide on Zoho / PR gates? · Decision chronology for Product Hunt. |
| `memory_graph` | Map threads related to this memory. · Graph neighbors of the RAG talk. · Who and what topics connect to id …? |
| `duplicate_candidates` | Find near-duplicate notes. · Any double-recorded meetings I can merge/clean? · Duplicate candidates from the last 400 memories. |
| `quote_search` | Find where I said “content ho gaya”. · Search transcripts for “ship it Friday”. · Who said “let’s park Atlation” and when? |
| `set_presentation_pref` | Always show rich cards when you present NeoRecall results. · Ask me before fancy formatting. · Never use themed cards — plain text only. |
| `get_presentation_pref` | What’s my presentation preference? · Are we on ask, always, or never for rich UI? |

---

## Evaluation results (2026-07-11)

Live evaluation on a real NeoSapien account (~2.6k memories), NeoRecall vs official Neo MCP where comparable.

### Fidelity vs official

| Check | Official | NeoRecall | Verdict |
|-------|----------|-----------|---------|
| Profile identity | Owner search → account owner | `get_profile` → same identity | Match |
| Participants | Firestore `entities` | Mapped to participants | Match |
| Duration | Derived from start/finish | Derived (no more `0`) | Match |
| MOM + transcript quote | Identical MOM | `quote_search` byte-match on phrase | Match |
| `search("meeting")` | ~243 FTS hits | ~159 BM25 on light fields | Improved, not full FTS parity |
| Person digests | Limited owner tools | `people_digest` / entity search | NeoRecall stronger |

### Newer tools — live grades

| Tool | Grade | Live result |
|------|-------|-------------|
| `quote_search` | Excellent | Exact phrase + speaker/timings vs official transcript |
| `export_brief_pack` | Excellent | Brief + people + 15 actions in one payload |
| `compare_periods` | Strong | 69 vs 61 week-over-week; close to official date search (TZ noise) |
| `decision_log` | Strong | Real chronology (e.g. MCP / PR / ownership decisions) |
| `habit_signals` | Strong | Peak hour, weekday skew, domain mix |
| `memory_graph` | Strong* | Rich seeds → edge scores 5–7; sparse seeds stay weak |
| `action_items` | Strong* | Real Firestore questions; thin notes add noise |
| `follow_ups_due` | OK | Real cues + some soft false positives |
| `presentation_pref` | OK | Persists `ask` / `always` / `never` |
| `duplicate_candidates` | Weak | 0 pairs at threshold 0.4 — needs retune |

**Ship verdict:** Prefer NeoRecall for briefs, digests, period compare, decisions, habits, and quote lookup. Use official FTS when maximum transcript recall on vague keywords matters. Treat `duplicate_candidates` as experimental.

---

## How search ranks results

`search_memories` scans the **entire corpus** on every query — all memories, no page
limit — and ranks locally with a field-weighted BM25 scorer (`enrich/search_rank.py`).
No embedding model, no external index, no extra dependencies. On a ~3k-memory corpus
(~2M characters) a query ranks in **well under 100ms**.

Plain BM25 over one flat text blob ranks natural-language questions badly. Two fixes:

**1. Stopwords are stripped from the query.** Words like *what / did / say / about*
appear in almost every memory, so a six-word question would match most of the corpus and
the ranking would be decided by whichever memory repeated *"about"* most often. Queries
reduce to their content words — `"what did <person> say about pricing"` becomes
`["<person>", "pricing"]`.

**2. Fields are scored separately, then weighted.** A blob makes a name matching a
participant score the same as that name appearing mid-sentence in a summary:

| Field | Weight | Rationale |
|-------|-------:|-----------|
| `title` | 3.0 | strongest signal of what a memory is *about* |
| `people` | 2.5 | a named entity is usually the point of the question |
| `topics` | 2.0 | curated, low-noise |
| `tags` | 1.5 | curated but sparse |
| `summary` | 1.0 | long and noisy — a hit here is weak evidence |
| `questions` | 1.0 | supporting signal |

On top of that: an exact phrase match is rewarded; covering *more* of the query's
content words beats repeating *one* of them; naming an entity **and** a topic that both
land is treated as the conjunction the user meant; and results scoring below a relevance
floor are dropped rather than padding the result set.

Measured on a ~3k-memory corpus, matches dropped from **~75% of the corpus to ~6%** for
natural-language questions, with the genuinely relevant memories moving into the top
few results. Keyword queries were unaffected. Behaviour is pinned by 21 tests in
`tests/test_search_rank.py`, which run against a synthetic corpus.

---

## Architecture

```text
Reads  → SQLite cache → Firestore (users/{uid}/memories)
Writes → NeoSapien backend (source of truth) → mirrored to Firestore
Auth   → Google once → refresh token in keychain → hourly ID token
```

Hard rules:

1. Writes are opt-in and two-phase — nothing is modified without an explicit `confirm=true`.
2. Tokens never logged.
3. Light rows by default; transcript / MOM on demand.
4. Firestore `integerValue` arrives as a string — parsed carefully.

---

## Dev

```bash
pip install -e ".[dev]"
pytest -q
```

```bash
docker build -t neo-recall .
docker run --rm \
  -e NEOSAPIEN_FIREBASE_API_KEY \
  -e NEOSAPIEN_REFRESH_TOKEN \
  neo-recall
```

---

## License

MIT. Your memories stay yours.
