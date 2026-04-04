---
title: SQL Review OpenEnv
colorFrom: blue
colorTo: gray
sdk: docker
pinned: false
app_port: 7860
tags:
  - openenv
  - sql
  - evaluation
---

# SQL Review OpenEnv

SQL Review OpenEnv is a real-world OpenEnv environment for training and evaluating agents on SQL review tasks. The agent acts like a database engineer or code reviewer: it receives a buggy, insecure, or inefficient SQL query and must return a corrected version.

This environment is designed to simulate work humans actually do in production systems:
- fixing correctness bugs in SQL queries
- identifying and removing insecure query patterns
- optimizing slow queries without changing expected results

The environment is built around a small e-commerce schema and exposes a standard OpenEnv API through `reset()`, `step()`, and `state()`.

## Why this environment matters

SQL review is a practical and high-value task for real software teams. Query mistakes can cause:
- incorrect business metrics
- data leaks or SQL injection vulnerabilities
- poor database performance and expensive queries

This environment provides a reproducible way to evaluate whether an agent can reason about SQL correctness, security, and efficiency across multiple difficulty levels.

## Environment Overview

The environment serves SQL review tasks across three difficulty bands:
- `easy`: correctness fixes
- `medium`: security remediation
- `hard`: performance optimization

Each episode gives the agent a task description, a buggy SQL query, schema context, and feedback from the previous attempt. The agent has up to 3 steps to improve its answer.

## Action Space

The agent submits a `SqlReviewAction`:

```python
class SqlReviewAction(Action):
    sql: str
    explanation: Optional[str]
```

Fields:
- `sql`: the corrected, secured, or optimized SQL query
- `explanation`: optional natural-language explanation of the fix

## Observation Space

The environment returns a `SqlReviewObservation`:

```python
class SqlReviewObservation(Observation):
    task_id: str
    difficulty: str
    description: str
    sql_to_review: str
    schema_summary: str
    step_number: int
    last_feedback: Optional[str]
    reward_info: Optional[SqlReviewReward]
    done: bool
    reward: float
```

Fields:
- `task_id`: unique task identifier
- `difficulty`: `easy`, `medium`, or `hard`
- `description`: natural-language objective for the agent
- `sql_to_review`: SQL query that needs review or repair
- `schema_summary`: summary of the e-commerce schema
- `step_number`: current step within the episode
- `last_feedback`: grader feedback from the previous attempt
- `reward_info`: structured reward details including score, feedback, and grader breakdown
- `done`: whether the episode is finished
- `reward`: scalar score for the latest attempt

The environment returns both:

- `reward`: a scalar numeric reward for OpenEnv-compatible evaluation
- `reward_info`: structured reward details containing score, feedback, and grader breakdown

## State

The environment exposes the standard OpenEnv state object through `/state`, including:
- `episode_id`
- `step_count`

Task-specific context such as the selected task, difficulty, and latest feedback is returned in observations from `/reset` and `/step`.


## Task Set

The environment currently includes 9 tasks.

### Easy: correctness fixes

These tasks require the agent to fix buggy SQL while preserving the intended result set.

Examples:
- `easy_wrong_join`: fixes a Cartesian product caused by an incorrect join between `users` and `orders`.
- `easy_missing_filter`: adds a missing stock filter so out-of-stock products are excluded.
- `easy_wrong_aggregate`: corrects an invalid aggregation and wrong join relationship when computing average ratings.

### Medium: security remediation

These tasks require the agent to remove insecure query patterns and replace them with safer SQL.

Examples:
- `medium_sql_injection`: rewrites interpolated SQL into a parameterized query using a placeholder.
- `medium_data_exposure`: removes unsafe column exposure and restricts results to active users.
- `medium_over_privilege`: removes unnecessary joins that leak user information into reports.

### Hard: performance optimization

These tasks require the agent to rewrite inefficient SQL into equivalent but more efficient forms.

Examples:
- `hard_correlated_subquery`: replaces a correlated subquery with a join-based aggregation.
- `hard_function_on_column`: rewrites a function-based date filter into an index-friendly range predicate.
- `hard_n_plus_one`: removes repeated subqueries by rewriting the query to proper joins.

## Reward and Grading

All tasks are graded deterministically and return scores in the range `0.0` to `1.0`.

### Easy tasks

Easy tasks use result-set grading:
- `1.0`: exact match with the reference result set
- `0.6`: partial match with strong overlap
- `0.3`: query runs but is incorrect
- `0.0`: empty or invalid submission

### Medium tasks

Medium tasks use a security grader combining:
- vulnerability removal
- presence of required safe patterns
- SQL syntax validity

This produces partial credit and rewards safer rewrites even when the answer is not perfect.

### Hard tasks

Hard tasks use a performance grader combining:
- correctness against the reference result set
- query-plan improvement using `EXPLAIN QUERY PLAN`
- explanation quality via SQL comments

This encourages agents to produce both correct and meaningfully optimized SQL.

## Why This Is Hard For Agents

This environment is challenging because agents must:
- preserve SQL correctness while changing query structure
- detect subtle security issues such as unsafe interpolation and overexposed columns
- optimize slow queries without changing the intended result set
- interpret grader feedback and improve over multiple steps
- handle different failure modes across correctness, security, and performance tasks

## Episode Flow

1. Call `reset()` to receive a task.
2. Inspect the observation.
3. Submit a `SqlReviewAction` through `step()`.
4. Receive updated observation, reward, and feedback.
5. Continue until the task is solved or the maximum number of steps is reached.

Episodes terminate when:
- the score is high enough for success
- the maximum step limit is reached

## API Usage Example

Reset to a specific task:

```json
{
  "task_id": "easy_wrong_join"
}
```

Step on that task:

```json
{
  "action": {
    "sql": "SELECT u.name, u.email, COUNT(o.id) AS order_count FROM users u INNER JOIN orders o ON o.user_id = u.id WHERE u.is_active = 1 GROUP BY u.id ORDER BY u.name;",
    "explanation": "Fixed the join condition."
  },
  "task_id": "easy_wrong_join"
}
```

Security task example:
```json
{
  "action": {
    "sql": "SELECT o.id, o.status, o.total_amount, o.created_at FROM orders o JOIN users u ON u.id = o.user_id WHERE u.email = ? AND u.is_active = 1",
    "explanation": "Replaced interpolation with a placeholder and filtered active users."
  },
  "task_id": "medium_sql_injection"
}
```

## Project Structure

```text
sql_review_env/
├── __init__.py
├── client.py
├── inference.py
├── models.py
├── openenv.yaml
├── pyproject.toml
├── README.md
└── server/
    ├── __init__.py
    ├── app.py
    ├── Dockerfile
    ├── graders.py
    ├── meta_environment.py
    ├── schema.sql
    └── tasks.py
```

## Running Locally

### Start the API server

From the project directory:

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Example client usage

```python
from sql_review_env import SqlReviewEnv, SqlReviewAction

with SqlReviewEnv(base_url="http://localhost:7860").sync() as env:
    result = env.reset()
    print(result.observation.task_id)
    print(result.observation.description)
    print(result.observation.sql_to_review)

    result = env.step(
        SqlReviewAction(
            sql="SELECT ...",
            explanation="Fixed join condition and filtering",
        ),
        task_id="easy_wrong_join",
    )
    print(result.observation.last_feedback)
    print(result.reward)
```

## Docker

### Build the container

```bash
docker build -t sql_review_env-env:latest -f server/Dockerfile .
```

### Run the container

```bash
docker run --rm -p 7860:7860 sql_review_env-env:latest
```

After startup, the environment should be available on:
- `/`
- `/health`
- `/docs`
- `/openapi.json`
- `/ws`

## Hugging Face Spaces

This environment is deployed as a Docker-based Hugging Face Space tagged with `openenv`.

The Space runs the FastAPI server and exposes the OpenEnv endpoints over HTTP and WebSocket.

## Baseline Inference Script

The submission includes a baseline agent runner in `inference.py`.

Required environment variables:
- `API_BASE_URL`: LLM API endpoint
- `MODEL_NAME`: model identifier
- `HF_TOKEN`: API token for model access

Recommended compatibility:
- support `OPENAI_API_KEY` as an alternative credential if needed

Run the baseline:

```bash
python inference.py
```

Expected behavior:
- connects to the deployed environment
- runs the model over all tasks
- records per-task scores
- writes a reproducible summary to `baseline_scores.json`

## Baseline Results

Baseline run details:
- Model: `meta-llama/Llama-3.3-70B-Instruct`
- API base URL: `https://router.huggingface.co/v1`
- Temperature: `0.0`

Per-task results:
- `easy_wrong_join`: 1.000
- `easy_missing_filter`: 1.000
- `easy_wrong_aggregate`: 1.000
- `medium_sql_injection`: 1.000
- `medium_data_exposure`: 1.000
- `medium_over_privilege`: 1.000
- `hard_correlated_subquery`: 0.533
- `hard_function_on_column`: 0.600
- `hard_n_plus_one`: 0.900

Summary:
Easy mean: 1.000
Medium mean: 1.000
Hard mean: 0.678
Overall mean: 0.893
These results were generated by running python inference.py against the deployed Hugging Face Space.

## OpenEnv Compliance

This environment includes:
- typed action and observation models
- `reset()`, `step()`, and `state()` semantics
- `openenv.yaml`
- deterministic task graders
- Dockerized deployment for Hugging Face Spaces

Before submission, validate the environment with:

```bash
openenv validate
```

## Validation

This environment has been validated with:

- successful Hugging Face Space deployment
- working /health, /docs, /openapi.json, /reset, and /step endpoints
- successful openenv validate
- successful baseline execution through python inference.py

## Notes for Evaluation

This environment is intended to evaluate whether agents can:
- understand SQL semantics
- preserve correctness while fixing bugs
- identify unsafe query patterns
- optimize query structure without changing behavior
- improve incrementally based on grader feedback
