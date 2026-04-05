# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Data models for the SQL Review Env environment."""

from typing import Optional
from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class SqlReviewAction(Action):
    """Action — a corrected SQL query submitted by the agent."""
    sql: str = Field(..., description="The corrected / audited / optimized SQL query")
    explanation: Optional[str] = Field(default=None, description="Optional explanation of changes")


class SqlReviewObservation(Observation):
    """Observation — what the agent sees each step."""
    task_id: str = Field(default="", description="Unique task identifier")
    difficulty: str = Field(default="", description="easy | medium | hard")
    description: str = Field(default="", description="Natural language task description")
    sql_to_review: str = Field(default="", description="The SQL query to fix/audit/optimize")
    schema_summary: str = Field(default="", description="Database schema description")
    step_number: int = Field(default=0, description="Current step in the episode")
    last_feedback: Optional[str] = Field(default=None, description="Feedback from previous step")