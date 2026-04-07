import unittest

from sql_review_env import SqlReviewAction
from sql_review_env.server.meta_environment import SqlReviewEnvironment
from sql_review_env.server.tasks import TASK_INDEX


class EnvironmentTests(unittest.TestCase):
    def test_reset_initializes_clean_episode_state(self) -> None:
        env = SqlReviewEnvironment()

        reset_obs = env.reset("easy_wrong_join")

        self.assertEqual(reset_obs.task_id, "easy_wrong_join")
        self.assertEqual(reset_obs.step_number, 0)
        self.assertEqual(reset_obs.steps_remaining, 3)
        self.assertIsNone(reset_obs.last_feedback)
        self.assertEqual(env.state.step_count, 0)
        self.assertEqual(env.state.current_task_id, "easy_wrong_join")

    def test_reset_clears_feedback_after_prior_step(self) -> None:
        env = SqlReviewEnvironment()

        env.reset("easy_wrong_join")
        env.step(SqlReviewAction(sql=TASK_INDEX["easy_wrong_join"]["reference_sql"]))
        reset_obs = env.reset("medium_sql_injection")

        self.assertEqual(reset_obs.task_id, "medium_sql_injection")
        self.assertEqual(reset_obs.step_number, 0)
        self.assertIsNone(reset_obs.last_feedback)
        self.assertEqual(env.state.step_count, 0)
        self.assertEqual(env.state.current_task_id, "medium_sql_injection")
        self.assertIsNone(env.state.last_feedback)

    def test_successful_step_returns_reward_info(self) -> None:
        env = SqlReviewEnvironment()
        env.reset("easy_missing_filter")

        observation = env.step(
            SqlReviewAction(sql=TASK_INDEX["easy_missing_filter"]["reference_sql"])
        )

        self.assertTrue(observation.done)
        self.assertGreater(observation.reward, 0.0)
        self.assertLess(observation.reward, 1.0)
        self.assertIsNotNone(observation.reward_info)
        self.assertGreater(observation.reward_info.score, 0.0)
        self.assertLess(observation.reward_info.score, 1.0)
        self.assertEqual(observation.steps_remaining, 2)


if __name__ == "__main__":
    unittest.main()
