import logging
import sqlite3
from pathlib import Path

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="Name database where articles are stored", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')

    if not args.db.exists():
        raise Exception(f"Database {args.db} does not exist")
    conn = sqlite3.connect(str(args.db))

    SQL = "select status, count(*) from articles group by status"
    cur = conn.cursor()
    cur.execute(SQL)
    rows = cur.fetchall()
    for status, n in rows:
        print(f"{status}: {n}")
