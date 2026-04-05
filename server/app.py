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

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schemas = openapi_schema.get("components", {}).get("schemas", {})

    if "ResetRequest" in schemas:
        schemas["ResetRequest"]["example"] = {
            "task_id": "easy_wrong_join"
        }

    if "StepRequest" in schemas:
        schemas["StepRequest"]["example"] = {
            "action": {
                "sql": "SELECT u.name, u.email, COUNT(o.id) AS order_count FROM users u INNER JOIN orders o ON o.user_id = u.id WHERE u.is_active = 1 GROUP BY u.id ORDER BY u.name;",
                "explanation": "Fixed the join condition."
            },
            "task_id": "easy_wrong_join"
        }

    paths = openapi_schema.get("paths", {})

    if "/reset" in paths and "post" in paths["/reset"]:
        content = paths["/reset"]["post"].get("requestBody", {}).get("content", {})
        if "application/json" in content:
            content["application/json"]["example"] = {
                "task_id": "easy_wrong_join"
            }

    if "/step" in paths and "post" in paths["/step"]:
        content = paths["/step"]["post"].get("requestBody", {}).get("content", {})
        if "application/json" in content:
            content["application/json"]["example"] = {
                "action": {
                    "sql": "SELECT u.name, u.email, COUNT(o.id) AS order_count FROM users u INNER JOIN orders o ON o.user_id = u.id WHERE u.is_active = 1 GROUP BY u.id ORDER BY u.name;",
                    "explanation": "Fixed the join condition."
                },
                "task_id": "easy_wrong_join"
            }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


def main(host: str = "0.0.0.0", port: int = 7860):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    if args.port==7860:
        main()
    else:
        main(port=args.port)
