import unittest

from sql_review_env.server.graders import grade_performance, grade_security
from sql_review_env.server.tasks import TASK_INDEX


class GraderTests(unittest.TestCase):
    def test_security_grader_is_deterministic(self) -> None:
        task = TASK_INDEX["medium_sql_injection"]
        sql = (
            "SELECT o.id, o.status, o.total_amount, o.created_at "
            "FROM orders o "
            "JOIN users u ON u.id = o.user_id "
            "WHERE u.email = ? AND u.is_active = 1"
        )

        first = grade_security(sql, task)
        second = grade_security(sql, task)

        self.assertEqual(first, second)

    def test_hard_task_requires_comment_for_success(self) -> None:
        task = TASK_INDEX["hard_n_plus_one"]

        score, breakdown = grade_performance(task["reference_sql"], task)

        self.assertLess(score, 0.9)
        self.assertFalse(breakdown["comment_requirement_met"])
        self.assertTrue(breakdown["comment_cap_applied"])

    def test_hard_task_with_comment_can_succeed(self) -> None:
        task = TASK_INDEX["hard_n_plus_one"]
        sql = (
            "-- Fixed the N+1 pattern by joining orders and products once\n"
            "SELECT oi.id AS item_id, oi.order_id, oi.unit_price, oi.quantity, "
            "p.name AS product_name, p.category AS product_category "
            "FROM order_items oi "
            "JOIN orders o ON o.id = oi.order_id "
            "JOIN products p ON p.id = oi.product_id "
            "WHERE o.status = 'delivered';"
        )

        score, breakdown = grade_performance(sql, task)

        self.assertGreaterEqual(score, 0.9)
        self.assertTrue(breakdown["comment_requirement_met"])
        self.assertGreater(breakdown["explanation_score"], 0.0)

    def test_security_grader_uses_semantic_execution(self) -> None:
        task = TASK_INDEX["medium_over_privilege"]
        sql = (
            "SELECT o.id, o.status, o.total_amount, o.created_at, o.shipped_at, "
            "p.name AS product_name, oi.quantity "
            "FROM orders o "
            "JOIN order_items oi ON oi.order_id = o.id "
            "JOIN products p ON p.id = o.id "
            "WHERE o.id = ?;"
        )

        score, breakdown = grade_security(sql, task)

        self.assertLess(score, 0.9)
        self.assertLess(breakdown["execution_score"], 1.0)
        self.assertIn("execution_match", breakdown)


if __name__ == "__main__":
    unittest.main()
