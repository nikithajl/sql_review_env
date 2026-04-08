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

            agent_sql = call_llm(client, build_prompt(observation, feedback))
            if not agent_sql.strip():
                raise RuntimeError(
                    f"LLM returned an empty response for task '{task_id}' at step {step_num}."
                )

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
        except Exception as exc:
            raise SystemExit(f"Baseline failed on task '{task_id}': {exc}") from exc

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
