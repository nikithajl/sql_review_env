# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""SQL Review Environment Implementation."""

import random
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment

try:
    from ..models import (
        SqlReviewAction,
        SqlReviewObservation,
        SqlReviewReward,
        SqlReviewState,
    )
except ImportError:
    from models import (
        SqlReviewAction,
        SqlReviewObservation,
        SqlReviewReward,
        SqlReviewState,
    )

try:
    from .tasks import TASKS, TASK_INDEX
    from .graders import grade
except ImportError:
    from tasks import TASKS, TASK_INDEX
    from graders import grade


SCHEMA_SUMMARY = """E-commerce database with 5 tables:
  users       (id, email, name, role, created_at, is_active)
  products    (id, name, category, price, stock_quantity, is_deleted)
  orders      (id, user_id, status, total_amount, created_at, shipped_at)
  order_items (id, order_id, product_id, quantity, unit_price)
  reviews     (id, user_id, product_id, rating, body, created_at)"""

MAX_STEPS = 3


class SqlReviewEnvironment(Environment):
    """
    SQL Review environment: agent fixes, audits, and optimizes SQL queries.

    Easy   tasks: fix buggy SQL (graded by result-set comparison)
    Medium tasks: audit security vulnerabilities (graded by pattern analysis)
    Hard   tasks: optimize slow queries (graded by EXPLAIN plan + correctness)
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = SqlReviewState(episode_id=str(uuid4()), step_count=0)
        self._current_task: dict | None = None
        self._last_feedback: str | None = None

    def reset(self, task_id: str | None = None) -> SqlReviewObservation:
        """Start a new episode, optionally selecting a specific task."""
        if task_id is not None:
            task = TASK_INDEX.get(task_id)
            if task is None:
                available = ", ".join(sorted(TASK_INDEX))
                raise ValueError(
                    f"Unknown task_id '{task_id}'. Available tasks: {available}"
                )
            self._current_task = task
        else:
            self._current_task = random.choice(TASKS)

        self._state = SqlReviewState(
            episode_id=str(uuid4()),
            step_count=0,
            current_task_id=self._current_task["id"],
            current_difficulty=self._current_task["difficulty"],
            last_feedback=None,
        )
        self._last_feedback = None

        return SqlReviewObservation(
            task_id=self._current_task["id"],
            difficulty=self._current_task["difficulty"],
            task_type=self._current_task["grader_type"],
            description=self._current_task["description"],
            sql_to_review=self._current_task["buggy_sql"],
            schema_summary=SCHEMA_SUMMARY,
            step_number=0,
            steps_remaining=MAX_STEPS,
            success_threshold=0.9,
            last_feedback=None,
            done=False,
            reward=0.0,
            reward_info=None,
            metadata={
                "task_category": self._current_task["grader_type"],
                "max_steps": MAX_STEPS,
            },
        )

    def step(
        self,
        action: SqlReviewAction,
        task_id: str | None = None,
    ) -> SqlReviewObservation:
        """Grade the agent's SQL and return reward plus next observation."""
        self._state.step_count += 1

        if self._current_task is None:
            if task_id is None:
                raise ValueError("task_id is required when no active task is loaded")
            task = TASK_INDEX.get(task_id)
            if task is None:
                available = ", ".join(sorted(TASK_INDEX))
                raise ValueError(
                    f"Unknown task_id '{task_id}'. Available tasks: {available}"
                )
            self._current_task = task
            self._state.current_task_id = task["id"]
            self._state.current_difficulty = task["difficulty"]

        score, breakdown = grade(action.sql, self._current_task)

        if score >= 0.9:
            feedback = f"Excellent! Score: {score:.3f}. {breakdown}"
        elif score >= 0.6:
            feedback = f"Good attempt. Score: {score:.3f}. {breakdown}"
        elif score >= 0.3:
            feedback = f"Partial credit. Score: {score:.3f}. {breakdown}"
        else:
            feedback = f"Needs improvement. Score: {score:.3f}. {breakdown}"

        reward_details = SqlReviewReward(
            score=score,
            feedback=feedback,
            breakdown=breakdown,
        )

        self._last_feedback = reward_details.feedback

        done = reward_details.score >= 0.9 or self._state.step_count >= MAX_STEPS
        self._state.current_task_id = self._current_task["id"]
        self._state.current_difficulty = self._current_task["difficulty"]
        self._state.last_feedback = reward_details.feedback

        return SqlReviewObservation(
            task_id=self._current_task["id"],
            difficulty=self._current_task["difficulty"],
            task_type=self._current_task["grader_type"],
            description=self._current_task["description"],
            sql_to_review=self._current_task["buggy_sql"],
            schema_summary=SCHEMA_SUMMARY,
            step_number=self._state.step_count,
            steps_remaining=max(0, MAX_STEPS - self._state.step_count),
            success_threshold=0.9,
            last_feedback=reward_details.feedback,
            done=done,
            reward=reward_details.score,
            reward_info=reward_details,
            metadata={
                "task_category": self._current_task["grader_type"],
                "max_steps": MAX_STEPS,
                "reward": reward_details.model_dump(),
            },
        )

    @property
    def state(self) -> SqlReviewState:
        return self._state
