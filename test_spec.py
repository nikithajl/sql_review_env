import re
import unittest
from pathlib import Path

from sql_review_env.server.tasks import TASK_INDEX


ROOT = Path(__file__).resolve().parents[1]


class SpecConsistencyTests(unittest.TestCase):
    def test_openenv_yaml_task_ids_match_runtime_tasks(self) -> None:
        content = (ROOT / "openenv.yaml").read_text(encoding="utf-8")
        declared_task_ids = re.findall(r"^\s*-\s+id:\s+([A-Za-z0-9_]+)\s*$", content, re.MULTILINE)

        self.assertEqual(declared_task_ids, list(TASK_INDEX.keys()))

    def test_all_tasks_have_valid_metadata(self) -> None:
        valid_difficulties = {"easy", "medium", "hard"}
        valid_graders = {"result_set", "security", "performance"}

        for task in TASK_INDEX.values():
            self.assertIn(task["difficulty"], valid_difficulties)
            self.assertIn(task["grader_type"], valid_graders)
            self.assertTrue(task["description"].strip())
            self.assertTrue(task["buggy_sql"].strip())
            self.assertTrue(task["reference_sql"].strip())


if __name__ == "__main__":
    unittest.main()
