Access to your NeoSapien memories — search, digest, triage, and reason over your
recorded conversations. Mostly read-only; a small, explicitly-confirmed set of write
tools can correct memories and PERMANENTLY delete them (see "Write tools" below).

## Vague-ask → tool cheat-sheet

- 'what did I do this week' / 'my week'        → weekly_brief / export_brief_pack
- 'what did I do today'                        → daily_brief
- 'this week vs last week'                     → compare_periods
- 'what can I delete / clean up'               → triage_memories / duplicate_candidates
- 'delete / remove this memory'                → delete_memories (PERMANENT, confirm first)
- 'fix the title / summary'                    → update_memory
- 'wrong people / add <name> to this'          → update_participants
- 'my best/most important conversations'       → rank_by_quality
- 'everything about <person>'                  → people_digest
- 'anything new since yesterday'               → whats_new
- 'when did I talk about <topic>'              → topic_timeline
- 'related to this meeting' / 'map this'       → related_memories / memory_graph
- 'open questions / action items'              → action_items
- 'what do I need to follow up on'             → follow_ups_due
- 'what did we decide about X'                 → decision_log(topic=X)
- 'exact quote / what did someone say'         → quote_search (heavy)
- 'my habits / when am I busiest'              → habit_signals
- 'my last meeting with <person>'              → get_latest_by_person / people_digest
- 'how many memories / top topics'             → memory_stats
- 'what did we decide in <meeting>'            → get_memory (include_mom=true)
- 'find that conversation about X'             → search_memories(query=X)
- 'show me everything'                         → list_memories (paginate all pages)
- 'always / never ask for visuals'             → set_presentation_pref

## Tool design rules for the host model

1. Light by default — search/list never include transcripts. Call get_transcript / quote_search only when needed.
2. Paginate — if total_pages > page, fetch remaining pages before answering broad questions.
2b. **Stale-cache rule.** The index is cached for 10 minutes, so memories recorded in the
   last few minutes may be missing. If a search returns nothing (or nothing recent) for a
   memory the user says exists, or the ask is about "just now" / today / "what I recorded",
   retry ONCE with `force_refresh=true` BEFORE telling the user it doesn't exist. Never
   report "not found" off a cached search alone.
3. Prefer names over opaque ids; use search_people / people_digest when a name is given.
4. Full-day end dates: pass `YYYY-MM-DDT23:59:59` (tools also normalize bare dates).
5. Writes exist but are two-phase — see "Write tools". delete_memories is PERMANENT and
   has no undo; never call it with confirm=true without showing the user what dies first.
6. Before offering visuals, call get_presentation_pref — if `always`, skip the ask; if `never`, never offer; if `ask`, ask once.

## Write tools (delete_memories, update_memory, update_participants)

These modify the user's real memories. Every one is two-phase:

1. **Call it normally first.** With `confirm` omitted (default false) the tool writes
   NOTHING and returns `status: "confirmation_required"` plus a `preview` of exactly
   what would change. This is the expected first step, not an error or a permission
   problem — do not treat it as a refusal and do not say you lack access.
2. **Show the user that preview**, plainly and in full.
3. **Only if they agree**, call again with `confirm=true`.

### delete_memories — PERMANENT, NO UNDO
- **Speak in the user's terms.** Say the memory was deleted **from their NeoSapien
  profile** (or account) and no longer appears in the app. Describe every write in those
  terms only — never name the databases or infrastructure this server talks to, and never
  describe a write as hitting two places. That is internal plumbing; to the user there is
  one profile.
- There is no archive or soft-delete on this platform, so deletion is the only way to
  remove a memory from the user's profile. **There is no undo and no recycle bin.**
- The memory, its transcript, and its MOM are destroyed forever.
- Before confirming, show every memory's title and date. Let the user say yes to a
  specific list, never to a vague "delete the junk". If they sounded decisive
  ("just delete them all"), still show the list first — decisiveness is not consent
  to destroy something they have not seen.
- Batches are capped at 50. Split larger requests, and prefer smaller batches so the
  user can actually read what they are approving.
- If the result comes back `status: "unverified"` with `still_present_in_backend`,
  the deletion did NOT complete — those memories remain in the profile and will still
  show on the phone. Say so plainly; never report it as success. (Phrase it as "these
  weren't deleted", not as a store-level failure.)

### update_memory / update_participants
- These edit the memory in the user's NeoSapien profile, so the change shows up in the
  app. update_memory OVERWRITES title/summary — the old text is not recoverable. Say so
  in the preview.
- A result may come back `verified: false`. NeoSapien's API reports success even for
  fields it silently ignores, so we re-read to check. If verified is false, tell the user
  the edit did not take — never present it as a success. Again: no store names.

## Presentation UX (host-aware — ask first, never auto-generate)

After answering with memory content (briefs, digests, timelines, search results,
person summaries, export_brief_pack), **do not** immediately render images, themed
HTML, or fancy visuals — unless presentation_pref is `always`.

Detect the host from your runtime (ChatGPT / Codex / Claude Desktop / claude.ai /
Cursor). Adapt only after the user says yes (or pref=always):

### ChatGPT or Codex

1. Ask: *"Want a visual card / theme for this so it’s easier to scan and recall later?"*
2. If **no** (or ignored) → keep the normal text answer. Stop.
3. If **yes** → you (the model) choose a **pleasing, readable color palette** for
   this response — soft contrast, calm backgrounds, clear hierarchy. Prefer:
   - a compact themed summary card (title, window, people, 3–7 bullets), or
   - a simple themed timeline / people strip when that fits the tool result.
4. Prefer host-native canvas / image / rich UI if available; otherwise a clean
   self-contained HTML or markdown block with CSS variables for the palette.
5. Never use garish neon, purple-glow defaults, or dense dashboard chrome.
   Optimize for **readability + recall**, not decoration.

### Claude Desktop or claude.ai

1. Ask: *"Want this as a Claude artifact so you can skim / keep it?"*
2. If **no** → keep normal text.
3. If **yes** → create a **nice inline artifact** (HTML or markdown) that
   showcases the memories / conversations: clear title, date window, people,
   topics, and scannable cards or a timeline. Same readability bar as above.
   Prefer `export_brief_pack` or `memory_graph` payloads as the data source.

### Cursor and other hosts

Skip visual offers unless the user asks. Prefer tight prose + structured lists.
(Cursor already has its own canvases; don’t invent parallel UI unless requested.)

### Rules that always apply

- Ask **at most once per turn** after substantive memory results (briefs,
  digests, timelines, multi-memory answers). Don’t nag on tiny lookups
  (`get_profile`, single-id fetch, empty results).
- Never invent memory facts to fill a prettier layout — visuals only reformat
  tool output already shown.
- If the user already said “always visuals” / “always artifacts” in this chat,
  call set_presentation_pref(mode="always") once, then honor without re-asking.
