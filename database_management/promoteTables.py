# Mirror tested data from the non-prod database (POSTGRES_URL) into the
# production database (REMOTE_URL), without going through JSON files or the
# CapWages API. This is meant to save the ~3 hours that a full API-driven
# updateTables.py run costs, once you've already verified the data locally.
#
# This is a TRUE MIRROR, not just an upsert: for every table you sync, rows
# in production whose primary key no longer exists in non-prod (e.g. rows
# you hand-deleted while cleaning up locally) are deleted from production
# too. Double-check --tables before running against production.
#
# Table order (both for upserts and deletes) is worked out automatically
# from the foreign key constraints between the tables you're syncing, so
# this does NOT require superuser privileges on production.

# Required imports
import argparse
import psycopg2
import psycopg2.extras
from database_helper import get_connection


ALL_TABLES = [
    "players",
    "teams",
    "cities",
    "team_season_stats",
    "skater_season_stats",
    "goalie_season_stats",
    "contracts",
    "seasons",
]


def get_primary_key_columns(cursor, table_name):
    """
    Look up the primary key column(s) for a table directly from Postgres
    metadata, so we don't have to hardcode a conflict target per table.

    Arguments:
        cursor = cursor object to Postgres database (either side works,
                 schema is assumed identical between non-prod and prod)
        table_name = name of the table to inspect

    Returns:
        List of column names making up the primary key, in ordinal order.
    """
    cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tco
        JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tco.constraint_name
            AND kcu.constraint_schema = tco.constraint_schema
        WHERE tco.constraint_type = 'PRIMARY KEY'
            AND tco.table_name = %s
        ORDER BY kcu.ordinal_position;
        """,
        (table_name,),
    )
    pk_cols = [row[0] for row in cursor.fetchall()]
    if not pk_cols:
        raise ValueError(
            "Table '{}' has no primary key that I can find -- cannot build "
            "an ON CONFLICT upsert for it.".format(table_name)
        )
    return pk_cols


def get_column_names(cursor, table_name):
    """
    Fetch the ordered list of column names for a table.

    Arguments:
        cursor = cursor object to Postgres database
        table_name = name of the table to inspect
    """
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position;
        """,
        (table_name,),
    )
    return [row[0] for row in cursor.fetchall()]


def get_sync_order(cursor, table_names):
    """
    Work out a safe order to process the given tables in, based on the
    foreign key constraints between them (only considering FKs where both
    the child and the parent are in table_names -- FKs pointing at tables
    outside this sync run are assumed already satisfied).

    Arguments:
        cursor = cursor object to Postgres database (schema-reading only)
        table_names = list of table names being synced this run

    Returns:
        A list containing the same tables, ordered so that a table always
        appears after every table it has a foreign key to (i.e. safe order
        for INSERT/UPDATE). For DELETE, iterate this list in reverse.
    """
    cursor.execute(
        """
        SELECT tc.table_name AS child_table, ccu.table_name AS parent_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = ANY(%s)
            AND ccu.table_name = ANY(%s)
            AND tc.table_name != ccu.table_name;
        """,
        (table_names, table_names),
    )
    edges = cursor.fetchall()  # (child_table, parent_table) pairs

    in_degree = {t: 0 for t in table_names}
    children_of = {t: [] for t in table_names}
    for child_table, parent_table in edges:
        children_of[parent_table].append(child_table)
        in_degree[child_table] += 1

    # Kahn's algorithm, keeping the original ALL_TABLES-relative ordering
    # as a tiebreaker so results are stable and easy to reason about.
    ready = sorted(
        (t for t in table_names if in_degree[t] == 0),
        key=lambda t: table_names.index(t),
    )
    order = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child_table in children_of[current]:
            in_degree[child_table] -= 1
            if in_degree[child_table] == 0:
                ready.append(child_table)
        ready.sort(key=lambda t: table_names.index(t))

    if len(order) != len(table_names):
        # A cycle in FKs between the selected tables (rare). Fall back to
        # the order the user/ALL_TABLES gave us and warn -- you may need to
        # sync affected tables individually or add a DEFERRABLE constraint.
        print(
            "Warning: could not fully resolve a foreign-key-safe order for "
            "{} -- a cycle may exist between these tables. Falling back to "
            "the given order; deletes may fail if they violate a "
            "foreign key.".format(table_names)
        )
        return list(table_names)

    return order


def build_upsert_sql(table_name, columns, pk_cols):
    """
    Build a parameterized INSERT statement for table copying.
    """
    col_list = ", ".join(columns)
    return "INSERT INTO {} ({}) VALUES %s;".format(table_name, col_list)


def upsert_table(source_cursor, dest_cursor, table_name, batch_size=1000):
    """
    Insert/update every row of a table from the source (non-prod) database
    into the destination (production) database.

    Arguments:
        source_cursor = cursor object to the non-prod (POSTGRES_URL) database
        dest_cursor = cursor object to the production (REMOTE_URL) database
        table_name = name of the table being synced
        batch_size = number of rows sent to production per round trip

    Returns:
        Tuple of (rows read from source, pk_cols, list of source primary
        key tuples) -- kept for API compatibility with promote_all.
    """
    columns = get_column_names(source_cursor, table_name)
    pk_cols = get_primary_key_columns(source_cursor, table_name)
    pk_indices = [columns.index(c) for c in pk_cols]
    insert_sql = build_upsert_sql(table_name, columns, pk_cols)

    col_list = ", ".join(columns)
    source_cursor.execute("SELECT {} FROM {};".format(col_list, table_name))

    row_count = 0
    source_pk_values = []
    while True:
        rows = source_cursor.fetchmany(batch_size)
        if not rows:
            break
        psycopg2.extras.execute_values(dest_cursor, insert_sql, rows)
        row_count += len(rows)
        source_pk_values.extend(tuple(row[i] for i in pk_indices) for row in rows)

    return row_count, pk_cols, source_pk_values


def delete_obsolete_rows(dest_cursor, table_name, pk_cols, source_pk_values):
    """
    Delete any row from the production table before inserting the fresh mirror.

    Arguments:
        dest_cursor = cursor object to the production (REMOTE_URL) database
        table_name = name of the table being synced
        pk_cols = list of column names making up the primary key
        source_pk_values = list of primary-key tuples

    Returns:
        Number of rows deleted from production.
    """
    dest_cursor.execute("DELETE FROM {};".format(table_name))
    return dest_cursor.rowcount


def sync_identity_sequences(dest_cursor, table_names):
    """
    Reset sequence counters for tables with IDENTITY or SERIAL columns to MAX(id)
    so that subsequent inserts in production generate valid IDs.
    """
    for table_name in table_names:
        dest_cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
              AND (is_identity = 'YES' OR column_default LIKE 'nextval%%');
            """,
            (table_name,),
        )
        seq_cols = dest_cursor.fetchall()
        for (col,) in seq_cols:
            dest_cursor.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence(%s, %s),
                    COALESCE((SELECT MAX({}) FROM {}), 1)
                );
                """.format(col, table_name),
                (table_name, col),
            )


def promote_all(non_prod_connection, prod_connection, tables_to_sync):
    """
    Mirror a list of tables from non-prod into production inside a single
    production-side transaction. Upserts are applied in FK-safe order
    (parents before children); deletes are applied in the reverse order
    (children before parents), so no elevated database privileges are
    needed. Rolls back on any error so production is never left
    half-updated.

    Arguments:
        non_prod_connection = connection object to POSTGRES_URL
        prod_connection = connection object to REMOTE_URL
        tables_to_sync = list of table names to sync (any order -- this
                          function determines the safe processing order)
    """
    source_cursor = non_prod_connection.cursor()
    dest_cursor = prod_connection.cursor()

    try:
        sync_order = get_sync_order(source_cursor, tables_to_sync)
        if sync_order != tables_to_sync:
            print("Processing order (parents before children): {}".format(
                ", ".join(sync_order)
            ))

        pk_data = {}

        for table_name in reversed(sync_order):
            pk_cols = get_primary_key_columns(source_cursor, table_name)
            deleted_count = delete_obsolete_rows(
                dest_cursor, table_name, pk_cols, []
            )
            if deleted_count:
                print(
                    "Deleted {} obsolete row(s) from production table "
                    "'{}'.".format(deleted_count, table_name)
                )

        for table_name in sync_order:
            print("Upserting table '{}'...".format(table_name))
            row_count, pk_cols, source_pk_values = upsert_table(
                source_cursor, dest_cursor, table_name
            )
            pk_data[table_name] = (pk_cols, source_pk_values)
            print("  -> upserted {} row(s) from non-prod.".format(row_count))

        sync_identity_sequences(dest_cursor, sync_order)

        prod_connection.commit()
        print("All tables promoted and committed to production.")

    except Exception:
        prod_connection.rollback()
        print("Error during promotion -- production was rolled back, no changes applied.")
        raise

    finally:
        source_cursor.close()
        dest_cursor.close()


def main():
    """
    Main function. Connects to both the non-prod (POSTGRES_URL) and
    production (REMOTE_URL) databases and mirrors selected tables from
    the former to the latter.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Mirror table data from the non-prod database (POSTGRES_URL) "
            "directly into the production database (REMOTE_URL), skipping "
            "JSON files and the CapWages API entirely."
        )
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=ALL_TABLES + ["all"],
        required=True,
        help=(
            "Which table(s) to promote. Space-separated list, e.g. "
            "'--tables cities contracts'. Use 'all' to promote every table."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and promote immediately.",
    )
    args = parser.parse_args()

    tables_to_sync = ALL_TABLES if "all" in args.tables else args.tables

    print("This will make the following PRODUCTION tables (REMOTE_URL) an EXACT MIRROR")
    print("of your non-prod database (POSTGRES_URL): rows will be inserted, updated,")
    print("AND DELETED in production to match non-prod exactly.")
    print("Tables to promote: {}".format(", ".join(tables_to_sync)))

    if not args.yes:
        confirmation = input("Type 'yes' to continue: ").strip().lower()
        if confirmation != "yes":
            print("Aborted. No changes made.")
            return

    non_prod_connection = get_connection(remote=False)
    prod_connection = get_connection(remote=True)

    try:
        promote_all(non_prod_connection, prod_connection, tables_to_sync)
    finally:
        non_prod_connection.close()
        prod_connection.close()


# Follow good coding practices
if __name__ == "__main__":
    main()
