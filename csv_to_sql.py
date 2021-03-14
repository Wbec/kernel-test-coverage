#!/usr/bin/env python

import csv
import sqlite3

from locations import blame_parsed, OUTDIR


connection = sqlite3.connect(OUTDIR / "function_survey.db")
cursor = connection.cursor()

def read_csv(filename):
    with open(filename) as f:
        reader = csv.reader(f)
        for row in reader:
            yield row


def corresponding_kernel_file(filename):
    """Get the path to the kernel file corresponding to parsed intermediary output file."""
    return str(filename.relative_to(blame_parsed).with_suffix(""))


def reset_table(table_name, suffix, column_names):
    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    cursor.execute(f"CREATE TABLE {table_name} ({','.join(column_names)})")
    placeholder = ", ".join(["?"] * len(column_names))
    cursor.executemany(
        f"INSERT INTO {table_name} VALUES ({placeholder})",
        (
            (corresponding_kernel_file(filename), *row)
            # assumes no extra commas in file contents. Will error if this is not true.
            for filename in blame_parsed.rglob(f"*.c.{suffix}")
            for row in read_csv(filename)
        ),
    )
    connection.commit()

def reset_all():
    reset_table("cregit_functions", "functions", ("file", "name"))
    reset_table("cregit_calls", "calls", ("file", "caller", "callee"))
    reset_table("cregit_includes", "includes", ("file", "include"))
    reset_table("cregit_specifiers", "specifiers", ("file", "name", "specifier"))
    reset_table("cregit_identifiers", "names", ("file", "function", "identifier"))
    reset_table("cregit_macros", "macros", ("file", "name"))


if __name__ == "__main__":
    reset_all()
