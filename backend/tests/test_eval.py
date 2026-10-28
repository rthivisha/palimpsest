"""Unit tests for the PALIMPSEST evaluation harness and statistical reporting."""
import os
import tempfile
import pytest

from backend.app.core.outcomes import RunOutcome, EvalOutcome, determine_verified_outcome
from backend.eval.harness import EvalConfig, EvalHarness, compute_wilson_interval, compute_percentiles
from backend.app.llm.fake import FakeLLMBackend


@pytest.fixture
def fixture_dataset_path():
    path = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures", "fixture_samples.jsonl")
    return os.path.abspath(path)


@pytest.fixture
def temp_eval_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestWilsonScoreIntervals:
    """Verifies statistical correctness of Wilson Score Interval calculation."""

    def test_zero_total_returns_zero(self):
        assert compute_wilson_interval(0, 0) == (0.0, 0.0)

    def test_zero_successes_has_valid_lower_bound(self):
        low, high = compute_wilson_interval(0, 100)
        assert low == 0.0
        assert high > 0.0  # Wilson interval gives small upper bound rather than 0.0

    def test_full_successes_has_valid_upper_bound(self):
        low, high = compute_wilson_interval(100, 100)
        assert low < 100.0
        assert high == 100.0

    def test_fifty_percent_symmetry(self):
        low, high = compute_wilson_interval(50, 100)
        # Symmetrical around 50%
        diff_low = 50.0 - low
        diff_high = high - 50.0
        assert abs(diff_low - diff_high) < 0.1

    def test_percentiles_calculation(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        p50, p95 = compute_percentiles(values)
        assert p50 == 30.0
        assert p95 == 50.0


class TestEvalHarness:
    """Verifies operational rules, refusal of mock backends, and resumption."""

    def test_refuses_fake_backend_without_allow_fake_flag(self, fixture_dataset_path, temp_eval_db):
        """Harness must strictly raise RuntimeError when fake backend is passed without allow_fake."""
        cfg = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            backend_name="fake",
            allow_fake=False,
        )
        with pytest.raises(RuntimeError, match="Evaluation harness refused to run against 'fake' backend without --allow-fake"):
            EvalHarness(cfg)

    def test_runs_cleanly_with_allow_fake_on_fixture(self, fixture_dataset_path, temp_eval_db):
        """Runs the 10-row fixture with --allow-fake and generates summary."""
        cfg = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            backend_name="fake",
            allow_fake=True,
            split="validation",
            max_k=5,
        )
        fake_backend = FakeLLMBackend(scenario="normal")
        harness = EvalHarness(cfg, backend=fake_backend)
        summary = harness.run()

        # Fixture validation partition has 7 validation rows
        assert summary["total_evaluated"] == 7
        assert "success_within_1_attempt_pct" in summary
        assert "success_within_3_attempts_pct" in summary
        assert "success_within_5_attempts_pct" in summary
        assert "outcomes" in summary

    def test_universal_denominator_preserves_total_count(self, fixture_dataset_path, temp_eval_db):
        """Universal denominator rule: all evaluated rows stay in denominator N."""
        cfg = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            backend_name="fake",
            allow_fake=True,
            split="validation",
            max_k=5,
        )
        fake_backend = FakeLLMBackend(scenario="always_wrong")
        harness = EvalHarness(cfg, backend=fake_backend)
        summary = harness.run()

        total = summary["total_evaluated"]
        sum_outcomes = sum(summary["outcomes"].values())
        assert total == sum_outcomes
        assert total == 7

    def test_resume_skips_already_completed_rows(self, fixture_dataset_path, temp_eval_db):
        """With resume=True, completed row IDs in SQLite DB are skipped."""
        cfg = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            backend_name="fake",
            allow_fake=True,
            split="validation",
            max_k=5,
            limit=2,
        )
        fake_backend = FakeLLMBackend(scenario="normal")
        harness1 = EvalHarness(cfg, backend=fake_backend)
        harness1.run()

        completed = harness1.get_completed_row_ids()
        assert len(completed) == 2

        # Second harness with resume=True and limit=4
        cfg2 = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            backend_name="fake",
            allow_fake=True,
            split="validation",
            max_k=5,
            limit=4,
            resume=True,
        )
        harness2 = EvalHarness(cfg2, backend=fake_backend)
        summary2 = harness2.run()

        # Should have evaluated the remaining rows up to limit=4
        completed_after = harness2.get_completed_row_ids()
        assert len(completed_after) == 4

    def test_z3_only_baseline_mode(self, fixture_dataset_path, temp_eval_db):
        """--z3-only executes native SMT simplifier baseline without LLM."""
        cfg = EvalConfig(
            dataset_path=fixture_dataset_path,
            db_path=temp_eval_db,
            split="validation",
            z3_only=True,
        )
        harness = EvalHarness(cfg)
        summary = harness.run()

        assert summary["total_evaluated"] == 7
        assert "verified" in summary["outcomes"]


class TestOutcomeEnumAndSimplerRule:
    """Verifies strict definition of the 8-outcome enum and simpler-than-original rule."""

    def test_outcome_enum_exact_members_and_values(self):
        """All 8 outcome enum values strictly adhere to the specification."""
        expected = {
            "VERIFIED": "verified",
            "VERIFIED_NOT_SIMPLER": "verified-not-simpler",
            "FAILED_EXHAUSTED": "failed-exhausted",
            "UNKNOWN_TIMEOUT": "unknown-timeout",
            "INVALID": "invalid",
            "REJECTED_UNSAFE": "rejected-unsafe",
            "DEPTH_REJECTED": "depth-rejected",
            "UNCONVERTIBLE": "unconvertible",
        }
        for member_name, expected_val in expected.items():
            assert getattr(RunOutcome, member_name).value == expected_val
            assert getattr(EvalOutcome, member_name).value == expected_val

    def test_determine_verified_outcome_standard_rows(self):
        """Standard rows require candidate node count to be strictly less than original."""
        # 9 nodes original vs 3 nodes candidate -> verified
        assert determine_verified_outcome(obf_nodes=9, cand_nodes=3, is_idempotent=False) == RunOutcome.VERIFIED
        # 9 nodes original vs 9 nodes candidate -> verified-not-simpler
        assert determine_verified_outcome(obf_nodes=9, cand_nodes=9, is_idempotent=False) == RunOutcome.VERIFIED_NOT_SIMPLER
        # 9 nodes original vs 11 nodes candidate -> verified-not-simpler
        assert determine_verified_outcome(obf_nodes=9, cand_nodes=11, is_idempotent=False) == RunOutcome.VERIFIED_NOT_SIMPLER

    def test_determine_verified_outcome_idempotent_rows(self):
        """Idempotent rows permit candidate node count to be less than or equal to original."""
        # 3 nodes original vs 3 nodes candidate (idempotent) -> verified
        assert determine_verified_outcome(obf_nodes=3, cand_nodes=3, is_idempotent=True) == RunOutcome.VERIFIED
        # 3 nodes original vs 1 node candidate (idempotent) -> verified
        assert determine_verified_outcome(obf_nodes=3, cand_nodes=1, is_idempotent=True) == RunOutcome.VERIFIED
        # 3 nodes original vs 5 nodes candidate (idempotent) -> verified-not-simpler
        assert determine_verified_outcome(obf_nodes=3, cand_nodes=5, is_idempotent=True) == RunOutcome.VERIFIED_NOT_SIMPLER

