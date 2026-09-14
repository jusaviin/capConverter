"""
Copies data from an existing SQLite database into an already-created
Postgres database with a matching (but not necessarily identical)
schema. Column names are read dynamically from SQLite rather than
hardcoded, since some tables here have 100+ columns.

Usage:
    pip install psycopg2-binary
    python3 migrate_data.py path/to/old.db "postgresql://user:pass@host/dbname"

Assumes the Postgres schema has already been created (e.g. via
databaseSchema_postgres.sql) and is empty. Tables are migrated in an
order that respects foreign key dependencies.
"""

import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

# Order matters: a table must come after every table it has a foreign
# key pointing to.
TABLE_ORDER = [
    "cities",
    "players",
    "seasons",
    "teams",
    "contracts",
    "team_season_stats",
    "skater_season_stats",
    "goalie_season_stats",
]

# Tables whose "id" column is a Postgres IDENTITY (auto-incrementing)
# column, as opposed to players.id which holds real NHL API IDs and
# must never be auto-generated. After bulk-loading explicit id values
# into these tables, Postgres's internal sequence needs to be told
# what the highest id actually is -- otherwise the next auto-generated
# id could collide with one we just inserted.
IDENTITY_TABLES = {
    "contracts",
    "team_season_stats",
    "skater_season_stats",
    "goalie_season_stats",
}


def migrate_table(sqlite_conn, pg_conn, table_name):
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"  {table_name}: no rows, skipping")
        return 0

    # Column names come from SQLite's cursor description, not typed by
    # hand -- this is what makes the script work unmodified even for
    # the very wide stats tables. Lowercased because the target schema
    # was created with unquoted identifiers, which Postgres silently
    # folds to lowercase (e.g. name_NHL_API -> name_nhl_api) -- using
    # the original SQLite casing here would look for a column that,
    # quoted, doesn't actually exist.
    columns = [description[0] for description in sqlite_cur.description]
    quoted_columns = ", ".join(f'"{col.lower()}"' for col in columns)

    insert_sql = f'INSERT INTO {table_name} ({quoted_columns}) VALUES %s'

    pg_cur = pg_conn.cursor()
    execute_values(pg_cur, insert_sql, rows, page_size=500)
    pg_conn.commit()

    print(f"  {table_name}: {len(rows)} rows migrated")
    return len(rows)


def resync_identity_sequence(pg_conn, table_name):
    """
    After bulk-loading rows with explicit id values into an IDENTITY
    column, Postgres's sequence still thinks the next id is 1 (or
    wherever it was left). Point it at MAX(id)+1 so future INSERTs
    that omit id don't collide with data we just imported.
    """
    pg_cur = pg_conn.cursor()
    pg_cur.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{table_name}', 'id'),
            COALESCE((SELECT MAX(id) FROM {table_name}), 1)
        )
    """)
    pg_conn.commit()
    print(f"  {table_name}: id sequence resynced")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python3 {sys.argv[0]} <sqlite_db_path> <postgres_connection_string>")
        sys.exit(1)

    sqlite_path, pg_conn_string = sys.argv[1], sys.argv[2]

    sqlite_conn = sqlite3.connect(sqlite_path)
    pg_conn = psycopg2.connect(pg_conn_string)

    print("Migrating data...")
    try:
        for table in TABLE_ORDER:
            migrate_table(sqlite_conn, pg_conn, table)

        print("\nResyncing auto-increment sequences...")
        for table in IDENTITY_TABLES:
            resync_identity_sequence(pg_conn, table)

        print("\nDone.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
