import unittest

from sql_review_env import SqlReviewEnv


class ClientContractTests(unittest.TestCase):
    def test_parse_result_preserves_observation_fields(self) -> None:
        payload = {
            "observation": {
                "task_id": "medium_sql_injection",
                "difficulty": "medium",
                "task_type": "security",
                "description": "Fix the SQL injection bug.",
                "sql_to_review": "SELECT * FROM orders",
                "schema_summary": "schema",
                "step_number": 1,
                "steps_remaining": 2,
                "success_threshold": 0.9,
                "last_feedback": "good",
                "reward_info": {
                    "score": 1.0,
                    "feedback": "good",
                    "breakdown": {"semantic_score": 1.0},
                },
                "metadata": {"task_category": "security"},
            },
            "reward": 1.0,
            "done": False,
        }

        result = SqlReviewEnv(base_url="http://localhost:7860")._parse_result(payload)
        observation = result.observation

        self.assertEqual(observation.task_type, "security")
        self.assertEqual(observation.steps_remaining, 2)
        self.assertEqual(observation.success_threshold, 0.9)
        self.assertIsNotNone(observation.reward_info)
        self.assertEqual(observation.reward_info.score, 1.0)


if __name__ == "__main__":
    unittest.main()
