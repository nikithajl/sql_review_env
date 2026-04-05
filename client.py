# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""SQL Review Env Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import SqlReviewAction, SqlReviewObservation


class SqlReviewEnv(
    EnvClient[SqlReviewAction, SqlReviewObservation, State]
):
    """
    Client for the SQL Review Environment.

    Example (sync):
        >>> with SqlReviewEnv(base_url="http://localhost:7860").sync() as client:
        ...     result = client.reset()
        ...     result = client.step(SqlReviewAction(sql="SELECT ..."))

    Example (async):
        >>> async with SqlReviewEnv(base_url="http://localhost:7860") as client:
        ...     result = await client.reset()
        ...     result = await client.step(SqlReviewAction(sql="SELECT ..."))
    """

    def _step_payload(self, action: SqlReviewAction) -> Dict:
        return {
            "sql": action.sql,
            "explanation": action.explanation,
        }

    def _parse_result(self, payload: Dict) -> StepResult[SqlReviewObservation]:
        obs_data = payload.get("observation", {})
        observation = SqlReviewObservation(
            task_id=obs_data.get("task_id", ""),
            difficulty=obs_data.get("difficulty", ""),
            task_type=obs_data.get("task_type", ""),
            description=obs_data.get("description", ""),
            sql_to_review=obs_data.get("sql_to_review", ""),
            schema_summary=obs_data.get("schema_summary", ""),
            step_number=obs_data.get("step_number", 0),
            steps_remaining=obs_data.get("steps_remaining", 0),
            success_threshold=obs_data.get("success_threshold", 0.9),
            last_feedback=obs_data.get("last_feedback"),
            reward_info=obs_data.get("reward_info"),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
