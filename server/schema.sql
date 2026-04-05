-- E-commerce schema used across all SQL Review tasks
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'customer',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    total_amount REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    shipped_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    body TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes used to make performance grading more meaningful
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id);

-- Seed data
INSERT INTO users VALUES
    (1, 'alice@example.com', 'Alice Kumar', 'customer', '2024-01-10 08:00:00', 1),
    (2, 'bob@example.com',   'Bob Smith',   'customer', '2024-02-15 09:30:00', 1),
    (3, 'carol@example.com', 'Carol Jones', 'admin',    '2023-11-01 10:00:00', 1),
    (4, 'dave@example.com',  'Dave Lee',    'customer', '2024-03-20 11:00:00', 0),
    (5, 'eve@example.com',   'Eve Patel',   'customer', '2024-04-05 12:00:00', 1);

INSERT INTO products VALUES
    (1, 'Wireless Headphones', 'Electronics', 89.99,  50, 0),
    (2, 'USB-C Hub',           'Electronics', 34.99, 120, 0),
    (3, 'Notebook (A5)',       'Stationery',   4.99, 500, 0),
    (4, 'Coffee Mug',          'Kitchen',      12.99, 200, 0),
    (5, 'Desk Lamp',           'Furniture',    45.00,   0, 0),
    (6, 'Old Keyboard',        'Electronics',  29.99,   0, 1);

INSERT INTO orders VALUES
    (1, 1, 'delivered', 124.98, '2024-03-01 10:00:00', '2024-03-05 14:00:00'),
    (2, 1, 'shipped',    34.99, '2024-04-10 11:00:00', '2024-04-12 09:00:00'),
    (3, 2, 'pending',    45.00, '2024-04-20 15:00:00', NULL),
    (4, 2, 'cancelled',  89.99, '2024-03-15 08:00:00', NULL),
    (5, 5, 'delivered',  17.98, '2024-02-28 09:00:00', '2024-03-03 11:00:00');

INSERT INTO order_items VALUES
    (1, 1, 1, 1, 89.99),
    (2, 1, 2, 1, 34.99),
    (3, 2, 2, 1, 34.99),
    (4, 3, 5, 1, 45.00),
    (5, 4, 1, 1, 89.99),
    (6, 5, 3, 2,  4.99),
    (7, 5, 4, 1, 12.99);

INSERT INTO reviews VALUES
    (1, 1, 1, 5, 'Amazing sound quality!', '2024-03-10 10:00:00'),
    (2, 2, 2, 4, 'Good but gets warm.',    '2024-04-22 11:00:00'),
    (3, 5, 3, 3, 'Average notebook.',      '2024-03-05 09:00:00');