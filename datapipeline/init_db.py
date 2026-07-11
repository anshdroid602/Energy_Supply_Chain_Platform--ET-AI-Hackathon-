"""Apply schema.sql to whatever DATABASE_URL points to (Neon or local).

Run from the repo root:
    python3 -m datapipeline.init_db
"""
import os

from datapipeline.common.db import connect

SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def main():
    with open(SCHEMA) as f:
        sql = f.read()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    target = os.environ.get("DATABASE_URL", "local default (localhost)")
    print("Schema applied to:", target.split("@")[-1])  # hide password in the print


if __name__ == "__main__":
    main()
