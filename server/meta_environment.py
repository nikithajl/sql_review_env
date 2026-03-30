# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""SQL Review Environment Implementation."""

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import SqlReviewAction, SqlReviewObservation
except ImportError:
    from models import SqlReviewAction, SqlReviewObservation

try:
    from .tasks import TASKS, TASK_INDEX
    from .graders import grade
except ImportError:
    from tasks import TASKS, TASK_INDEX
    from graders import grade

import random

SCHEMA_SUMMARY = """E-commerce database with 5 tables:
  users       (id, email, name, role, created_at, is_active)
  products    (id, name, category, price, stock_quantity, is_deleted)
  orders      (id, user_id, status, total_amount, created_at, shipped_at)
  order_items (id, order_id, product_id, quantity, unit_price)
  reviews     (id, user_id, product_id, rating, body, created_at)"""

MAX_STEPS = 3


class SqlReviewEnvironment(Environment):
    """
    SQL Review environment — agent fixes/audits/optimizes SQL queries.

    Easy   tasks: fix buggy SQL (graded by result-set comparison)
    Medium tasks: audit security vulnerabilities (graded by pattern analysis)
    Hard   tasks: optimize slow queries (graded by EXPLAIN plan + correctness)
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._current_task: dict | None = None
        self._last_feedback: str | None = None

    def reset(self) -> SqlReviewObservation:
        """Start a new episode with a random task."""
        self._current_task = random.choice(TASKS)
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._last_feedback = None

        return SqlReviewObservation(
            task_id=self._current_task["id"],
            difficulty=self._current_task["difficulty"],
            description=self._current_task["description"],
            sql_to_review=self._current_task["buggy_sql"],
            schema_summary=SCHEMA_SUMMARY,
            step_number=0,
            last_feedback=None,
            done=False,
            reward=0.0,
        )

    def step(self, action: SqlReviewAction) -> SqlReviewObservation:
        """Grade the agent's SQL and return reward + next observation."""
        self._state.step_count += 1

        score, breakdown = grade(action.sql, self._current_task)

        if score >= 0.9:
            feedback = f"Excellent! Score: {score:.3f}. {breakdown}"
        elif score >= 0.6:
            feedback = f"Good attempt. Score: {score:.3f}. {breakdown}"
        elif score >= 0.3:
            feedback = f"Partial credit. Score: {score:.3f}. {breakdown}"
        else:
            feedback = f"Needs improvement. Score: {score:.3f}. {breakdown}"

        self._last_feedback = feedback

        done = score >= 0.9 or self._state.step_count >= MAX_STEPS

        return SqlReviewObservation(
            task_id=self._current_task["id"],
            difficulty=self._current_task["difficulty"],
            description=self._current_task["description"],
            sql_to_review=self._current_task["buggy_sql"],
            schema_summary=SCHEMA_SUMMARY,
            step_number=self._state.step_count,
            last_feedback=feedback,
            done=done,
            reward=score,
            metadata={"breakdown": breakdown},
        )

    @property
    def state(self) -> State:
        return self._state