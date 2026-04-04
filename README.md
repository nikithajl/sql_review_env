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

SQL Review OpenEnv is a benchmark environment for training and evaluating agents on a real software engineering task: reviewing SQL queries for correctness, security, and performance.

The agent is given a flawed SQL query, task context, and schema information. Its job is to return a corrected query that preserves the intended behavior while fixing the underlying issue. Depending on the task, the issue may be:

- a logical correctness bug
- a security flaw such as unsafe interpolation or overexposure of data
- a performance issue such as correlated subqueries, N+1 access patterns, or non-index-friendly filters

This environment is designed for real-world agent evaluation, not toy interaction. SQL review is a recurring task in analytics engineering, backend development, database administration, and security review, and it is exactly the kind of work agents are increasingly expected to assist with.

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

Each episode gives the agent:
- a task identifier
- a difficulty label
- a natural-language problem statement
- the buggy SQL query
- a summary of the database schema
- feedback from the previous attempt

The observation explicitly tells the agent what type of task it is solving, how many attempts remain, and what score threshold counts as success.

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
    task_type: str
    description: str
    sql_to_review: str
    schema_summary: str
    step_number: int
    steps_remaining: int
    success_threshold: float
    last_feedback: Optional[str]
    reward_info: Optional[SqlReviewReward]
    done: bool
    reward: float
```

Fields:

- `task_id`: unique task identifier
- `difficulty`: `easy`, `medium`, or `hard`
- `task_type`: high-level task type such as `result_set`, `security`, or `performance`
- `description`: natural-language objective for the agent
- `sql_to_review`: the SQL query that needs review or repair
- `schema_summary`: summary of the e-commerce schema
- `step_number`: current step in the episode
- `steps_remaining`: number of attempts remaining in the episode
- `success_threshold`: reward threshold at which the task is considered solved
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

## Underlying Schema

The environment uses a small e-commerce schema with five tables:

- `users (id, email, name, role, created_at, is_active)`
- `products (id, name, category, price, stock_quantity, is_deleted)`
- `orders (id, user_id, status, total_amount, created_at, shipped_at)`
- `order_items (id, order_id, product_id, quantity, unit_price)`
- `reviews (id, user_id, product_id, rating, body, created_at)`

This is intentionally compact enough to be learnable, while still realistic enough to support meaningful SQL review tasks.

## Task Set

The environment currently includes 9 tasks.

### Easy: correctness fixes

These tasks require the agent to fix buggy SQL while preserving the intended result set.

- `easy_wrong_join`: fixes a Cartesian product caused by an incorrect join between `users` and `orders`.
- `easy_missing_filter`: adds a missing stock filter so out-of-stock products are excluded.
- `easy_wrong_aggregate`: corrects an invalid aggregation and wrong join relationship when computing average ratings.

### Medium: security remediation

These tasks require the agent to remove insecure query patterns and replace them with safer SQL.

- `medium_sql_injection`: rewrites interpolated SQL into a parameterized query using a placeholder.
- `medium_data_exposure`: removes unsafe column exposure and restricts results to active users.
- `medium_over_privilege`: removes unnecessary joins that leak user information into reports.

### Hard: performance optimization

These tasks require the agent to rewrite inefficient SQL into equivalent but more efficient forms.

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

Medium tasks use a security grader that combines:

- Vulnerability-pattern removal
- Required safety constraints such as parameterization and active-user filtering
- Task-specific semantic checks on selected columns, table usage, and access restrictions
- SQL syntax validity

This provides partial credit for answers that improve safety even if they are not fully correct.

### Hard tasks

Hard tasks use a performance grader that combines:

- Correctness against the reference result set
- Task-specific anti-pattern removal
- Query-plan quality using `EXPLAIN QUERY PLAN`
- Explanation quality via SQL comments

This rewards agents that preserve semantics while also removing the actual performance anti-pattern, not just rewriting the query superficially.

## Why This Is Hard For Agents

This environment is difficult for agents because it tests multiple kinds of reasoning at once:

This environment is difficult for agents because it tests multiple kinds of reasoning at once:

- Semantic preservation: the rewritten SQL must still produce the intended result.
- Security awareness: the agent must distinguish safe parameterization from insecure interpolation.
- Performance reasoning: the agent must understand why a query is slow, not just that it is slow.
- Feedback utilization: the agent must use structured grader feedback to improve over multiple steps.
- Cross-domain competence: correctness, security, and performance tasks require different solution patterns.

The benchmark is designed to distinguish between queries that merely look plausible and queries that are actually correct, safe, and meaningfully improved. This makes it more realistic than single-mode SQL generation tasks.

## Common Failure Modes

This environment is designed to surface realistic agent mistakes, including:

- Generating syntactically valid SQL that changes the result set.
- Fixing one bug while preserving another.
- Removing obvious vulnerabilities but forgetting required access constraints.
- Producing a correct query that is still inefficient.
- Adding comments or explanations without actually improving the query plan.

These failure modes matter in real engineering settings, and the benchmark is designed to detect them.

## Episode Flow

1. Call `reset()` to receive a task.
2. Inspect the observation.
3. Submit a `SqlReviewAction` through `step()`.
4. Receive updated observation, reward, and feedback.
5. Continue until the task is solved or the maximum number of steps is reached.

This makes the environment intentionally multi-step: agents can use grader feedback to refine their solution before the episode ends.

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

Performance task example:

{
  "action": {
    "sql": "-- Replaced the correlated subquery with a single join and aggregation\nSELECT u.name, u.email, COUNT(o.id) AS order_count FROM users u LEFT JOIN orders o ON o.user_id = u.id WHERE u.is_active = 1 GROUP BY u.id, u.name, u.email ORDER BY order_count DESC;",
    "explanation": "Used a join-based aggregation to avoid repeated per-row subqueries."
  },
  "task_id": "hard_correlated_subquery"
}

## Project Structure

```text
sql_review_env/
├── __init__.py
├── baseline_scores.json
├── client.py
├── inference.py
├── models.py
├── openenv.yaml
├── pyproject.toml
├── README.md
├── uv.lock
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

## Smoke Test

A lightweight smoke test is included to verify the main interaction loop across easy, medium, and hard tasks.

Run:

```bash
python smoke_test.py
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

The main interaction endpoints, including `/reset`, `/step`, and `/state`, are documented and testable through `/docs`.

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

- Connects to the deployed environment.
- Runs the model over all tasks.
- Records per-task scores.
- Writes a reproducible summary to `baseline_scores.json`.

## Baseline Results

Baseline run details:

- Model: `meta-llama/Llama-3.3-70B-Instruct`
- API base URL: `https://router.huggingface.co/v1`
- Temperature: `0.0`

Per-task results:
- `easy_wrong_join`: `1.000`
- `easy_missing_filter`: `1.000`
- `easy_wrong_aggregate`: `1.000`
- `medium_sql_injection`: `1.000`
- `medium_data_exposure`: `1.000`
- `medium_over_privilege`: `1.000`
- `hard_correlated_subquery`: `0.533`
- `hard_function_on_column`: `0.600`
- `hard_n_plus_one`: `0.900`

Summary:

- Easy mean: `1.000`
- Medium mean: `1.000`
- Hard mean: `0.678`
- Overall mean: `0.893`

These results were generated by running `python inference.py` against the deployed Hugging Face Space.

## OpenEnv Compliance

This environment includes:

- Typed action and observation models.
- Structured reward details through reward_info.
- `reset()`, `step()`, and `state()` semantics.
- `openenv.yaml`
- Deterministic task graders.
- Dockerized deployment for Hugging Face Spaces.

The grading logic is deterministic and includes task-specific semantic checks for security and performance tasks, rather than relying only on surface-level pattern matching.


Validate the environment with:

```bash
openenv validate
```

## Validation

This environment has been validated with:

- Successful Hugging Face Space deployment.
- Working /health, /docs, /openapi.json, /reset, and /step endpoints.
- Successful openenv validate.
- Successful baseline execution through python inference.py.

## Notes for Evaluation

This environment is intended to evaluate whether agents can:

- Understand SQL semantics.
- Preserve correctness while fixing bugs.
- Identify unsafe query patterns.
- Optimize query structure without changing behavior.
- Improve incrementally based on grader feedback.
