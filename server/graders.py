"""Deterministic graders for all SQL Review task types."""

from __future__ import annotations

import pathlib
import re
import sqlite3
from collections import Counter
from typing import Any

SCHEMA_PATH = pathlib.Path(__file__).parent / "schema.sql"
SECURITY_PLACEHOLDER_VALUES = {
    "medium_sql_injection": "'alice@example.com'",
    "medium_data_exposure": "1",
    "medium_over_privilege": "1",
}
SCORE_EPSILON = 0.001


def _make_connection() -> sqlite3.Connection:
    """Return a fresh seeded in-memory SQLite connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def _normalise_rows(rows: list[dict]) -> list[tuple]:
    """Convert rows to sorted tuples for order-independent comparison."""
    if not rows:
        return []
    keys = sorted(rows[0].keys())
    return sorted([tuple(str(r.get(k, "")) for k in keys) for r in rows])


def _strip_comments(sql: str) -> str:
    """Remove SQL line comments for cleaner pattern matching."""
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return " ".join(lines)


def _run_query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    return [dict(r) for r in cur.fetchall()]


def _plan_rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    cur = conn.execute(f"EXPLAIN QUERY PLAN {sql}")
    return cur.fetchall()


def _plan_text(conn: sqlite3.Connection, sql: str) -> str:
    try:
        rows = _plan_rows(conn, sql)
        return " | ".join(str(row[3]).lower() for row in rows)
    except Exception:
        return ""


def _count_plan_nodes(conn: sqlite3.Connection, sql: str) -> int:
    try:
        return len(_plan_rows(conn, sql))
    except Exception:
        return 999


def _substitute_placeholders(sql: str, replacement: str = "'test_value'") -> str:
    return re.sub(r"\?", replacement, sql)


def _lower_clean_sql(sql: str) -> str:
    return _strip_comments(sql).lower()


def _has_placeholder(sql: str) -> bool:
    return "?" in sql


def _extract_select_clause(sql: str) -> str:
    clean = _strip_comments(sql)
    match = re.search(r"select\s+(.*?)\s+from\s", clean, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_selected_aliases(sql: str) -> list[str]:
    clause = _extract_select_clause(sql)
    if not clause:
        return []

    parts = [part.strip() for part in clause.split(",")]
    aliases: list[str] = []

    for part in parts:
        alias_match = re.search(r"\bas\s+([a-zA-Z_][\w]*)\s*$", part, re.IGNORECASE)
        if alias_match:
            aliases.append(alias_match.group(1).lower())
            continue

        tail = part.split(".")[-1].strip()
        tail = re.sub(r"[^a-zA-Z0-9_]", "", tail)
        if tail:
            aliases.append(tail.lower())

    return aliases


def _references_table(sql: str, table_name: str) -> bool:
    pattern = rf"\b{re.escape(table_name.lower())}\b"
    return bool(re.search(pattern, _lower_clean_sql(sql), re.IGNORECASE))


def _contains_select_star(sql: str) -> bool:
    return bool(re.search(r"select\s+\*", _lower_clean_sql(sql), re.IGNORECASE))


def _contains_scalar_subquery(sql: str) -> bool:
    clean = _lower_clean_sql(sql)
    return bool(re.search(r"select\s+.*\(\s*select\b", clean, re.IGNORECASE | re.DOTALL))


def _contains_correlated_subquery(sql: str) -> bool:
    clean = _lower_clean_sql(sql)
    return "select count(*) from orders o where o.user_id = u.id" in clean


def _contains_function_on_created_at(sql: str) -> bool:
    clean = _lower_clean_sql(sql)
    return "strftime('%y-%m', created_at)" in clean or "strftime('%y-%m'" in clean or "strftime('%Y-%m', created_at)".lower() in clean


def _uses_created_at_range(sql: str) -> bool:
    clean = _lower_clean_sql(sql)
    return "created_at >=" in clean and "created_at  <" in clean or (
        "created_at >=" in clean and "created_at <" in clean
    )


def _syntax_valid(sql: str) -> tuple[bool, str]:
    conn = _make_connection()
    try:
        conn.execute(f"EXPLAIN {_substitute_placeholders(sql)}")
        return True, "valid"
    except Exception as exc:
        return False, f"invalid: {exc}"
    finally:
        conn.close()


def _execute_with_task_placeholders(sql: str, task: dict) -> list[dict]:
    replacement = SECURITY_PLACEHOLDER_VALUES.get(task["id"], "'test_value'")
    executable_sql = _substitute_placeholders(sql, replacement)
    conn = _make_connection()
    try:
        return _run_query(conn, executable_sql)
    finally:
        conn.close()


def _semantic_execution_score(agent_sql: str, task: dict) -> tuple[float, dict[str, Any]]:
    breakdown: dict[str, Any] = {}

    try:
        ref_rows = _execute_with_task_placeholders(task["reference_sql"], task)
    except Exception as exc:
        return 0.0, {"execution_error": f"reference query failed: {exc}"}

    try:
        agent_rows = _execute_with_task_placeholders(agent_sql, task)
    except Exception as exc:
        return 0.0, {"execution_error": str(exc)}

    ref_norm = _normalise_rows(ref_rows)
    agent_norm = _normalise_rows(agent_rows)
    breakdown["execution_reference_row_count"] = len(ref_rows)
    breakdown["execution_agent_row_count"] = len(agent_rows)

    if ref_norm == agent_norm:
        breakdown["execution_match"] = "exact"
        return 1.0, breakdown

    overlap = _score_overlap(agent_rows, ref_rows)
    breakdown["execution_match"] = "partial"
    breakdown["execution_overlap_ratio"] = round(overlap, 3)

    if len(agent_rows) == len(ref_rows) and overlap >= 0.75:
        return 0.7, breakdown
    if overlap > 0.0:
        return 0.3, breakdown
    return 0.0, breakdown


def _score_overlap(agent_rows: list[dict], ref_rows: list[dict]) -> float:
    ref_norm = _normalise_rows(ref_rows)
    agent_norm = _normalise_rows(agent_rows)
    if not ref_norm:
        return 0.0
    ref_counts = Counter(ref_norm)
    matching = 0
    for row in agent_norm:
        if ref_counts[row] > 0:
            matching += 1
            ref_counts[row] -= 1
    return matching / len(ref_norm)


def _normalize_score(score: float, breakdown: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Keep public scores strictly inside (0, 1) for submission validation."""
    clamped = max(0.0, min(1.0, float(score)))
    normalized = min(1.0 - SCORE_EPSILON, max(SCORE_EPSILON, clamped))
    if normalized != clamped:
        breakdown["raw_score"] = round(clamped, 3)
    breakdown["normalized_score"] = round(normalized, 3)
    return round(normalized, 3), breakdown


def _score_selected_columns(
    sql: str,
    required: set[str] | None = None,
    forbidden: set[str] | None = None,
) -> tuple[float, dict[str, Any]]:
    required = required or set()
    forbidden = forbidden or set()
    aliases = set(_extract_selected_aliases(sql))

    missing_required = sorted(required - aliases)
    forbidden_present = sorted(aliases & forbidden)

    score = 1.0
    if required:
        score -= 0.5 * (len(missing_required) / len(required))
    if forbidden:
        score -= 0.5 * (len(forbidden_present) / max(len(forbidden), 1))

    return max(0.0, score), {
        "selected_aliases": sorted(aliases),
        "missing_required_columns": missing_required,
        "forbidden_columns_present": forbidden_present,
    }


def _security_semantic_score(agent_sql: str, task: dict) -> tuple[float, dict[str, Any]]:
    task_id = task["id"]
    breakdown: dict[str, Any] = {}

    score = 1.0

    if task_id == "medium_sql_injection":
        has_active_filter = bool(re.search(r"is_active\s*=\s*1", agent_sql, re.IGNORECASE))
        has_placeholder = _has_placeholder(agent_sql)
        selected = set(_extract_selected_aliases(agent_sql))
        expected = {"id", "status", "total_amount", "created_at"}

        breakdown["semantic_has_placeholder"] = has_placeholder
        breakdown["semantic_has_active_filter"] = has_active_filter
        breakdown["selected_aliases"] = sorted(selected)

        if not has_placeholder:
            score -= 0.4
        if not has_active_filter:
            score -= 0.3
        if not expected.issubset(selected):
            score -= 0.3

    elif task_id == "medium_data_exposure":
        has_active_filter = bool(re.search(r"is_active\s*=\s*1", agent_sql, re.IGNORECASE))
        has_id_filter = bool(re.search(r"\bid\s*=\s*\?", agent_sql, re.IGNORECASE))
        col_score, col_breakdown = _score_selected_columns(
            agent_sql,
            required={"id", "name", "email", "created_at"},
            forbidden={"role", "is_active"},
        )
        breakdown.update(col_breakdown)
        breakdown["semantic_has_active_filter"] = has_active_filter
        breakdown["semantic_has_id_filter"] = has_id_filter

        score = col_score
        if not has_active_filter:
            score -= 0.2
        if not has_id_filter:
            score -= 0.2
        if _contains_select_star(agent_sql):
            score -= 0.3

    elif task_id == "medium_over_privilege":
        has_order_filter = bool(re.search(r"\bo\.id\s*=\s*\?|\bid\s*=\s*\?", agent_sql, re.IGNORECASE))
        references_users = _references_table(agent_sql, "users")
        col_score, col_breakdown = _score_selected_columns(
            agent_sql,
            required={"id", "status", "total_amount", "created_at", "shipped_at", "product_name", "quantity"},
            forbidden={"email", "role"},
        )
        breakdown.update(col_breakdown)
        breakdown["semantic_has_order_filter"] = has_order_filter
        breakdown["semantic_references_users"] = references_users

        score = col_score
        if references_users:
            score -= 0.4
        if not has_order_filter:
            score -= 0.2
        if not _references_table(agent_sql, "order_items"):
            score -= 0.1
        if not _references_table(agent_sql, "products"):
            score -= 0.1

    return max(0.0, min(1.0, score)), breakdown


def _performance_antipattern_score(agent_sql: str, task: dict) -> tuple[float, dict[str, Any]]:
    task_id = task["id"]
    clean = _lower_clean_sql(agent_sql)
    breakdown: dict[str, Any] = {}
    score = 1.0

    if task_id == "hard_correlated_subquery":
        still_correlated = _contains_correlated_subquery(clean)
        has_join = " join orders " in clean or " left join orders " in clean
        has_group_by = "group by" in clean

        breakdown["still_correlated_subquery"] = still_correlated
        breakdown["uses_join_orders"] = has_join
        breakdown["uses_group_by"] = has_group_by

        if still_correlated:
            score -= 0.7
        if not has_join:
            score -= 0.15
        if not has_group_by:
            score -= 0.15

    elif task_id == "hard_function_on_column":
        still_uses_function = _contains_function_on_created_at(clean)
        uses_range = _uses_created_at_range(clean)

        breakdown["still_uses_function_on_created_at"] = still_uses_function
        breakdown["uses_created_at_range"] = uses_range

        if still_uses_function:
            score -= 0.7
        if not uses_range:
            score -= 0.3

    elif task_id == "hard_n_plus_one":
        still_scalar = _contains_scalar_subquery(clean)
        joins_products = " join products " in clean
        joins_orders = " join orders " in clean

        breakdown["still_uses_scalar_subquery"] = still_scalar
        breakdown["joins_products"] = joins_products
        breakdown["joins_orders"] = joins_orders

        if still_scalar:
            score -= 0.7
        if not joins_products:
            score -= 0.15
        if not joins_orders:
            score -= 0.15

    return max(0.0, min(1.0, score)), breakdown


# Easy: result-set grader

def grade_result_set(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    Run agent SQL and reference SQL, compare result sets.
    1.0 = exact match, 0.6 = right row count + majority overlap,
    0.3 = ran but wrong, 0.0 = crashed or empty.
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return _normalize_score(0.0, {"error": "empty submission"})

    ref_conn = _make_connection()
    try:
        ref_rows = _run_query(ref_conn, task["reference_sql"])
    except Exception as exc:
        return 0.0, {"error": f"reference query failed: {exc}"}
    finally:
        ref_conn.close()

    agent_conn = _make_connection()
    try:
        agent_rows = _run_query(agent_conn, agent_sql)
    except Exception as exc:
        return 0.0, {"run_error": str(exc)}
    finally:
        agent_conn.close()

    ref_norm = _normalise_rows(ref_rows)
    agent_norm = _normalise_rows(agent_rows)

    breakdown["reference_row_count"] = len(ref_rows)
    breakdown["agent_row_count"] = len(agent_rows)

    if ref_norm == agent_norm:
        breakdown["match"] = "exact"
        return _normalize_score(1.0, breakdown)

    if len(agent_rows) == len(ref_rows):
        ratio = _score_overlap(agent_rows, ref_rows)
        breakdown["match"] = "partial"
        breakdown["row_overlap_ratio"] = round(ratio, 3)
        return _normalize_score((0.6 if ratio >= 0.5 else 0.3), breakdown)

    breakdown["match"] = "wrong"
    return _normalize_score(0.3, breakdown)


# Medium: security grader

def grade_security(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    20% vulnerability removal
    20% required safe patterns
    25% task-specific semantic constraints
    25% execution equivalence against a seeded example
    10% syntax validity
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return _normalize_score(0.0, {"error": "empty submission"})

    clean = _strip_comments(agent_sql)

    vuln_patterns = task.get("vuln_patterns", [])
    vulns_present = [p for p in vuln_patterns if re.search(p, clean, re.IGNORECASE)]
    vuln_score = 1.0 if not vulns_present else max(
        0.0, 1.0 - len(vulns_present) / max(len(vuln_patterns), 1)
    )
    breakdown["vulns_still_present"] = vulns_present
    breakdown["vuln_score"] = round(vuln_score, 3)

    req_patterns = task.get("required_patterns", [])
    missing = [p for p in req_patterns if not re.search(p, clean, re.IGNORECASE)]
    req_score = 1.0 if not missing else max(
        0.0, 1.0 - len(missing) / max(len(req_patterns), 1)
    )
    breakdown["missing_required"] = missing
    breakdown["req_score"] = round(req_score, 3)

    semantic_score, semantic_breakdown = _security_semantic_score(clean, task)
    breakdown.update(semantic_breakdown)
    breakdown["semantic_score"] = round(semantic_score, 3)

    execution_score, execution_breakdown = _semantic_execution_score(clean, task)
    breakdown.update(execution_breakdown)
    breakdown["execution_score"] = round(execution_score, 3)

    syntax_ok, syntax_msg = _syntax_valid(clean)
    syntax_score = 1.0 if syntax_ok else 0.0
    breakdown["syntax"] = syntax_msg

    total = (
        (vuln_score * 0.20)
        + (req_score * 0.20)
        + (semantic_score * 0.25)
        + (execution_score * 0.25)
        + (syntax_score * 0.10)
    )
    normalized, breakdown = _normalize_score(total, breakdown)
    breakdown["total"] = normalized
    return normalized, breakdown


# Hard: performance grader

def grade_performance(agent_sql: str, task: dict) -> tuple[float, dict]:
    """
    40% correctness
    30% task-specific anti-pattern removal
    20% EXPLAIN plan quality
    10% explanation quality
    """
    breakdown: dict[str, Any] = {}

    if not agent_sql or not agent_sql.strip():
        return _normalize_score(0.0, {"error": "empty submission"})

    exec_sql = "\n".join(
        line for line in agent_sql.splitlines() if not line.strip().startswith("--")
    )

    correctness_score = 0.0
    ref_conn = _make_connection()
    agent_conn = _make_connection()
    try:
        ref_rows = _run_query(ref_conn, task["reference_sql"])
        agent_rows = _run_query(agent_conn, exec_sql)
        ref_norm = _normalise_rows(ref_rows)
        agent_norm = _normalise_rows(agent_rows)
        if ref_norm == agent_norm:
            correctness_score = 1.0
            breakdown["correctness"] = "exact match"
        elif len(agent_rows) == len(ref_rows):
            correctness_score = 0.5
            breakdown["correctness"] = "row count matches, data differs"
            breakdown["row_overlap_ratio"] = round(_score_overlap(agent_rows, ref_rows), 3)
        else:
            breakdown["correctness"] = f"expected {len(ref_rows)} rows, got {len(agent_rows)}"
    except Exception as exc:
        breakdown["correctness_error"] = str(exc)
    finally:
        ref_conn.close()
        agent_conn.close()

    antipattern_score, antipattern_breakdown = _performance_antipattern_score(exec_sql, task)
    breakdown.update(antipattern_breakdown)
    breakdown["antipattern_score"] = round(antipattern_score, 3)

    plan_score = 0.0
    buggy_conn = _make_connection()
    opt_conn = _make_connection()
    try:
        buggy_nodes = _count_plan_nodes(buggy_conn, task["buggy_sql"])
        agent_nodes = _count_plan_nodes(opt_conn, exec_sql)
        buggy_plan = _plan_text(buggy_conn, task["buggy_sql"])
        agent_plan = _plan_text(opt_conn, exec_sql)

        breakdown["buggy_plan_nodes"] = buggy_nodes
        breakdown["agent_plan_nodes"] = agent_nodes
        breakdown["buggy_plan"] = buggy_plan
        breakdown["agent_plan"] = agent_plan

        if agent_nodes < buggy_nodes:
            improvement = (buggy_nodes - agent_nodes) / max(buggy_nodes, 1)
            plan_score = min(1.0, 0.4 + improvement)
            breakdown["plan_improvement"] = f"{round(improvement * 100)}% fewer nodes"
        elif agent_nodes == buggy_nodes:
            plan_score = 0.4 if "search" in agent_plan and "scan" not in agent_plan else 0.25
            breakdown["plan_improvement"] = "same plan size"
        else:
            plan_score = 0.1
            breakdown["plan_improvement"] = "query plan got worse"
    except Exception as exc:
        breakdown["plan_error"] = str(exc)
    finally:
        buggy_conn.close()
        opt_conn.close()

    explanation_score = 0.0
    comment_lines = [
        line.strip().lstrip("--").strip()
        for line in agent_sql.splitlines()
        if line.strip().startswith("--")
    ]
    comment_text = " ".join(comment_lines).lower()
    hint_keywords = [w for w in task.get("slow_hint", "").lower().split() if len(w) > 4]

    if comment_text and hint_keywords:
        matches = sum(1 for keyword in hint_keywords if keyword in comment_text)
        explanation_score = min(1.0, matches / max(len(hint_keywords), 1))
        breakdown["explanation_keywords_found"] = matches
    elif comment_text:
        explanation_score = 0.5
        breakdown["explanation"] = "comment present"
    else:
        breakdown["explanation"] = "no comment found"
    breakdown["comment_required"] = True
    breakdown["comment_requirement_met"] = bool(comment_lines)

    total = (
        (correctness_score * 0.40)
        + (antipattern_score * 0.30)
        + (plan_score * 0.20)
        + (explanation_score * 0.10)
    )
    # Hard-task prompts explicitly require a SQL comment explaining the fix.
    # Cap the score below the environment success threshold when that
    # requirement is not met so the grader matches the task contract.
    if not comment_lines and round(total, 3) >= 0.9:
        total = 0.89
        breakdown["comment_cap_applied"] = True

    breakdown["correctness_score"] = round(correctness_score, 3)
    breakdown["plan_score"] = round(plan_score, 3)
    breakdown["explanation_score"] = round(explanation_score, 3)
    normalized, breakdown = _normalize_score(total, breakdown)
    breakdown["total"] = normalized
    return normalized, breakdown


# Dispatcher

def grade(agent_sql: str, task: dict) -> tuple[float, dict]:
    """Route to the correct grader based on task type."""
    grader_type = task.get("grader_type", "result_set")
    if grader_type == "result_set":
        return grade_result_set(agent_sql, task)
    if grader_type == "security":
        return grade_security(agent_sql, task)
    if grader_type == "performance":
        return grade_performance(agent_sql, task)
    return 0.0, {"error": f"unknown grader type: {grader_type}"}
