import contextlib
from collections.abc import Generator
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from app.config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def get_connection(*, with_database: bool = True) -> pymysql.Connection:
    kwargs: dict[str, Any] = {
        "host": MYSQL_HOST,
        "port": MYSQL_PORT,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if with_database:
        kwargs["database"] = MYSQL_DATABASE
    return pymysql.connect(**kwargs)


def ensure_database() -> None:
    try:
        conn = get_connection(with_database=False)
    except pymysql.Error as exc:
        raise RuntimeError(f"Failed to connect to MySQL server: {exc}") from exc

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    except pymysql.Error as exc:
        raise RuntimeError(f"Failed to ensure database '{MYSQL_DATABASE}': {exc}") from exc
    finally:
        conn.close()


@contextlib.contextmanager
def db_cursor() -> Generator[Any, None, None]:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
