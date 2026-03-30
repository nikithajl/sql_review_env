"""All 9 task definitions for the SQL Review environment."""

TASKS: list[dict] = [

    # ── EASY: Bug Fix tasks ──────────────────────────────────────
    {
        "id": "easy_wrong_join",
        "difficulty": "easy",
        "description": (
            "The following query should return the name, email, and total number of orders "
            "for every ACTIVE customer (is_active = 1). It has a bug: it uses a CROSS JOIN "
            "instead of an INNER JOIN, producing a Cartesian product. Fix the query so it "
            "correctly joins users to orders and returns one row per active user with their "
            "order count. Return only the corrected SQL query, nothing else."
        ),
        "buggy_sql": """SELECT u.name, u.email, COUNT(o.id) AS order_count
FROM users u
CROSS JOIN orders o
WHERE u.is_active = 1
GROUP BY u.id
ORDER BY u.name;""",
        "reference_sql": """SELECT u.name, u.email, COUNT(o.id) AS order_count
FROM users u
INNER JOIN orders o ON o.user_id = u.id
WHERE u.is_active = 1
GROUP BY u.id
ORDER BY u.name;""",
        "grader_type": "result_set",
    },

    {
        "id": "easy_missing_filter",
        "difficulty": "easy",
        "description": (
            "The following query should return all products that are NOT soft-deleted "
            "(is_deleted = 0) and have stock_quantity > 0, ordered by price ascending. "
            "The query is missing the stock_quantity filter — it returns out-of-stock items too. "
            "Fix the query. Return only the corrected SQL query, nothing else."
        ),
        "buggy_sql": """SELECT id, name, category, price, stock_quantity
FROM products
WHERE is_deleted = 0
ORDER BY price ASC;""",
        "reference_sql": """SELECT id, name, category, price, stock_quantity
FROM products
WHERE is_deleted = 0
  AND stock_quantity > 0
ORDER BY price ASC;""",
        "grader_type": "result_set",
    },

    {
        "id": "easy_wrong_aggregate",
        "difficulty": "easy",
        "description": (
            "The query below tries to find the average rating per product, but uses SUM "
            "instead of AVG, and joins on the wrong column (p.id = r.user_id). Fix it to "
            "return product_id, product name, and the correct average rating per product. "
            "Return only the corrected SQL query, nothing else."
        ),
        "buggy_sql": """SELECT r.product_id, p.name, SUM(r.rating) AS avg_rating
FROM reviews r
JOIN products p ON p.id = r.user_id
GROUP BY r.user_id
ORDER BY avg_rating DESC;""",
        "reference_sql": """SELECT r.product_id, p.name, AVG(r.rating) AS avg_rating
FROM reviews r
JOIN products p ON p.id = r.product_id
GROUP BY r.product_id
ORDER BY avg_rating DESC;""",
        "grader_type": "result_set",
    },

    # ── MEDIUM: Security Audit tasks ─────────────────────────────
    {
        "id": "medium_sql_injection",
        "difficulty": "medium",
        "description": (
            "The following query template is vulnerable to SQL injection because it "
            "interpolates user input directly into the SQL string. Rewrite it as a safe "
            "parameterized query using a ? placeholder for the user-supplied email value. "
            "Also add a filter so only is_active = 1 users are matched. "
            "Return only the fixed SQL query with ? placeholders."
        ),
        "buggy_sql": (
            "SELECT o.id, o.status, o.total_amount, o.created_at "
            "FROM orders o "
            "JOIN users u ON u.id = o.user_id "
            "WHERE u.email = '{user_input}'"
        ),
        "reference_sql": (
            "SELECT o.id, o.status, o.total_amount, o.created_at "
            "FROM orders o "
            "JOIN users u ON u.id = o.user_id "
            "WHERE u.email = ? AND u.is_active = 1"
        ),
        "grader_type": "security",
        "vuln_patterns": [
            r"\{user_input\}",
            r"'.*\+.*'",
        ],
        "required_patterns": [
            r"\?",
            r"is_active\s*=\s*1",
        ],
    },

    {
        "id": "medium_data_exposure",
        "difficulty": "medium",
        "description": (
            "The query below is used by a customer-facing API to return a user profile. "
            "It exposes ALL columns including sensitive ones like role and is_active. "
            "Rewrite it to: (1) select only id, name, email, and created_at; "
            "(2) filter by a ? placeholder for user id; (3) only return active users. "
            "Return only the corrected SQL query."
        ),
        "buggy_sql": "SELECT * FROM users",
        "reference_sql": (
            "SELECT id, name, email, created_at "
            "FROM users "
            "WHERE id = ? AND is_active = 1"
        ),
        "grader_type": "security",
        "vuln_patterns": [
            r"SELECT\s+\*",
            r"\brole\b",
        ],
        "required_patterns": [
            r"\?",
            r"is_active\s*=\s*1",
        ],
    },

    {
        "id": "medium_over_privilege",
        "difficulty": "medium",
        "description": (
            "The query below joins to the users table unnecessarily, leaking email "
            "addresses and roles into a report. Rewrite it to: (1) select only order id, "
            "status, total_amount, created_at, shipped_at from orders, and product name "
            "and quantity from order_items; (2) do NOT include any user columns; "
            "(3) filter by a ? placeholder for order_id. Return only the fixed SQL query."
        ),
        "buggy_sql": """SELECT *
FROM orders o
JOIN users u ON u.id = o.user_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id;""",
        "reference_sql": """SELECT o.id, o.status, o.total_amount, o.created_at, o.shipped_at,
       p.name AS product_name, oi.quantity
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
WHERE o.id = ?;""",
        "grader_type": "security",
        "vuln_patterns": [
            r"SELECT\s+\*",
            r"\busers\b",
        ],
        "required_patterns": [
            r"\?",
            r"order_items",
        ],
    },

    # ── HARD: Performance Optimization tasks ─────────────────────
    {
        "id": "hard_correlated_subquery",
        "difficulty": "hard",
        "description": (
            "The query below uses a correlated subquery to count each user's orders — "
            "an O(n²) pattern that executes the subquery once per user row. "
            "Rewrite it using a single JOIN with GROUP BY so the database scans once. "
            "Result must return user name, email, and order_count for all active users, "
            "ordered by order_count descending. Add a SQL comment (--) explaining the fix. "
            "Return the full improved SQL query."
        ),
        "buggy_sql": """SELECT
    u.name,
    u.email,
    (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count
FROM users u
WHERE u.is_active = 1
ORDER BY order_count DESC;""",
        "reference_sql": """SELECT u.name, u.email, COUNT(o.id) AS order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.is_active = 1
GROUP BY u.id, u.name, u.email
ORDER BY order_count DESC;""",
        "grader_type": "performance",
        "slow_hint": "correlated subquery executes once per user row",
    },

    {
        "id": "hard_function_on_column",
        "difficulty": "hard",
        "description": (
            "The query below finds orders placed in April 2024 but applies strftime() "
            "directly on the indexed column created_at, preventing index usage (full scan). "
            "Rewrite it using a range comparison (>= and <) on created_at directly so an "
            "index can be used. Result must return order id, user_id, status, total_amount, "
            "created_at for April 2024 orders. Add a comment explaining the fix. "
            "Return the full SQL query."
        ),
        "buggy_sql": """SELECT id, user_id, status, total_amount, created_at
FROM orders
WHERE strftime('%Y-%m', created_at) = '2024-04'
ORDER BY created_at;""",
        "reference_sql": """SELECT id, user_id, status, total_amount, created_at
FROM orders
WHERE created_at >= '2024-04-01'
  AND created_at  < '2024-05-01'
ORDER BY created_at;""",
        "grader_type": "performance",
        "slow_hint": "function call on column prevents index usage",
    },

    {
        "id": "hard_n_plus_one",
        "difficulty": "hard",
        "description": (
            "The query below fetches product details using a separate subquery per "
            "order_item row — a classic N+1 pattern. Rewrite it as a single query with "
            "proper JOINs returning: item id, order_id, unit_price, quantity, product_name, "
            "product_category for all delivered orders. Add a comment explaining N+1 "
            "and how you fixed it. Return the full SQL query."
        ),
        "buggy_sql": """SELECT
    oi.id AS item_id,
    oi.order_id,
    oi.unit_price,
    oi.quantity,
    (SELECT name FROM products WHERE id = oi.product_id) AS product_name,
    (SELECT category FROM products WHERE id = oi.product_id) AS product_category
FROM order_items oi
WHERE oi.order_id IN (
    SELECT id FROM orders WHERE status = 'delivered'
);""",
        "reference_sql": """SELECT
    oi.id AS item_id,
    oi.order_id,
    oi.unit_price,
    oi.quantity,
    p.name AS product_name,
    p.category AS product_category
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status = 'delivered';""",
        "grader_type": "performance",
        "slow_hint": "N+1 subqueries one products lookup per order item row",
    },
]

# Quick lookup by task id
TASK_INDEX: dict[str, dict] = {t["id"]: t for t in TASKS}