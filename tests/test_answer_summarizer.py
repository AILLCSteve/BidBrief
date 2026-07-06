"""
Tests for Layer 6.5 — AnswerSummarizer.

For each answered question, an expert-personified synthesis pass distills the
appended pile of verbatim quotes into a direct 1-3 sentence summary answer,
stored on the primary Answer.summary and surfaced as `answer_summary` in the
legacy payload + a dedicated column in every export.
"""
import asyncio
import json

import pytest

from services.hotdog.models import (
    Answer, ExpertPersona, ParsedConfig, Question, Section
)
from services.hotdog.answer_summarizer import AnswerSummarizer


class _FakeCompletions:
    def __init__(self, payloads, raise_for_sections=None):
        self.payloads = payloads  # list of dicts returned per call, in order
        self.calls = []
        self.raise_for_sections = raise_for_sections or set()

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["messages"][0]["content"]
        for name in self.raise_for_sections:
            if name in system:
                raise RuntimeError("boom")
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]

        class _Msg:
            content = json.dumps(payload)

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

            class usage:
                total_tokens = 42

        return _Resp()


class _FakeClient:
    def __init__(self, payloads, raise_for_sections=None):
        self.chat = type("chat", (), {})()
        self.chat.completions = _FakeCompletions(payloads, raise_for_sections)


def _fixture():
    s1 = Section(id="general_info", name="General", description="d")
    s1.add_question(Question(id="Q1", text="Project name?", section_id="general_info"))
    s1.add_question(Question(id="Q2", text="Deadline?", section_id="general_info"))
    config = ParsedConfig(
        name="t", version="1", sections=[s1],
        section_map={"general_info": s1},
        question_map={q.id: q for q in s1.questions},
    )
    experts = {
        "general_info": ExpertPersona(
            id="e1", section_id="general_info", section_name="General",
            name="Gen Expert", specialization="General bid analysis",
            system_prompt="sp", citation_strategy="cs", answer_format="af",
        )
    }
    accumulation = {
        "Q1": [Answer(question_id="Q1", text="Alpha Plant <PDF pg 2>", pages=[2],
                      confidence=0.9, expert="Gen Expert", window=1)],
        "Q2": [],  # unanswered — must be skipped
    }
    return config, experts, accumulation


def test_summaries_applied_to_primary_answers():
    config, experts, acc = _fixture()
    client = _FakeClient([{"summaries": [{"question_id": "Q1", "summary": "The project is Alpha Plant."}]}])
    summarizer = AnswerSummarizer(client, "gpt-5.4")
    asyncio.run(summarizer.summarize_answers(acc, config, experts))
    assert acc["Q1"][0].summary == "The project is Alpha Plant."
    # Unanswered question untouched and not sent
    sent = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "Q2" not in sent


def test_section_failure_is_non_fatal():
    config, experts, acc = _fixture()
    client = _FakeClient([{"summaries": []}], raise_for_sections={"General"})
    summarizer = AnswerSummarizer(client, "gpt-5.4")
    asyncio.run(summarizer.summarize_answers(acc, config, experts))  # must not raise
    assert acc["Q1"][0].summary == ""


def test_only_question_ids_limits_scope():
    config, experts, acc = _fixture()
    acc["Q2"] = [Answer(question_id="Q2", text="June 1 <PDF pg 4>", pages=[4],
                        confidence=0.8, expert="Gen Expert", window=2)]
    client = _FakeClient([{"summaries": [{"question_id": "Q2", "summary": "Bids due June 1."}]}])
    summarizer = AnswerSummarizer(client, "gpt-5.4")
    asyncio.run(summarizer.summarize_answers(acc, config, experts, only_question_ids={"Q2"}))
    sent = client.chat.completions.calls[0]["messages"][1]["content"]
    assert "Q1" not in sent
    assert acc["Q2"][0].summary == "Bids due June 1."
    assert acc["Q1"][0].summary == ""


def test_answer_model_has_summary_default():
    a = Answer(question_id="Q9", text="x <PDF pg 1>", pages=[1],
               confidence=0.5, expert="E", window=0)
    assert a.summary == ""


# ---------------------------------------------------------------------------
# Integration surfaces: legacy transform + browser format carry the summary
# ---------------------------------------------------------------------------

def test_legacy_transform_emits_answer_summary():
    from app import _transform_to_legacy_format
    hotdog_output = {
        "sections": [{
            "section_id": "s1", "section_name": "General", "description": "",
            "questions": [
                {"question_id": "Q1", "question_text": "Name?", "has_answer": True,
                 "primary_answer": {"text": "Alpha <PDF pg 2>", "pages": [2],
                                    "confidence": 0.9, "footnote": "",
                                    "summary": "The project is Alpha."}},
                {"question_id": "Q2", "question_text": "Deadline?", "has_answer": False,
                 "primary_answer": None},
            ],
        }],
    }
    legacy = _transform_to_legacy_format(hotdog_output)
    q1, q2 = legacy["sections"][0]["questions"]
    assert q1["answer_summary"] == "The project is Alpha."
    assert q2["answer_summary"] is None
    # Column order contract: summary sits between answer and page_citations
    keys = list(q1.keys())
    assert keys.index("answer") < keys.index("answer_summary") < keys.index("page_citations")


def test_browser_format_includes_summary():
    from datetime import datetime
    from services.hotdog.output_compiler import OutputCompiler
    from services.hotdog.models import AnalysisResult
    config, _, acc = _fixture()
    acc["Q1"][0].summary = "The project is Alpha Plant."
    result = AnalysisResult(
        document_name="doc.pdf", total_pages=3, pages_analyzed=3,
        questions=acc, footnotes=[], metadata={},
        started_at=datetime.now(), completed_at=datetime.now(),
        total_tokens=1, estimated_cost=0.0,
    )
    browser = OutputCompiler().format_for_browser(result, config)
    q1 = browser["sections"][0]["questions"][0]
    assert q1["primary_answer"]["summary"] == "The project is Alpha Plant."
