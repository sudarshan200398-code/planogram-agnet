"""Tests for sentence-level politeness splitting in rule-based fallback."""
import pytest

from planogram_agent.agents.query import rule_based_fallback
from planogram_agent.settings import Settings


def test_fallback_drops_politeness_wrapper_sentences():
    settings = Settings()
    query = "Good morning! Could you please help me find organic apples? Thank you so much!"
    res = rule_based_fallback(query, settings)
    assert res.intent == "find"
    assert len(res.items) == 1
    assert res.items[0].text == "organic apples"
    assert "?" not in res.items[0].text
    assert "!" not in res.items[0].text


def test_fallback_drops_hi_there_and_cheers():
    settings = Settings()
    query = "Hi there. Where is sparkling water? Cheers!"
    res = rule_based_fallback(query, settings)
    assert res.intent == "find"
    assert len(res.items) == 1
    assert res.items[0].text == "sparkling water"
    assert "?" not in res.items[0].text
    assert "!" not in res.items[0].text


def test_fallback_does_not_split_decimal_numbers_like_2_5():
    settings = Settings()
    query = "Where is dog food 2.5 kg?"
    res = rule_based_fallback(query, settings)
    assert res.intent == "find"
    assert len(res.items) == 1
    assert "2.5" in res.items[0].text
    assert res.items[0].text == "dog food 2.5 kg"


def test_fallback_only_politeness_returns_unknown_without_crashing():
    settings = Settings()
    for query in [
        "Thank you so much! Cheers!",
        "Good morning! Many thanks! Cheers!",
        "Much appreciated, thank you!",
        "Thanks a lot!",
    ]:
        res = rule_based_fallback(query, settings)
        assert res.intent == "unknown"
        assert len(res.items) == 0
