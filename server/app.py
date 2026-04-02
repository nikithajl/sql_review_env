# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""FastAPI application for the SQL Review Environment."""

"""FastAPI application for the SQL Review Environment."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:
    raise ImportError(f"openenv is required: {e}") from e

from models import SqlReviewAction, SqlReviewObservation
from server.meta_environment import SqlReviewEnvironment

app = create_app(
    SqlReviewEnvironment,
    SqlReviewAction,
    SqlReviewObservation,
    env_name="sql_review_env",
    max_concurrent_envs=10,
)

@app.get("/")
async def root():
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "healthy", "name": "sql_review_env"})

@app.get("/health")
async def health():
    from fastapi.responses import JSONResponse
    return JSONResponse({"status": "healthy"})

def main(host: str = "0.0.0.0", port: int = 7860):
    import uvicorn
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()