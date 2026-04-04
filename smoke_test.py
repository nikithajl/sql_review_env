"""Basic smoke test for SQL Review OpenEnv."""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")

TASK_CASES: list[dict[str, Any]] = [
    {
        "action": {
            "sql": (
                "SELECT u.name, u.email, COUNT(o.id) AS order_count "
                "FROM users u "
                "INNER JOIN orders o ON o.user_id = u.id "
                "WHERE u.is_active = 1 "
                "GROUP BY u.id "
                "ORDER BY u.name;"
            ),
            "explanation": "Fixed the join condition.",
        },
        "task_id": "easy_wrong_join"
    },
    {
        "action": {
            "sql": (
                "SELECT o.id, o.status, o.total_amount, o.created_at "
                "FROM orders o "
                "JOIN users u ON u.id = o.user_id "
                "WHERE u.email = ? AND u.is_active = 1"
            ),
            "explanation": "Replaced interpolation with a placeholder.",
        },
        "task_id": "medium_sql_injection"
    },
    {
        "action": {
            "sql": (
                "-- Replaced repeated subqueries with joins\n"
                "SELECT oi.id AS item_id, oi.order_id, oi.unit_price, oi.quantity, "
                "p.name AS product_name, p.category AS product_category "
                "FROM order_items oi "
                "JOIN orders o ON o.id = oi.order_id "
                "JOIN products p ON p.id = oi.product_id "
                "WHERE o.status = 'delivered';"
            ),
            "explanation": "Removed N+1 subqueries with proper joins.",
        },
        "task_id": "hard_n_plus_one"
    },
]


def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{ENV_BASE_URL}{path}", json=body, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    print(f"Smoke testing environment: {ENV_BASE_URL}")

    for case in TASK_CASES:
        task_id = case["task_id"]
        print(f"\nTesting task: {task_id}")

        reset_payload = {"task_id": task_id}
        reset_resp = post("/reset", reset_payload)
        observation = reset_resp.get("observation", {})

        assert observation.get("task_id") == task_id, f"reset task_id mismatch for {task_id}"
        assert "difficulty" in observation, f"missing difficulty in reset for {task_id}"
        assert "task_type" in observation, f"missing task_type in reset for {task_id}"
        assert "steps_remaining" in observation, f"missing steps_remaining in reset for {task_id}"

        step_payload = {
            "action": case["action"],
            "task_id": task_id,
        }
        step_resp = post("/step", step_payload)
        step_obs = step_resp.get("observation", {})

        assert isinstance(step_resp.get("reward"), (int, float)), f"reward not numeric for {task_id}"
        assert "reward_info" in step_obs, f"missing reward_info in step observation for {task_id}"
        assert "last_feedback" in step_obs, f"missing last_feedback in step observation for {task_id}"
        assert "steps_remaining" in step_obs, f"missing steps_remaining in step observation for {task_id}"

        print(
            f"  reward={step_resp['reward']:.3f} "
            f"done={step_resp.get('done')} "
            f"steps_remaining={step_obs.get('steps_remaining')}"
        )

    print("\nSmoke test passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nSmoke test failed: {exc}")
        sys.exit(1)
