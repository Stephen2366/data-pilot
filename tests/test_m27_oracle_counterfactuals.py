"""M27 高风险业务 oracle 的小型反事实测试。

这些 fixture 不调用 pipeline/LLM；目标是证明 canonical reference 不是在当前 seed 上“碰巧正确”。
每个坏 SQL 都只缺少一个关键业务条件，并且必须在专门构造的最小数据上暴露差异。
"""

from __future__ import annotations

import sqlite3


def _rows(connection: sqlite3.Connection, sql: str) -> list[tuple[object, ...]]:
    return connection.execute(sql).fetchall()


def test_scd_price_oracle_keeps_open_ended_valid_to_interval() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE products (id INTEGER PRIMARY KEY, product_name TEXT);
        CREATE TABLE product_price_history (product_id INTEGER, price REAL, valid_from TEXT, valid_to TEXT);
        INSERT INTO products VALUES (1, '开放区间商品');
        INSERT INTO product_price_history VALUES (1, 100, '2026-05-01 00:00:00', NULL);
        """
    )
    expected = _rows(connection, """
        SELECT p.product_name, ROUND(AVG(pph.price), 2) FROM products p JOIN product_price_history pph ON pph.product_id = p.id
        WHERE pph.valid_from < '2026-07-01 00:00:00' AND (pph.valid_to IS NULL OR pph.valid_to > '2026-06-01 00:00:00')
        GROUP BY p.id, p.product_name
    """)
    bad_without_open_interval = _rows(connection, """
        SELECT p.product_name, ROUND(AVG(pph.price), 2) FROM products p JOIN product_price_history pph ON pph.product_id = p.id
        WHERE pph.valid_from < '2026-07-01 00:00:00' AND pph.valid_to > '2026-06-01 00:00:00'
        GROUP BY p.id, p.product_name
    """)

    assert expected == [("开放区间商品", 100.0)]
    assert bad_without_open_interval == []


def test_channel_refund_rate_oracle_excludes_non_completed_refunds() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE channels (id INTEGER PRIMARY KEY, channel_name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, channel_id INTEGER, paid_at TEXT, order_status TEXT);
        CREATE TABLE refunds (id INTEGER PRIMARY KEY, order_id INTEGER, refund_status TEXT);
        INSERT INTO channels VALUES (1, 'APP');
        INSERT INTO orders VALUES (10, 1, '2026-06-03 00:00:00', 'paid'), (11, 1, '2026-06-04 00:00:00', 'paid');
        INSERT INTO refunds VALUES (1, 10, 'completed'), (2, 11, 'rejected');
        """
    )
    expected = _rows(connection, """
        WITH eligible_orders AS (
          SELECT id, channel_id FROM orders WHERE paid_at >= '2026-06-01 00:00:00' AND paid_at < '2026-07-01 00:00:00'
            AND order_status NOT IN ('cancelled', 'canceled')
        ), completed_refunds AS (
          SELECT DISTINCT r.order_id FROM refunds r JOIN eligible_orders eo ON eo.id = r.order_id WHERE r.refund_status = 'completed'
        )
        SELECT c.channel_name, COUNT(DISTINCT cr.order_id) * 1.0 / COUNT(DISTINCT eo.id)
        FROM channels c JOIN eligible_orders eo ON eo.channel_id = c.id LEFT JOIN completed_refunds cr ON cr.order_id = eo.id
        GROUP BY c.id, c.channel_name
    """)
    bad_all_refund_statuses = _rows(connection, """
        SELECT c.channel_name, COUNT(DISTINCT r.order_id) * 1.0 / COUNT(DISTINCT o.id)
        FROM channels c JOIN orders o ON o.channel_id = c.id LEFT JOIN refunds r ON r.order_id = o.id
        WHERE o.paid_at >= '2026-06-01 00:00:00' AND o.paid_at < '2026-07-01 00:00:00'
        GROUP BY c.id, c.channel_name
    """)

    assert expected == [("APP", 0.5)]
    assert bad_all_refund_statuses == [("APP", 1.0)]


def test_recursive_category_oracle_includes_descendants() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE product_categories (id INTEGER PRIMARY KEY, name TEXT, parent_id INTEGER);
        CREATE TABLE products (id INTEGER PRIMARY KEY, category_id INTEGER);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, paid_at TEXT, order_status TEXT);
        CREATE TABLE order_items (id INTEGER PRIMARY KEY, product_id INTEGER, order_id INTEGER, line_amount REAL);
        INSERT INTO product_categories VALUES (1, '数码电子', NULL), (2, '手机', 1);
        INSERT INTO products VALUES (1, 2);
        INSERT INTO orders VALUES (1, '2026-06-10 00:00:00', 'paid');
        INSERT INTO order_items VALUES (1, 1, 1, 88.5);
        """
    )
    expected = _rows(connection, """
        WITH RECURSIVE category_tree AS (
          SELECT id, name, parent_id, name AS root_category FROM product_categories WHERE name = '数码电子'
          UNION ALL
          SELECT pc.id, pc.name, pc.parent_id, ct.root_category FROM product_categories pc JOIN category_tree ct ON pc.parent_id = ct.id
        )
        SELECT ct.root_category, ROUND(SUM(oi.line_amount), 2) FROM category_tree ct JOIN products p ON p.category_id = ct.id
        JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id
        WHERE o.paid_at >= '2026-06-01 00:00:00' AND o.paid_at < '2026-07-01 00:00:00'
        GROUP BY ct.root_category
    """)
    bad_direct_category_only = _rows(connection, """
        SELECT pc.name, ROUND(SUM(oi.line_amount), 2) FROM product_categories pc JOIN products p ON p.category_id = pc.id
        JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id
        WHERE pc.name = '数码电子' AND o.paid_at >= '2026-06-01 00:00:00' AND o.paid_at < '2026-07-01 00:00:00'
        GROUP BY pc.name
    """)

    assert expected == [("数码电子", 88.5)]
    assert bad_direct_category_only == []
