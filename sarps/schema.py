"""
Upgrade the database schema to match the models.
"""
from sqlalchemy import inspect, text

from sarps.extensions import db


def upgrade_schema(engine=None):
    engine = engine or db.engine
    quote = engine.dialect.identifier_preparer.quote
    inspector = inspect(engine)
    done = []
    with engine.begin() as connection:
        for table in db.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"]: c for c in inspector.get_columns(table.name)}
            for column in table.columns:
                sql_type = column.type.compile(dialect=engine.dialect)
                if column.name not in existing:
                    if not column.nullable:
                        done.append(f"SKIPPED {table.name}.{column.name}: required column cannot be added to a table with rows")
                        continue
                    connection.execute(text(
                        f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} {sql_type} NULL"))
                    done.append(f"added {table.name}.{column.name}")
                elif column.nullable and existing[column.name]["nullable"] is False:
                    if engine.dialect.name in ("mysql", "mariadb"):
                        connection.execute(text(
                            f"ALTER TABLE {quote(table.name)} MODIFY COLUMN {quote(column.name)} {sql_type} NULL"))
                        done.append(f"made {table.name}.{column.name} optional")
                    else:
                        done.append(f"SKIPPED {table.name}.{column.name}: this database type cannot change a column in place")
    return done
