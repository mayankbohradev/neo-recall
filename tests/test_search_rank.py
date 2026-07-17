"""Ranking tests for the field-weighted BM25 scorer.

Deterministic and offline — built on a small synthetic corpus rather than a live index,
so the assertions describe ranking BEHAVIOUR and never depend on anyone's real data.

The behaviours pinned here are the ones a naive BM25 gets wrong:
  * a natural-language question must not match the whole corpus via its stopwords
  * a title hit must outrank the same term buried in prose
  * naming an entity plus a topic must beat a document that only matches the topic
  * a rare term must still be findable when nothing scores above the floor
"""

from __future__ import annotations

import pytest

from neosapien_mcp.enrich.search_rank import content_tokens, rank_memories, tokenize
from neosapien_mcp.models.memory import MemoryLight


def mem(
    mid: str,
    title: str = "",
    summary: str = "",
    topics: list[str] | None = None,
    participants: list[str] | None = None,
    created: str = "2026-01-01T00:00:00Z",
) -> MemoryLight:
    return MemoryLight(
        id=mid,
        title=title,
        summary=summary,
        topics=topics or [],
        participants=participants or [],
        created_at=created,
    )


def ranked_ids(memories: list[MemoryLight], query: str) -> list[str]:
    return [m.id for _, m in rank_memories(memories, query)]


# --- tokenisation / stopwords ------------------------------------------------


def test_tokenize_lowercases_and_splits():
    assert tokenize("Pricing Strategy 2026") == ["pricing", "strategy", "2026"]


def test_content_tokens_drops_question_scaffolding():
    """A question must reduce to its content words, or it matches everything."""
    assert content_tokens("what did she say about pricing") == ["pricing"]


def test_content_tokens_keeps_meaningful_terms():
    assert set(content_tokens("dashboard automation")) == {"dashboard", "automation"}


def test_content_tokens_falls_back_when_query_is_all_stopwords():
    """Never return an empty query — degrade to the raw tokens instead."""
    assert content_tokens("what did they say") == ["what", "did", "they", "say"]


# --- the core defect: questions matching the whole corpus ---------------------


def test_question_does_not_match_documents_sharing_only_stopwords():
    corpus = [
        mem("hit", title="Pricing Review", summary="Annual vs monthly pricing."),
        mem("noise1", summary="What did we do about the thing? I said it was fine."),
        mem("noise2", summary="They talked about that, and did say something."),
    ]
    out = ranked_ids(corpus, "what did she say about pricing")
    assert out[0] == "hit"
    assert "noise1" not in out and "noise2" not in out


# --- field weighting ---------------------------------------------------------


def test_title_match_outranks_summary_match():
    corpus = [
        mem("summary_only", summary="we mentioned onboarding once in passing here"),
        mem("titled", title="Onboarding Redesign"),
    ]
    assert ranked_ids(corpus, "onboarding")[0] == "titled"


def test_topic_match_outranks_summary_match():
    corpus = [
        mem("summary_only", summary="a passing remark about migration mid-paragraph"),
        mem("topical", topics=["migration"]),
    ]
    assert ranked_ids(corpus, "migration")[0] == "topical"


# --- entity + topic conjunction ----------------------------------------------


def test_entity_plus_topic_outranks_topic_only():
    """The defect this fixes: a topic-heavy doc burying the conversation actually wanted."""
    corpus = [
        mem(
            "topic_only",
            title="Pricing Deep Dive",
            summary="pricing pricing pricing tiers and pricing models discussed at length",
        ),
        mem("both", title="Roadmap Sync", summary="we covered pricing", participants=["Ada"]),
    ]
    assert ranked_ids(corpus, "what did ada say about pricing")[0] == "both"


def test_entity_named_in_participants_is_findable():
    corpus = [mem("a", participants=["Ada"]), mem("b", participants=["Grace"])]
    assert ranked_ids(corpus, "ada") == ["a"]


def test_entity_match_alone_does_not_beat_full_conjunction():
    corpus = [
        mem("person_only", participants=["Ada"], summary="unrelated chatter"),
        mem("conjunction", participants=["Ada"], title="Budget", summary="budget planning"),
    ]
    assert ranked_ids(corpus, "ada budget")[0] == "conjunction"


# --- coverage ----------------------------------------------------------------


def test_covering_both_terms_beats_repeating_one():
    corpus = [
        mem("repeats_one", summary="latency latency latency latency latency"),
        mem("covers_both", summary="latency in the caching layer"),
    ]
    assert ranked_ids(corpus, "latency caching")[0] == "covers_both"


def test_exact_phrase_is_rewarded():
    corpus = [
        mem("scattered", summary="the release was delayed; notes on the plan"),
        mem("phrase", summary="we discussed the release plan today"),
    ]
    assert ranked_ids(corpus, "release plan")[0] == "phrase"


# --- floor and fallback ------------------------------------------------------


def test_irrelevant_documents_are_dropped_entirely():
    corpus = [
        mem("relevant", title="Kubernetes Migration"),
        mem("irrelevant", summary="lunch plans and weekend chatter"),
    ]
    assert ranked_ids(corpus, "kubernetes") == ["relevant"]


def test_rare_term_still_returns_a_result_via_fallback():
    """A strict floor must never turn a real match into 'nothing found'."""
    corpus = [mem("a", summary="the zzyzx protocol was mentioned briefly")]
    assert ranked_ids(corpus, "zzyzx") == ["a"]


def test_no_match_returns_empty_rather_than_the_whole_corpus():
    corpus = [mem("a", title="Alpha"), mem("b", title="Beta")]
    assert ranked_ids(corpus, "nonexistentterm") == []


def test_empty_query_preserves_input_order():
    corpus = [mem("a"), mem("b")]
    assert ranked_ids(corpus, "") == ["a", "b"]


# --- ordering / stability ----------------------------------------------------


def test_ties_break_toward_the_more_recent_memory():
    corpus = [
        mem("older", title="Standup", created="2026-01-01T00:00:00Z"),
        mem("newer", title="Standup", created="2026-06-01T00:00:00Z"),
    ]
    assert ranked_ids(corpus, "standup")[0] == "newer"


@pytest.mark.parametrize("query", ["pricing", "what about pricing", "PRICING", "  pricing  "])
def test_ranking_is_robust_to_query_phrasing(query):
    corpus = [mem("hit", title="Pricing"), mem("miss", title="Logistics")]
    assert ranked_ids(corpus, query)[0] == "hit"
