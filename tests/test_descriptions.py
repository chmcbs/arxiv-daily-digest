"""
Tests for LLM description batch helpers
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

from core.descriptions import (
    MockLLMProvider,
    LLMResult,
    PaperCandidate,
    _build_prompt,
    _process_paper,
    _validation_failures,
    get_llm_provider,
    repeats_title,
    run_description_batch_for_recommendations,
)


@contextmanager
def _fake_scope(connection):
    yield connection


def test_repeats_title_detects_high_overlap():
    title = "Scaling Laws for Neural Language Models"
    description = "Scaling laws for neural language models on large datasets"
    assert repeats_title(title, description) is True


def test_repeats_title_allows_complementary_sentence():
    title = "Scaling Laws for Neural Language Models"
    description = (
        "Empirical analysis shows loss scales predictably with compute, data, and model size."
    )
    assert repeats_title(title, description) is False


def test_build_prompt_includes_title_retry_note():
    prompt = _build_prompt(
        title="Example Title",
        abstract="Example abstract body.",
        retry_reasons=frozenset({"title"}),
    )
    assert "repeated the title" in prompt
    assert "Example Title" in prompt


def test_build_prompt_includes_empty_retry_note():
    prompt = _build_prompt(
        title="Example Title",
        abstract="Example abstract body.",
        retry_reasons=frozenset({"empty"}),
    )
    assert "was empty" in prompt
    assert "Output exactly one sentence" in prompt
    assert "repeated the title" not in prompt


def test_build_prompt_includes_length_retry_note():
    prompt = _build_prompt(
        title="Example Title",
        abstract="Example abstract body.",
        retry_reasons=frozenset({"length"}),
    )
    assert "too long" in prompt
    assert "no more than 35 words" in prompt
    assert "was empty" not in prompt


def test_build_prompt_includes_both_retry_notes():
    prompt = _build_prompt(
        title="Example Title",
        abstract="Example abstract body.",
        retry_reasons=frozenset({"title", "length"}),
    )
    assert "repeated the title" in prompt
    assert "no more than 35 words" in prompt


def test_validation_failures_detects_empty_length_and_title():
    title = "Transformers Improve Benchmark Accuracy"
    too_long = " ".join(["word"] * 51)
    assert _validation_failures(title=title, description=too_long) == frozenset(
        {"length"}
    )
    assert _validation_failures(
        title=title,
        description="Transformers improve benchmark accuracy on standard tasks.",
    ) == frozenset({"title"})
    assert _validation_failures(title=title, description="") == frozenset({"empty"})


def test_get_llm_provider_returns_mock():
    provider = get_llm_provider("mock")
    assert provider.provider_name == "mock"


def test_process_paper_persists_successful_description(monkeypatch):
    paper = PaperCandidate(
        arxiv_id="2601.00001",
        title="A Completely Different Headline About Widgets",
        abstract="We evaluate widget throughput on synthetic workloads.",
        max_score=0.91,
    )
    provider = MockLLMProvider(
        response_text=(
            "Synthetic workload experiments quantify widget throughput limits across hardware tiers."
        )
    )
    persist = Mock(return_value=True)
    monkeypatch.setattr("core.descriptions._persist_description", persist)

    outcome = _process_paper(
        paper,
        provider,
        batch_id="batch-1",
        request_timeout_s=5,
    )

    assert outcome.status == "succeeded"
    persist.assert_called_once()


def test_process_paper_retries_on_title_repetition(monkeypatch):
    paper = PaperCandidate(
        arxiv_id="2601.00002",
        title="Transformers Improve Benchmark Accuracy",
        abstract="We study benchmark accuracy under varied settings.",
        max_score=0.88,
    )
    provider = MockLLMProvider()
    provider.generate = Mock(
        side_effect=[
            LLMResult(
                text="Transformers improve benchmark accuracy on standard tasks.",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            ),
            LLMResult(
                text="Benchmark accuracy gains come from a revised training schedule and data mix.",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            ),
        ]
    )
    persist = Mock(return_value=True)
    monkeypatch.setattr("core.descriptions._persist_description", persist)

    outcome = _process_paper(
        paper,
        provider,
        batch_id="batch-2",
        request_timeout_s=5,
    )

    assert outcome.status == "succeeded"
    assert provider.generate.call_count == 2


def test_process_paper_retries_on_length_failure(monkeypatch):
    paper = PaperCandidate(
        arxiv_id="2601.00004",
        title="Efficient GPU Kernels for Sparse Attention",
        abstract="We benchmark sparse attention kernels across GPU generations.",
        max_score=0.87,
    )
    provider = MockLLMProvider()
    provider.generate = Mock(
        side_effect=[
            LLMResult(
                text=" ".join(["verbose"] * 55),
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            ),
            LLMResult(
                text="Benchmarks show sparse attention kernels scale best on newer GPUs.",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            ),
        ]
    )
    persist = Mock(return_value=True)
    monkeypatch.setattr("core.descriptions._persist_description", persist)

    outcome = _process_paper(
        paper,
        provider,
        batch_id="batch-3",
        request_timeout_s=5,
    )

    assert outcome.status == "succeeded"
    assert provider.generate.call_count == 2
    retry_prompt = provider.generate.call_args_list[1].args[0]
    assert "too long" in retry_prompt
    assert "no more than 35 words" in retry_prompt
    assert "repeated the title" not in retry_prompt


def test_process_paper_retries_on_empty_response(monkeypatch):
    paper = PaperCandidate(
        arxiv_id="2601.00005",
        title="Robust Planning Under Uncertainty",
        abstract="We study planning algorithms for uncertain environments.",
        max_score=0.86,
    )
    provider = MockLLMProvider()
    provider.generate = Mock(
        side_effect=[
            LLMResult(text="   ", input_tokens=10, output_tokens=0, latency_ms=1),
            LLMResult(
                text="Planning experiments compare robustness across uncertain benchmark settings.",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            ),
        ]
    )
    persist = Mock(return_value=True)
    monkeypatch.setattr("core.descriptions._persist_description", persist)

    outcome = _process_paper(
        paper,
        provider,
        batch_id="batch-4",
        request_timeout_s=5,
    )

    assert outcome.status == "succeeded"
    assert provider.generate.call_count == 2
    retry_prompt = provider.generate.call_args_list[1].args[0]
    assert "was empty" in retry_prompt
    assert "repeated the title" not in retry_prompt


def test_run_description_batch_for_recommendations_records_stats(monkeypatch):
    candidates = [
        PaperCandidate(
            arxiv_id="2601.00003",
            title="Different Title About Systems",
            abstract="Abstract text.",
            max_score=0.95,
        )
    ]
    monkeypatch.setattr(
        "core.descriptions.fetch_paper_candidates",
        Mock(return_value=candidates),
    )
    monkeypatch.setattr(
        "core.descriptions._process_paper",
        Mock(
            return_value=Mock(
                arxiv_id="2601.00003",
                status="succeeded",
                input_tokens=10,
                output_tokens=5,
                latency_ms=3,
            )
        ),
    )

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(
        "core.descriptions.connection_scope",
        lambda conn=None: _fake_scope(connection),
    )

    stats = run_description_batch_for_recommendations(
        run_ids=["run-1"],
        provider=MockLLMProvider(),
    )

    assert stats["candidate_count"] == 1
    assert stats["attempted"] == 1
    assert stats["succeeded"] == 1
    cursor.execute.assert_called()
