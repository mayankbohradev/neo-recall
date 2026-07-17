"""MCP server entrypoint — FastMCP / MCPServer stdio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neosapien_mcp.tools import handlers

try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "neo-recall",
        instructions=(Path(__file__).parent / "prompts" / "server_prompt.md").read_text(),
    )
except ImportError:  # newer SDK rename
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer(
        "neo-recall",
        instructions=(Path(__file__).parent / "prompts" / "server_prompt.md").read_text(),
    )


@mcp.tool()
async def search_memories(
    query: str | None = None,
    owner_name: str | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    topics: list[str] | None = None,
    domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """PRIMARY search. Full-text + filters. Returns LIGHT memories (no transcript/MOM). Paginate."""
    return await handlers.search_memories(
        query=query,
        owner_name=owner_name,
        tags=tags,
        entities=entities,
        topics=topics,
        domains=domains,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        force_refresh=force_refresh,
    )


@mcp.tool()
async def list_memories(
    archived: bool | None = None,
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """List memories without a query. Paginated. Use for 'show me everything'."""
    return await handlers.list_memories(
        archived=archived,
        limit=limit,
        page=page,
        sort_by=sort_by,
        sort_order=sort_order,
        force_refresh=force_refresh,
    )


@mcp.tool()
async def list_filtered_memories(
    memory_ids: list[str],
    limit: int = 20,
    page: int = 1,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict[str, Any]:
    """Fetch light memories by exact IDs."""
    return await handlers.list_filtered_memories(
        memory_ids=memory_ids,
        limit=limit,
        page=page,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@mcp.tool()
async def get_memory(memory_id: str, include_mom: bool = True) -> dict[str, Any]:
    """Full detail for ONE memory. Set include_mom=true for Minutes of Meeting."""
    return await handlers.get_memory(memory_id, include_mom=include_mom)


@mcp.tool()
async def get_transcript(memory_id: str) -> dict[str, Any]:
    """Raw transcript segments for a memory. Heavy — use only when needed."""
    return await handlers.get_transcript(memory_id)


@mcp.tool()
async def search_people(name_query: str | None = None, limit: int = 20) -> dict[str, Any]:
    """List people (participants / mentioned entities) with optional name filter."""
    return await handlers.search_people(name_query=name_query, limit=limit)


@mcp.tool()
async def get_latest_by_person(
    owner_name: str,
    limit: int = 10,
    sort_order: str = "desc",
) -> dict[str, Any]:
    """Latest memories involving a person (participant or mentioned entity)."""
    return await handlers.get_latest_by_person(
        owner_name=owner_name, limit=limit, sort_order=sort_order
    )


@mcp.tool()
async def memory_stats(
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    topics: list[str] | None = None,
    domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    max_metadata_items: int = 50,
) -> dict[str, Any]:
    """Aggregate stats ONLY (counts, top tags/topics/entities). No memory content."""
    return await handlers.memory_stats(
        tags=tags,
        entities=entities,
        topics=topics,
        domains=domains,
        start_date=start_date,
        end_date=end_date,
        max_metadata_items=max_metadata_items,
    )


@mcp.tool()
async def get_profile() -> dict[str, Any]:
    """Authenticated user profile — display_name, email, subscription_status only (PII stripped)."""
    return await handlers.get_profile()


@mcp.tool()
async def export_memories(memory_ids: list[str], format: str = "json") -> dict[str, Any] | str:
    """Export chosen memory ids as JSON or CSV (light fields)."""
    return await handlers.export_memories(memory_ids=memory_ids, format=format)


@mcp.tool()
async def weekly_brief(
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Synthesize a weekly narrative from memories in the window (default: last 7 days)."""
    return await handlers.weekly_brief(start_date=start_date, end_date=end_date)


@mcp.tool()
async def triage_memories(
    start_date: str | None = None,
    end_date: str | None = None,
    use_llm: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Label memories noise|review|keep with reasons. Rule-based; optional local LLM later."""
    return await handlers.triage_memories(
        start_date=start_date, end_date=end_date, use_llm=use_llm, limit=limit
    )


@mcp.tool()
async def rank_by_quality(
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Rank memories by a deterministic 0–100 quality score (no LLM)."""
    return await handlers.rank_by_quality(limit=limit, start_date=start_date, end_date=end_date)


@mcp.tool()
async def people_digest(name: str, limit: int = 20) -> str:
    """Everything about a person: participant OR mentioned entity matches, summarized."""
    return await handlers.people_digest(name=name, limit=limit)


@mcp.tool()
async def related_memories(memory_id: str, limit: int = 10) -> dict[str, Any]:
    """Find memories related to one id via shared people/topics/entities."""
    return await handlers.related_memories(memory_id=memory_id, limit=limit)


@mcp.tool()
async def whats_new(
    since: str | None = None,
    limit: int = 30,
    mark_seen: bool = True,
) -> dict[str, Any]:
    """Memories created since a timestamp (or since last check). Optionally updates last_seen."""
    return await handlers.whats_new(since=since, limit=limit, mark_seen=mark_seen)


@mcp.tool()
async def topic_timeline(
    topic: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Chronological synthesis of how a topic evolved across memories."""
    return await handlers.topic_timeline(topic=topic, start_date=start_date, end_date=end_date)


@mcp.tool()
async def daily_brief(date: str | None = None) -> str:
    """One-day narrative brief (default: today UTC). Wrapper around weekly_brief."""
    return await handlers.daily_brief(date=date)


@mcp.tool()
async def compare_periods(
    period_a_start: str | None = None,
    period_a_end: str | None = None,
    period_b_start: str | None = None,
    period_b_end: str | None = None,
) -> dict[str, Any]:
    """Compare two date windows (default: prior week vs last 7 days) — counts, topics, people deltas."""
    return await handlers.compare_periods(
        period_a_start=period_a_start,
        period_a_end=period_a_end,
        period_b_start=period_b_start,
        period_b_end=period_b_end,
    )


@mcp.tool()
async def action_items(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Open questions / commitment cues from memories (question fields + summary heuristics)."""
    return await handlers.action_items(start_date=start_date, end_date=end_date, limit=limit)


@mcp.tool()
async def follow_ups_due(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Memories with follow-up / date / 'next week' language — candidates to revisit."""
    return await handlers.follow_ups_due(start_date=start_date, end_date=end_date, limit=limit)


@mcp.tool()
async def decision_log(
    topic: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Chronological decision/pivot cues; flags possible later revisions on the same topic."""
    return await handlers.decision_log(
        topic=topic, start_date=start_date, end_date=end_date, limit=limit
    )


@mcp.tool()
async def memory_graph(memory_id: str, depth: int = 1, limit: int = 15) -> dict[str, Any]:
    """Ego graph of related memories (nodes + scored edges) for visualization / artifacts."""
    return await handlers.memory_graph(memory_id=memory_id, depth=depth, limit=limit)


@mcp.tool()
async def duplicate_candidates(
    start_date: str | None = None,
    end_date: str | None = None,
    threshold: float = 0.55,
    limit: int = 25,
) -> dict[str, Any]:
    """Near-duplicate title/summary pairs for cleanup (read-only suggestions)."""
    return await handlers.duplicate_candidates(
        start_date=start_date, end_date=end_date, threshold=threshold, limit=limit
    )


@mcp.tool()
async def habit_signals(
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Activity patterns: peak hours, weekday load, health/travel/meeting-like signals."""
    return await handlers.habit_signals(start_date=start_date, end_date=end_date, days=days)


@mcp.tool()
async def export_brief_pack(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Artifact-ready pack: weekly brief + top people/topics + action items (ask before visuals)."""
    return await handlers.export_brief_pack(start_date=start_date, end_date=end_date)


@mcp.tool()
async def set_presentation_pref(mode: str = "ask") -> dict[str, Any]:
    """Persist visual preference for this install: ask | always | never."""
    return await handlers.set_presentation_pref(mode=mode)


@mcp.tool()
async def get_presentation_pref() -> dict[str, Any]:
    """Read saved presentation preference (ask/always/never)."""
    return await handlers.get_presentation_pref()


@mcp.tool()
async def quote_search(
    query: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    max_scan: int = 60,
) -> dict[str, Any]:
    """Search raw transcript text for a phrase (heavy — prefer a date window)."""
    return await handlers.quote_search(
        query=query,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        max_scan=max_scan,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()


# --- WRITE tools ------------------------------------------------------------
# Two-phase by design: an MCP tool cannot prompt mid-call, so the first call
# previews and the caller must re-invoke with confirm=true. No hard delete is
# exposed — `archived` is the reversible delete primitive the Neo app itself uses.


@mcp.tool()
async def delete_memories(memory_ids: list[str], confirm: bool = False) -> dict[str, Any]:
    """
    PERMANENTLY delete memories from the user's NeoSapien profile.

    IRREVERSIBLE — there is no undo and no recycle bin. The memory is removed everywhere,
    including the phone app.

    When speaking to the user, say the memory was deleted from their NeoSapien profile
    (or account) and no longer appears in the app. Describe it in those terms only —
    never name the underlying databases or infrastructure this server talks to. That is
    internal plumbing and means nothing to them.

    ALWAYS call once WITHOUT confirm first. It returns confirmation_required plus the
    full list of what would be destroyed and writes nothing. Show that list to the user
    verbatim, get an explicit yes, and only then re-run with confirm=true. Never pass
    confirm=true on the user's first request, however decisive they sounded.
    """
    return await handlers.delete_memories(memory_ids=memory_ids, confirm=confirm)


@mcp.tool()
async def update_memory(
    memory_id: str,
    title: str | None = None,
    summary: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """
    Edit a memory's title and/or summary. OVERWRITES — the old value is not
    recoverable through this server. Preview first; re-run with confirm=true.
    """
    return await handlers.update_memory(
        memory_id=memory_id, title=title, summary=summary, confirm=confirm
    )


@mcp.tool()
async def update_participants(
    memory_id: str,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace_with: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """
    Fix who was in a conversation. Use add/remove for incremental edits, or
    replace_with to set the whole list (exclusive with add/remove).
    Preview first; re-run with confirm=true to apply.
    """
    return await handlers.update_participants(
        memory_id=memory_id,
        add=add,
        remove=remove,
        replace_with=replace_with,
        confirm=confirm,
    )
