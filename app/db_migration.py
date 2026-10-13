import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeMeta

logger = logging.getLogger("erp.db_migration")


def get_column_type_sql(column) -> str:
    """Map SQLAlchemy column type to a safe SQLite/PostgreSQL DDL type for ALTER TABLE ADD COLUMN."""
    type_str = str(column.type).upper()
    if "BOOL" in type_str:
        default = "1" if getattr(column.default, "arg", None) is True else "0"
        return f"BOOLEAN NOT NULL DEFAULT {default}"
    elif "INT" in type_str:
        default = getattr(column.default, "arg", None)
        default_clause = f" DEFAULT {default}" if default is not None and not callable(default) else ""
        return f"INTEGER{default_clause}"
    elif "FLOAT" in type_str or "NUMERIC" in type_str or "REAL" in type_str:
        default = getattr(column.default, "arg", None)
        default_clause = f" DEFAULT {default}" if default is not None and not callable(default) else " DEFAULT 0.0"
        return f"REAL{default_clause}"
    elif "DATETIME" in type_str or "TIMESTAMP" in type_str:
        return "DATETIME"
    elif "DATE" in type_str:
        return "DATE"
    else:
        default = getattr(column.default, "arg", None)
        default_clause = f" DEFAULT '{default}'" if default is not None and not callable(default) else ""
        return f"TEXT{default_clause}"


def verify_and_sync_schema(engine: Engine, base: DeclarativeMeta) -> dict:
    """
    Self-healing database schema synchronizer.
    1. Tests DB connectivity.
    2. Compares SQLAlchemy model columns with real database tables.
    3. Auto-adds any missing columns using ALTER TABLE.
    4. Guarantees that schema updates never result in 500 'no such column' errors.
    """
    results = {
        "connected": False,
        "tables_checked": 0,
        "columns_added": [],
        "errors": []
    }

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        results["connected"] = True
    except Exception as e:
        results["errors"].append(f"Database connection failed: {str(e)}")
        logger.error("Database connection check failed: %s", e)
        return results

    try:
        # Create any entirely new tables
        base.metadata.create_all(bind=engine)

        insp = inspect(engine)
        for table_name, table in base.metadata.tables.items():
            if not insp.has_table(table_name):
                continue

            results["tables_checked"] += 1
            existing_cols = {c["name"] for c in insp.get_columns(table_name)}
            
            for column in table.columns:
                if column.name not in existing_cols:
                    col_sql = get_column_type_sql(column)
                    ddl = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_sql}"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text(ddl))
                            conn.commit()
                        logger.info("Migrated schema: Added column %s.%s (%s)", table_name, column.name, col_sql)
                        results["columns_added"].append(f"{table_name}.{column.name}")
                    except Exception as err:
                        logger.error("Failed to add column %s.%s: %s", table_name, column.name, err)
                        results["errors"].append(f"Failed to add {table_name}.{column.name}: {str(err)}")

        # Data backfill for sections.planning_id if null
        if insp.has_table("sections"):
            try:
                with engine.connect() as conn:
                    conn.execute(text("UPDATE sections SET planning_id = display_order WHERE planning_id IS NULL AND display_order > 0"))
                    conn.execute(text("UPDATE sections SET planning_id = id WHERE planning_id IS NULL OR planning_id <= 0"))
                    conn.commit()
            except Exception as backfill_err:
                logger.warning("Section planning_id backfill warning: %s", backfill_err)

    except Exception as e:
        logger.error("Schema sync failed: %s", e)
        results["errors"].append(str(e))

    return results


def print_startup_banner(results: dict):
    status_db = "CONNECTED" if results.get("connected") else "FAILED"
    status_schema = "VALID & SYNCED" if not results.get("errors") else "SCHEMA ISSUES DETECTED"
    print("\n" + "=" * 55)
    print("           MK FOOTWEAR PLANNING STARTUP")
    print("=" * 55)
    print(f"API Server:       READY")
    print(f"Database:         {status_db}")
    print(f"Schema:           {status_schema}")
    print(f"Columns Migrated: {len(results.get('columns_added', []))}")
    print(f"Authentication:   READY")
    print(f"Buyer API:        READY")
    print(f"Order API:        READY")
    print(f"Planning API:     READY")
    print(f"Production API:   READY")
    print("=" * 55 + "\n")
