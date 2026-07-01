"""Unit tests for parse + enrichment (no network)."""

from __future__ import annotations

from neosapien_mcp.client.parse import parse_light, parse_detail
from neosapien_mcp.enrich.quality import compute_quality_score, triage_batch
from neosapien_mcp.models.memory import MemoryLight
from neosapien_mcp.service import normalize_end_date, apply_filters


def test_integer_value_is_string():
    doc = {
        "name": "projects/neo-app-prod/databases/(default)/documents/users/u/memories/abc",
        "fields": {
            "title": {"stringValue": "Hi"},
            "duration_sec": {"integerValue": "42"},
            "archived": {"booleanValue": False},
            "created_at": {"timestampValue": "2026-07-10T15:30:01.578Z"},
            "topics": {"arrayValue": {"values": [{"stringValue": "AI"}]}},
        },
    }
    m = parse_light(doc)
    assert m is not None
    assert m.id == "abc"
    assert m.duration_sec == 42.0
    assert m.topics == ["AI"]
    assert m.created_at.endswith("Z")


def test_mom_key_variants():
    doc = {
        "name": ".../memories/x",
        "fields": {
            "title": {"stringValue": "T"},
            "mom": {"stringValue": "## Notes\n- a"},
        },
    }
    d = parse_detail(doc, include_mom=True)
    assert d is not None
    assert d.mom and d.mom.startswith("##")


def test_end_date_full_day():
    assert normalize_end_date("2026-07-10") == "2026-07-10T23:59:59Z"


def test_quality_and_triage():
    noise = MemoryLight(id="1", duration_sec=1.0)
    keep = MemoryLight(
        id="2",
        title="Standup",
        summary="We decided to ship the RAG pipeline this week with BM25.",
        duration_sec=400,
        participants=["Mayank", "Cofounder"],
        topics=["RAG", "Product"],
        emotions=["focused"],
    )
    assert compute_quality_score(keep) > compute_quality_score(noise)
    results = triage_batch([noise, keep])
    by_id = {r.id: r for r in results}
    assert by_id["1"].label == "noise"
    assert by_id["2"].label == "keep"


def test_entity_filter():
    memories = [
        MemoryLight(id="a", participants=["Preetam"], created_at="2026-07-10T10:00:00Z"),
        MemoryLight(id="b", mentioned_entities=["NeoSapien"], created_at="2026-07-10T11:00:00Z"),
    ]
    hit = apply_filters(memories, entities=["preetam"])
    assert [m.id for m in hit] == ["a"]


def test_relatedness_and_timeline():
    from neosapien_mcp.enrich import related, briefs

    a = MemoryLight(
        id="1",
        title="RAG talk",
        topics=["RAG"],
        participants=["Mayank", "Cofounder"],
        mentioned_entities=["BM25"],
        created_at="2026-07-01T10:00:00Z",
        summary="Discussed BM25",
    )
    b = MemoryLight(
        id="2",
        title="Follow-up",
        topics=["RAG", "Product"],
        participants=["Mayank"],
        mentioned_entities=["BM25"],
        created_at="2026-07-08T10:00:00Z",
        summary="Shipped hybrid search",
    )
    c = MemoryLight(
        id="3",
        title="Unrelated",
        topics=["Sleep"],
        created_at="2026-07-09T10:00:00Z",
    )
    assert related.relatedness_score(a, b) > related.relatedness_score(a, c)
    items = related.find_related([a, b, c], "1", limit=5)
    assert items and items[0]["id"] == "2"

    tl = briefs.build_topic_timeline([a, b, c], "RAG")
    assert "Topic timeline" in tl
    assert "2026-07-01" in tl
    assert "2026-07-08" in tl


def test_entities_become_participants_and_duration_from_bounds():
    doc = {
        "name": ".../memories/xyz",
        "fields": {
            "title": {"stringValue": "Chat"},
            "entities": {
                "arrayValue": {
                    "values": [
                        {"stringValue": "Mayank Bohra"},
                        {"stringValue": "Colleague"},
                    ]
                }
            },
            "participants": {"arrayValue": {}},
            "domain": {"stringValue": "Operations"},
            "questions": {"arrayValue": {"values": [{"stringValue": "Who owns the cut?"}]}},
            "started_at": {"timestampValue": "2026-07-10T10:00:01.578Z"},
            "finished_at": {"timestampValue": "2026-07-10T10:00:26.689Z"},
            "created_at": {"timestampValue": "2026-07-10T10:00:01.578Z"},
        },
    }
    m = parse_light(doc)
    assert m is not None
    assert m.participants == ["Mayank Bohra", "Colleague"]
    assert "Operations" in m.domains
    assert m.questions == ["Who owns the cut?"]
    assert 24.0 <= m.duration_sec <= 26.0


def test_bm25_ranks_relevant_first():
    from neosapien_mcp.enrich.search_rank import rank_memories

    memories = [
        MemoryLight(
            id="1",
            title="Grocery list",
            summary="Milk and eggs",
            created_at="2026-07-01T10:00:00Z",
        ),
        MemoryLight(
            id="2",
            title="Team meeting about RAG",
            summary="Discussed BM25 hybrid search for meeting notes",
            topics=["meeting", "RAG"],
            created_at="2026-07-02T10:00:00Z",
        ),
        MemoryLight(
            id="3",
            title="Casual chat",
            summary="Weather was nice",
            created_at="2026-07-03T10:00:00Z",
        ),
    ]
    ranked = rank_memories(memories, "meeting")
    assert ranked
    assert ranked[0][1].id == "2"


def test_action_items_and_compare_and_duplicates():
    from neosapien_mcp.enrich import analytics, extract, duplicates, graph

    a = MemoryLight(
        id="1",
        title="Decided to ship BM25",
        summary="We decided to ship hybrid search. Follow up next Monday with Varun.",
        participants=["Mayank", "Varun"],
        topics=["RAG"],
        questions=["Who owns the BM25 rollout?"],
        created_at="2026-07-01T10:00:00Z",
        duration_sec=120,
    )
    b = MemoryLight(
        id="2",
        title="Revisit BM25 choice",
        summary="Changed our mind — instead of BM25 we may use embeddings only.",
        participants=["Mayank"],
        topics=["RAG"],
        created_at="2026-07-08T10:00:00Z",
        duration_sec=90,
    )
    c = MemoryLight(
        id="3",
        title="Decided to ship BM25",
        summary="We decided to ship hybrid search. Follow up next Monday with Varun.",
        created_at="2026-07-01T11:00:00Z",
        duration_sec=10,
    )
    actions = extract.action_items([a, b])
    assert actions["count"] >= 1
    follows = extract.follow_ups_due([a, b])
    assert follows["count"] >= 1
    decisions = extract.decision_log([a, b], topic="RAG")
    assert decisions["decision_count"] >= 1
    assert decisions["possible_revisions"]

    cmp = analytics.compare_periods(
        [a, b],
        period_a_start="2026-07-01T00:00:00Z",
        period_a_end="2026-07-07T23:59:59Z",
        period_b_start="2026-07-08T00:00:00Z",
        period_b_end="2026-07-14T23:59:59Z",
    )
    assert cmp["period_a"]["count"] == 1
    assert cmp["period_b"]["count"] == 1

    dups = duplicates.duplicate_candidates([a, b, c], threshold=0.5, limit=5)
    assert dups["count"] >= 1

    g = graph.memory_graph([a, b, c], seed_id="1", limit=5)
    assert g["node_count"] >= 2
    assert g["edges"]


def test_presentation_pref_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOSAPIEN_CACHE_PATH", str(tmp_path / "m.db"))
    from neosapien_mcp.cache.sqlite import MemoryCache

    cache = MemoryCache(path=tmp_path / "m.db")
    cache.set_meta("presentation_pref", "always")
    assert cache.get_meta("presentation_pref") == "always"
    cache.close()
