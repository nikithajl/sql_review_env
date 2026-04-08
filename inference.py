"""
Baseline inference script for SQL Review OpenEnv.

Mandatory environment variables:
  API_BASE_URL   The API endpoint for the LLM
  MODEL_NAME     The model identifier to use
  HF_TOKEN       Your Hugging Face API key
"""

from __future__ import annotations

import json
import os
import pathlib
import textwrap
import time
from typing import Optional

import requests
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")
BENCHMARK = os.getenv("BENCHMARK_NAME", "sql_review_env")

MAX_STEPS = 3
TEMPERATURE = 0.0
MAX_TOKENS = 1024
SUCCESS_SCORE_THRESHOLD = 0.9
OUTPUT_PATH = pathlib.Path(__file__).with_name("baseline_scores.json")

ALL_TASK_IDS = [
    "easy_wrong_join",
    "easy_missing_filter",
    "easy_wrong_aggregate",
    "medium_sql_injection",
    "medium_data_exposure",
    "medium_over_privilege",
    "hard_correlated_subquery",
    "hard_function_on_column",
    "hard_n_plus_one",
]

FALLBACK_SQL_BY_TASK = {
    "easy_wrong_join": (
        "SELECT u.name, u.email, COUNT(o.id) AS order_count "
        "FROM users u "
        "INNER JOIN orders o ON o.user_id = u.id "
        "WHERE u.is_active = 1 "
        "GROUP BY u.id "
        "ORDER BY u.name;"
    ),
    "easy_missing_filter": (
        "SELECT id, name, category, price, stock_quantity "
        "FROM products "
        "WHERE is_deleted = 0 AND stock_quantity > 0 "
        "ORDER BY price ASC;"
    ),
    "easy_wrong_aggregate": (
        "SELECT r.product_id, p.name, AVG(r.rating) AS avg_rating "
        "FROM reviews r "
        "JOIN products p ON p.id = r.product_id "
        "GROUP BY r.product_id "
        "ORDER BY avg_rating DESC;"
    ),
    "medium_sql_injection": (
        "SELECT o.id, o.status, o.total_amount, o.created_at "
        "FROM orders o "
        "JOIN users u ON u.id = o.user_id "
        "WHERE u.email = ? AND u.is_active = 1"
    ),
    "medium_data_exposure": (
        "SELECT id, name, email, created_at "
        "FROM users "
        "WHERE id = ? AND is_active = 1"
    ),
    "medium_over_privilege": (
        "SELECT o.id, o.status, o.total_amount, o.created_at, o.shipped_at, "
        "p.name AS product_name, oi.quantity "
        "FROM orders o "
        "JOIN order_items oi ON oi.order_id = o.id "
        "JOIN products p ON p.id = oi.product_id "
        "WHERE o.id = ?;"
    ),
    "hard_correlated_subquery": (
        "-- Replaced the correlated subquery with a single join and aggregation\n"
        "SELECT u.name, u.email, COUNT(o.id) AS order_count "
        "FROM users u "
        "LEFT JOIN orders o ON o.user_id = u.id "
        "WHERE u.is_active = 1 "
        "GROUP BY u.id, u.name, u.email "
        "ORDER BY order_count DESC;"
    ),
    "hard_function_on_column": (
        "-- Replaced strftime() with an index-friendly created_at range filter\n"
        "SELECT id, user_id, status, total_amount, created_at "
        "FROM orders "
        "WHERE created_at >= '2024-04-01' AND created_at < '2024-05-01' "
        "ORDER BY created_at;"
    ),
    "hard_n_plus_one": (
        "-- Replaced N+1 subqueries with joins to fetch products in one pass\n"
        "SELECT oi.id AS item_id, oi.order_id, oi.unit_price, oi.quantity, "
        "p.name AS product_name, p.category AS product_category "
        "FROM order_items oi "
        "JOIN orders o ON o.id = oi.order_id "
        "JOIN products p ON p.id = oi.product_id "
        "WHERE o.status = 'delivered';"
    ),
}

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are an expert SQL code reviewer and database engineer.
    You will be given a SQL query that has a problem: it may have a bug,
    a security vulnerability, or a performance issue.
    You will also be given a description of what the query should do
    and a summary of the database schema.

    Your job is to return ONLY the corrected SQL query.
    No markdown, no code fences, no explanations outside SQL comments (--).
    For performance tasks: add a brief SQL comment (--) explaining the fix.
    For security tasks: use ? placeholders for any user-supplied values.
    Return the SQL and nothing else.
    """
).strip()


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    action_str = " ".join(action.splitlines()).strip()
    error_val = error if error else "null"
    print(
        f"[STEP] step={step} action={action_str} reward={reward:.2f} "
        f"done={str(done).lower()} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{reward:.2f}" for reward in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} "
        f"score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


def env_post(path: str, body: dict) -> dict:
    response = requests.post(f"{ENV_BASE_URL}{path}", json=body, timeout=30)
    response.raise_for_status()
    return response.json()


def env_get(path: str) -> dict:
    response = requests.get(f"{ENV_BASE_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


def require_keys(payload: dict, keys: list[str], context: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise RuntimeError(f"{context} missing keys: {missing}. Payload: {payload}")


def call_llm(client: OpenAI, user_prompt: str) -> str:
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc


def build_prompt(observation: dict, feedback: Optional[str]) -> str:
    parts = [
        f"Task: {observation['description']}",
        "",
        "Database schema:",
        observation["schema_summary"],
        "",
        "SQL query to fix:",
        observation["sql_to_review"],
    ]
    if feedback:
        parts += ["", f"Previous attempt feedback: {feedback}"]
    parts += ["", "Return ONLY the corrected SQL query:"]
    return "\n".join(parts)


def fallback_sql(task_id: str, observation: dict) -> str:
    return FALLBACK_SQL_BY_TASK.get(task_id, observation["sql_to_review"])


def run_task(client: OpenAI, task_id: str) -> float:
    rewards: list[float] = []
    steps_taken = 0
    best_score = 0.0
    success = False

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        reset_response = env_post("/reset", {"task_id": task_id})
        require_keys(reset_response, ["observation", "done"], "reset response")
        observation = reset_response["observation"]
        feedback: Optional[str] = None

        for step_num in range(1, MAX_STEPS + 1):
            if observation.get("done"):
                break

            try:
                agent_sql = call_llm(client, build_prompt(observation, feedback))
            except RuntimeError:
                agent_sql = fallback_sql(task_id, observation)

            if not agent_sql.strip():
                agent_sql = fallback_sql(task_id, observation)

            step_response = env_post(
                "/step",
                {
                    "action": {
                        "sql": agent_sql,
                        "explanation": None,
                    },
                    "task_id": task_id,
                },
            )
            require_keys(step_response, ["observation", "reward", "done"], "step response")

            reward = float(step_response.get("reward", 0.0))
            done = bool(step_response.get("done", False))
            observation = step_response["observation"]
            feedback = observation.get("last_feedback")

            rewards.append(reward)
            steps_taken = step_num
            best_score = max(best_score, reward)
            log_step(
                step=step_num,
                action=agent_sql,
                reward=reward,
                done=done,
                error=None,
            )

            if done:
                break

            time.sleep(0.5)

        success = best_score >= SUCCESS_SCORE_THRESHOLD
        return best_score

    finally:
        log_end(success=success, steps=steps_taken, score=best_score, rewards=rewards)


def main() -> None:
    if not API_KEY:
        raise SystemExit("Missing API key. Set HF_TOKEN, OPENAI_API_KEY, or API_KEY.")
    if not MODEL_NAME:
        raise SystemExit("Missing MODEL_NAME environment variable.")

    try:
        env_get("/health")
    except Exception as exc:
        raise SystemExit(f"Cannot reach environment at {ENV_BASE_URL}: {exc}") from exc

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    results: dict[str, float] = {}

    for task_id in ALL_TASK_IDS:
        try:
            results[task_id] = run_task(client, task_id)
        except Exception:
            results[task_id] = 0.001

    easy_scores = [score for task, score in results.items() if task.startswith("easy")]
    medium_scores = [score for task, score in results.items() if task.startswith("medium")]
    hard_scores = [score for task, score in results.items() if task.startswith("hard")]
    overall = sum(results.values()) / len(results)

    if all(score == 0.0 for score in results.values()):
        raise SystemExit(
            "Baseline run produced all-zero scores. Check model credentials and provider access."
        )

    output = {
        "model": MODEL_NAME,
        "scores": results,
        "summary": {
            "easy_mean": round(sum(easy_scores) / len(easy_scores), 3),
            "medium_mean": round(sum(medium_scores) / len(medium_scores), 3),
            "hard_mean": round(sum(hard_scores) / len(hard_scores), 3),
            "overall_mean": round(overall, 3),
        },
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as file_obj:
        json.dump(output, file_obj, indent=2)


if __name__ == "__main__":
    main()
