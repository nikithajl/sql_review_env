"""Deterministic graders for all SQL Review task types."""

import re
import sqlite3
import pathlib
from typing import Any

SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"


def _make_connection() -> sqlite3.Connection:
    """Return a fresh seeded in-memory SQLite connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def _normalise_rows(rows: list[dict]) -> list[tuple]:
    """Convert rows to sorted list-of-tuples for order-independent comparison."""
    if not rows:
        return []
    keys = sorted(rows[0].keys())
    return sorted([tuple(str(r.get(k, "")) for k in keys) for r in rows])


def _strip_comments(sql: str) -> str:
    """Remove SQL line comments for cleaner pattern matching."""
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return " ".join(lines)


def _run_query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def _count_plan_nodes(conn: sqlite3.Connection, sql: str) -> int:
    try:
        cur = conn.execute(f"EXPLAIN QUERY PLAN {sql}")
        return len(cur.fetchall())
    except Exception:
        return 999


# ── Easy: result-set grader ───────────────────────────────────────

def grade_result_set(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    Run agent SQL and reference SQL, compare result sets.
    1.0 = exact match, 0.6 = right row count + majority overlap,
    0.3 = ran but wrong, 0.0 = crashed or empty.
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return 0.0, {"error": "empty submission"}

    ref_conn = _make_connection()
    try:
        ref_rows = _run_query(ref_conn, task["reference_sql"])
    except Exception as e:
        return 0.0, {"error": f"reference query failed: {e}"}
    finally:
        ref_conn.close()

    agent_conn = _make_connection()
    try:
        agent_rows = _run_query(agent_conn, agent_sql)
    except Exception as e:
        return 0.0, {"run_error": str(e)}
    finally:
        agent_conn.close()

    ref_norm   = _normalise_rows(ref_rows)
    agent_norm = _normalise_rows(agent_rows)

    breakdown["reference_row_count"] = len(ref_rows)
    breakdown["agent_row_count"]     = len(agent_rows)

    if ref_norm == agent_norm:
        breakdown["match"] = "exact"
        return 1.0, breakdown

    if len(agent_rows) == len(ref_rows):
        matching = sum(1 for r in agent_norm if r in ref_norm)
        ratio = matching / max(len(ref_norm), 1)
        breakdown["match"] = "partial"
        breakdown["row_overlap_ratio"] = round(ratio, 3)
        return (0.6 if ratio >= 0.5 else 0.3), breakdown

    breakdown["match"] = "wrong"
    return 0.3, breakdown


# ── Medium: security grader ───────────────────────────────────────

def grade_security(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    40% vuln removal + 40% required safe patterns + 20% syntax validity.
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return 0.0, {"error": "empty submission"}

    clean = _strip_comments(agent_sql)

    # 1. Vulnerability removal (40%)
    vuln_patterns = task.get("vuln_patterns", [])
    vulns_present = [p for p in vuln_patterns if re.search(p, clean, re.IGNORECASE)]
    vuln_score = 1.0 if not vulns_present else max(
        0.0, 1.0 - len(vulns_present) / max(len(vuln_patterns), 1)
    )
    breakdown["vulns_still_present"] = vulns_present
    breakdown["vuln_score"] = round(vuln_score, 3)

    # 2. Required safe patterns (40%)
    req_patterns = task.get("required_patterns", [])
    missing = [p for p in req_patterns if not re.search(p, clean, re.IGNORECASE)]
    req_score = 1.0 if not missing else max(
        0.0, 1.0 - len(missing) / max(len(req_patterns), 1)
    )
    breakdown["missing_required"] = missing
    breakdown["req_score"] = round(req_score, 3)

    # 3. Syntax validity (20%)
    syntax_score = 0.0
    test_sql = re.sub(r"\?", "'test_value'", clean)
    conn = _make_connection()
    try:
        conn.execute(f"EXPLAIN {test_sql}")
        syntax_score = 1.0
        breakdown["syntax"] = "valid"
    except Exception as e:
        breakdown["syntax"] = f"invalid: {e}"
    finally:
        conn.close()

    total = (vuln_score * 0.40) + (req_score * 0.40) + (syntax_score * 0.20)
    breakdown["total"] = round(total, 3)
    return round(total, 3), breakdown


# ── Hard: performance grader ──────────────────────────────────────

def grade_performance(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    40% correctness + 40% EXPLAIN plan improvement + 20% explanation quality.
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return 0.0, {"error": "empty submission"}

    exec_sql = "\n".join(
        l for l in agent_sql.splitlines() if not l.strip().startswith("--")
    )

    # 1. Correctness (40%)
    correctness_score = 0.0
    ref_conn   = _make_connection()
    agent_conn = _make_connection()
    try:
        ref_rows   = _run_query(ref_conn,   task["reference_sql"])
        agent_rows = _run_query(agent_conn, exec_sql)
        ref_norm   = _normalise_rows(ref_rows)
        agent_norm = _normalise_rows(agent_rows)
        if ref_norm == agent_norm:
            correctness_score = 1.0
            breakdown["correctness"] = "exact match"
        elif len(agent_rows) == len(ref_rows):
            correctness_score = 0.5
            breakdown["correctness"] = "row count matches, data differs"
        else:
            breakdown["correctness"] = f"expected {len(ref_rows)} rows, got {len(agent_rows)}"
    except Exception as e:
        breakdown["correctness_error"] = str(e)
    finally:
        ref_conn.close()
        agent_conn.close()

    # 2. Plan quality (40%)
    plan_score = 0.0
    buggy_conn = _make_connection()
    opt_conn   = _make_connection()
    try:
        buggy_nodes = _count_plan_nodes(buggy_conn, task["buggy_sql"])
        agent_nodes = _count_plan_nodes(opt_conn,   exec_sql)
        breakdown["buggy_plan_nodes"] = buggy_nodes
        breakdown["agent_plan_nodes"] = agent_nodes
        if agent_nodes < buggy_nodes:
            improvement = (buggy_nodes - agent_nodes) / max(buggy_nodes, 1)
            plan_score  = min(1.0, improvement * 2)
            breakdown["plan_improvement"] = f"{round(improvement*100)}% fewer nodes"
        elif agent_nodes == buggy_nodes:
            plan_score = 0.3
            breakdown["plan_improvement"] = "no improvement"
        else:
            breakdown["plan_improvement"] = "query plan got worse"
    except Exception as e:
        breakdown["plan_error"] = str(e)
    finally:
        buggy_conn.close()
        opt_conn.close()

    # 3. Explanation quality (20%)
    explanation_score = 0.0
    comment_lines = [
        l.strip().lstrip("--").strip()
        for l in agent_sql.splitlines()
        if l.strip().startswith("--")
    ]
    comment_text = " ".join(comment_lines).lower()
    hint_keywords = [
        w for w in task.get("slow_hint", "").lower().split() if len(w) > 4
    ]
    if comment_text and hint_keywords:
        matches = sum(1 for kw in hint_keywords if kw in comment_text)
        explanation_score = min(1.0, matches / max(len(hint_keywords), 1))
        breakdown["explanation_keywords_found"] = matches
    elif comment_text:
        explanation_score = 0.5
        breakdown["explanation"] = "comment present"
    else:
        breakdown["explanation"] = "no comment found"

    total = (correctness_score * 0.40) + (plan_score * 0.40) + (explanation_score * 0.20)
    breakdown["correctness_score"]   = round(correctness_score, 3)
    breakdown["plan_score"]          = round(plan_score, 3)
    breakdown["explanation_score"]   = round(explanation_score, 3)
    breakdown["total"]               = round(total, 3)
    return round(total, 3), breakdown


# ── Dispatcher ────────────────────────────────────────────────────

def grade(agent_sql: str, task: dict) -> tuple[float, dict]:
    """Route to the correct grader based on task type."""
    grader_type = task.get("grader_type", "result_set")
    if grader_type == "result_set":
        return grade_result_set(agent_sql, task)
    elif grader_type == "security":
        return grade_security(agent_sql, task)
    elif grader_type == "performance":
        return grade_performance(agent_sql, task)
    return 0.0, {"error": f"unknown grader type: {grader_type}"}