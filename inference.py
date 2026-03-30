"""
inference.py  -  Baseline inference script for SQL Review OpenEnv
=================================================================
Mandatory environment variables:
  API_BASE_URL   The API endpoint for the LLM
  MODEL_NAME     The model identifier to use
  HF_TOKEN       Your Hugging Face API key
"""

import os
import json
import time
import textwrap
from typing import Optional

import requests
from openai import OpenAI

# ── Mandatory env vars ────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY", "")
MODEL_NAME   = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:7860")

MAX_STEPS   = 3
TEMPERATURE = 0.1
MAX_TOKENS  = 1024

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

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL code reviewer and database engineer.
    You will be given a SQL query that has a problem: it may have a bug,
    a security vulnerability, or a performance issue.
    You will also be given a description of what the query should do
    and a summary of the database schema.

    Your job is to return ONLY the corrected SQL query.
    No markdown, no code fences, no explanations outside SQL comments (--)
    For performance tasks: add a brief SQL comment (--) explaining the fix.
    For security tasks: use ? placeholders for any user-supplied values.
    Return the SQL and nothing else.
""").strip()


# ── HTTP helpers ──────────────────────────────────────────────────

def env_post(path: str, body: dict) -> dict:
    resp = requests.post(f"{ENV_BASE_URL}{path}", json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def env_get(path: str) -> dict:
    resp = requests.get(f"{ENV_BASE_URL}{path}", timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── LLM call ─────────────────────────────────────────────────────

def call_llm(client: OpenAI, user_prompt: str) -> str:
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"    [LLM ERROR] {exc}")
        return ""


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


# ── Per-task episode runner ───────────────────────────────────────

def run_task(client: OpenAI, task_id: str) -> float:
    print(f"\n  Task: {task_id}")

    reset_resp  = env_post("/reset", {"task_id": task_id})
    observation = reset_resp["observation"]
    feedback: Optional[str] = None
    best_score  = 0.0

    for step_num in range(1, MAX_STEPS + 1):
        if observation.get("done"):
            break

        agent_sql = call_llm(client, build_prompt(observation, feedback))
        if not agent_sql:
            print(f"    Step {step_num}: empty LLM response, skipping")
            break

        step_resp   = env_post("/step", {"action": {"sql": agent_sql}})
        reward_val  = step_resp["reward"]["value"]
        feedback    = step_resp["reward"]["feedback"]
        done        = step_resp["done"]
        observation = step_resp["observation"]

        best_score = max(best_score, reward_val)
        print(f"    Step {step_num}: score={reward_val:.3f}  done={done}")
        print(f"             {str(feedback)[:120]}")

        if done:
            break

        time.sleep(0.5)

    return best_score


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("SQL Review OpenEnv  -  Baseline Inference")
    print(f"Model:   {MODEL_NAME}")
    print(f"Env URL: {ENV_BASE_URL}")
    print("=" * 60)

    try:
        health = env_get("/health")
        print(f"Environment health: {health}\n")
    except Exception as e:
        print(f"ERROR: Cannot reach environment at {ENV_BASE_URL}: {e}")
        raise SystemExit(1)

    client  = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    results: dict[str, float] = {}

    for task_id in ALL_TASK_IDS:
        results[task_id] = run_task(client, task_id)

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    easy_scores   = [v for k, v in results.items() if k.startswith("easy")]
    medium_scores = [v for k, v in results.items() if k.startswith("medium")]
    hard_scores   = [v for k, v in results.items() if k.startswith("hard")]

    for task_id, score in results.items():
        print(f"  {task_id:<35} {score:.3f}")

    print("-" * 60)
    print(f"  Easy   mean:  {sum(easy_scores)   / len(easy_scores):.3f}")
    print(f"  Medium mean:  {sum(medium_scores) / len(medium_scores):.3f}")
    print(f"  Hard   mean:  {sum(hard_scores)   / len(hard_scores):.3f}")
    print("-" * 60)
    overall = sum(results.values()) / len(results)
    print(f"  OVERALL mean: {overall:.3f}")
    print("=" * 60)

    output = {
        "model": MODEL_NAME,
        "scores": results,
        "summary": {
            "easy_mean":    round(sum(easy_scores)   / len(easy_scores),   3),
            "medium_mean":  round(sum(medium_scores) / len(medium_scores), 3),
            "hard_mean":    round(sum(hard_scores)   / len(hard_scores),   3),
            "overall_mean": round(overall, 3),
        },
    }
    with open("baseline_scores.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nScores saved to baseline_scores.json")


if __name__ == "__main__":
    main()