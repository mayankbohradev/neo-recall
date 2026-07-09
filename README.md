# NeoRecall

**NeoRecall** is a read-only [MCP](https://modelcontextprotocol.io) server for [NeoSapien](https://neosapien.ai) / NeoCore memories.

It matches the official Neo Sapien MCP’s read surface, then adds **local synthesis** tools — briefs, triage, quality ranking, people digests, period comparison, decision logs, memory graphs, and quote search — so agents can answer *“what happened this week?”* without dumping fifty raw rows into the chat.

**Read-only by design.** No delete, edit, or write tools. The only network write is refreshing your Google login token.

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

Copy-paste these into Cursor, Claude, or Codex after NeoRecall is connected.

| You say | Tool(s) |
|---------|---------|
| What did I do this week? | `weekly_brief` |
| What did I do today? | `daily_brief` |
| Pack my week into one artifact I can paste | `export_brief_pack` |
| Compare this week to last week | `compare_periods` |
| Anything new since yesterday? | `whats_new` |
| When did I talk about RAG / MCP / Product Hunt? | `topic_timeline` |
| Everything about Preetam / Varun | `people_digest` |
| What can I archive or clean up? | `triage_memories` |
| My most important conversations lately | `rank_by_quality` |
| What open questions do I still have since July 1? | `action_items` |
| What follow-ups are still hanging? | `follow_ups_due` |
| Log the decisions I made about MCP | `decision_log` |
| Map threads related to this memory | `memory_graph` |
| Find near-duplicate notes | `duplicate_candidates` |
| When am I usually recording? | `habit_signals` |
| Find where I said “content ho gaya” | `quote_search` |
| How many memories / top topics? | `memory_stats` |
| Who am I signed in as? | `get_profile` |

---

## Evaluation results (2026-07-11)

Live evaluation on a real NeoSapien account (~2.6k memories), NeoRecall vs official Neo MCP where comparable.

### Fidelity vs official

| Check | Official | NeoRecall | Verdict |
|-------|----------|-----------|---------|
| Profile identity | Owner search → Mayank Bohra | `get_profile` → same identity | Match |
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

## Architecture

```text
MCP tools → SQLite cache → Firestore (users/{uid}/memories)
Auth      → Google once → refresh token in keychain → hourly ID token
```

Hard rules:

1. Read-only — only allowed POST is `securetoken.googleapis.com` (token refresh).
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
