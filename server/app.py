# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""FastAPI application for the SQL Review Environment."""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(
        "openenv is required. Install with: pip install openenv-core"
    ) from e

try:
    from models import SqlReviewAction, SqlReviewObservation
    from server.meta_environment import SqlReviewEnvironment
except ModuleNotFoundError:
    from ..models import SqlReviewAction, SqlReviewObservation
    from .meta_environment import SqlReviewEnvironment

app = create_app(
    SqlReviewEnvironment,
    SqlReviewAction,
    SqlReviewObservation,
    env_name="sql_review_env",
    max_concurrent_envs=10,
)


def main(host: str = "0.0.0.0", port: int = 7860):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    main(port=args.port)