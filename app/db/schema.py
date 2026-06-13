from app.db.connection import db_cursor, ensure_database


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    row = cursor.fetchone()
    return bool(row and row["cnt"] > 0)


def _index_exists(cursor, table: str, index_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        (table, index_name),
    )
    row = cursor.fetchone()
    return bool(row and row["cnt"] > 0)


def _migrate_datasets_rag_columns(cursor) -> None:
    migrations = [
        ("ragflow_kb_id", "ALTER TABLE datasets ADD COLUMN ragflow_kb_id VARCHAR(64) NULL"),
        (
            "rag_index_status",
            "ALTER TABLE datasets ADD COLUMN rag_index_status "
            "VARCHAR(20) NOT NULL DEFAULT 'pending'",
        ),
        ("rag_index_error", "ALTER TABLE datasets ADD COLUMN rag_index_error TEXT NULL"),
    ]
    for column, statement in migrations:
        if not _column_exists(cursor, "datasets", column):
            cursor.execute(statement)


def _migrate_datasets_content_hash(cursor) -> None:
    if not _column_exists(cursor, "datasets", "content_hash"):
        cursor.execute("ALTER TABLE datasets ADD COLUMN content_hash CHAR(64) NULL")
    if not _index_exists(cursor, "datasets", "idx_datasets_content_hash"):
        cursor.execute(
            "CREATE UNIQUE INDEX idx_datasets_content_hash ON datasets (content_hash)"
        )


def init_schema() -> None:
    ensure_database()

    statements = [
        """
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id VARCHAR(32) PRIMARY KEY,
            original_filename VARCHAR(255) NOT NULL,
            stored_filename VARCHAR(255) NOT NULL,
            file_ext VARCHAR(10) NOT NULL,
            file_size_bytes BIGINT NOT NULL,
            row_count INT NOT NULL,
            column_count INT NOT NULL,
            profile_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id VARCHAR(32) PRIMARY KEY,
            dataset_id VARCHAR(32) NOT NULL,
            created_at DATETIME(6) NOT NULL,
            updated_at DATETIME(6) NOT NULL,
            INDEX idx_sessions_dataset (dataset_id),
            CONSTRAINT fk_sessions_dataset
                FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            session_id VARCHAR(32) NOT NULL,
            turn_index INT NOT NULL,
            question TEXT NOT NULL,
            summary TEXT,
            generated_code MEDIUMTEXT,
            success TINYINT(1) NOT NULL DEFAULT 1,
            has_charts TINYINT(1) NOT NULL DEFAULT 0,
            result_json JSON,
            charts_json JSON,
            error TEXT,
            created_at DATETIME(6) NOT NULL,
            UNIQUE KEY uk_session_turn (session_id, turn_index),
            INDEX idx_turns_session (session_id),
            CONSTRAINT fk_turns_session
                FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]

    try:
        with db_cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            _migrate_datasets_rag_columns(cursor)
            _migrate_datasets_content_hash(cursor)
    except Exception as exc:
        raise RuntimeError(f"Failed to initialize database schema: {exc}") from exc
