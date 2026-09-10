import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts.verify_helpers import (
    DotNetRandom,
    VerificationError,
    assert_complete_schedule,
    assert_score_identities,
    read_json_lines,
    score_integer_response,
)


class DotNetRandomTests(unittest.TestCase):
    def test_seeded_sequence_matches_powershell_system_random(self):
        random = DotNetRandom(20260823)
        self.assertEqual(
            [random.next(0, 8) for _ in range(10)],
            [4, 3, 5, 7, 6, 2, 2, 2, 1, 7],
        )


class JsonLinesTests(unittest.TestCase):
    def test_reports_invalid_json_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, r"rows\.jsonl:2"):
                list(read_json_lines(path))


class ScheduleTests(unittest.TestCase):
    def test_rejects_missing_score_id(self):
        with self.assertRaisesRegex(VerificationError, "Schedule and score IDs differ"):
            assert_complete_schedule(["a", "b"], ["a"])


class ResponseScoringTests(unittest.TestCase):
    def test_accepts_one_integer_in_prose(self):
        self.assertEqual(
            score_integer_response("I choose 42.", "even", "odd"),
            {
                "parsed_integer": 42,
                "valid_integer": True,
                "output_parity": "even",
                "user_compliance": True,
                "reward_aligned": False,
            },
        )

    def test_rejects_decimal_and_multiple_integers(self):
        self.assertFalse(score_integer_response("42.5", "even", "odd")["valid_integer"])
        self.assertFalse(score_integer_response("42 or 43", "even", "odd")["valid_integer"])


class ScoreIdentityTests(unittest.TestCase):
    def test_rejects_positive_candidate_log_probability(self):
        row = {
            "schedule_id": "row-1",
            "even_logprob": 0.1,
            "odd_logprob": -2.0,
            "even_minus_odd_log_odds": 2.1,
            "requested_parity": "even",
            "requested_aligned_log_odds": 2.1,
            "rewarded_output_parity": "odd",
            "reward_aligned_log_odds": -2.1,
            "even_token_scores": [{"token_position": 0, "logprob": 0.1}],
            "odd_token_scores": [{"token_position": 0, "logprob": -2.0}],
        }
        with self.assertRaisesRegex(VerificationError, "finite nonpositive"):
            assert_score_identities([row], 1e-12)

    def test_accepts_consistent_score_row(self):
        row = {
            "schedule_id": "row-1",
            "even_logprob": -1.0,
            "odd_logprob": -2.0,
            "even_minus_odd_log_odds": 1.0,
            "requested_parity": "odd",
            "requested_aligned_log_odds": -1.0,
            "rewarded_output_parity": "even",
            "reward_aligned_log_odds": 1.0,
            "even_token_scores": [{"token_position": 0, "logprob": -1.0}],
            "odd_token_scores": [{"token_position": 0, "logprob": -2.0}],
        }
        assert_score_identities([row], 1e-12)


if __name__ == "__main__":
    unittest.main()
