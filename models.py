# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Data models for the SQL Review Env environment."""

from typing import Any, Optional

from openenv.core.env_server.types import Action, Observation
from openenv.core.env_server.types import State as OpenEnvState
from pydantic import BaseModel, Field


class SqlReviewReward(BaseModel):
    """Structured reward details used by graders and the environment."""

    score: float = Field(..., ge=0.0, le=1.0, description="Reward score from 0.0 to 1.0")
    feedback: str = Field(..., description="Human-readable feedback for the latest step")
    breakdown: dict[str, Any] = Field(
        default_factory=dict,
        description="Deterministic grader details for debugging and analysis",
    )


class SqlReviewAction(Action):
    """Action: a corrected SQL query submitted by the agent."""

    sql: str = Field(..., description="The corrected / audited / optimized SQL query")
    explanation: Optional[str] = Field(
        default=None, description="Optional explanation of changes"
    )


class SqlReviewObservation(Observation):
    """Observation: what the agent sees each step."""

    task_id: str = Field(default="", description="Unique task identifier")
    difficulty: str = Field(default="", description="easy | medium | hard")
    task_type: str = Field(
        default="",
        description="High-level task type: result_set, security, or performance",
    )
    description: str = Field(default="", description="Natural language task description")
    sql_to_review: str = Field(
        default="", description="The SQL query to fix/audit/optimize"
    )
    schema_summary: str = Field(default="", description="Database schema description")
    step_number: int = Field(default=0, description="Current step in the episode")
    steps_remaining: int = Field(
        default=0,
        description="Number of attempts remaining in the current episode",
    )
    success_threshold: float = Field(
        default=0.9,
        description="Reward threshold at which the episode is considered solved",
    )
    last_feedback: Optional[str] = Field(
        default=None, description="Feedback from previous step"
    )
    reward_info: Optional[SqlReviewReward] = Field(
        default=None,
        description="Structured reward details for the latest step",
    )


class SqlReviewState(OpenEnvState):
    """State for the current episode."""

    current_task_id: Optional[str] = Field(
        default=None, description="Current task identifier for the episode"
    )
    current_difficulty: Optional[str] = Field(
        default=None, description="Difficulty of the current task"
    )
    last_feedback: Optional[str] = Field(
        default=None, description="Latest grader feedback for the episode"
    )

