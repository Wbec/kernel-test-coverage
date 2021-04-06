#!/usr/bin/env python

import csv
import sqlite3

from locations import blame_parsed, OUTDIR


def read_csv(filename):
    with open(filename) as f:
        reader = csv.reader(f)
        for row in reader:
            yield row


def corresponding_kernel_file(filename, source_dir):
    """Get the path to the kernel file corresponding to parsed intermediary output file."""
    return str(filename.relative_to(source_dir).with_suffix(""))


def reset_table(table_name, suffix, column_names, connection, source_dir):
    cursor = connection.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    cursor.execute(f"CREATE TABLE {table_name} ({','.join(column_names)})")
    placeholder = ", ".join(["?"] * len(column_names))
    cursor.executemany(
        f"INSERT INTO {table_name} VALUES ({placeholder})",
        (
            (corresponding_kernel_file(filename, source_dir), *row)
            # assumes no extra commas in file contents. Will error if this is not true.
            for filename in source_dir.rglob(f"*.{suffix}")
            for row in read_csv(filename)
        ),
    )
    connection.commit()


def reset_all(source_dir, connection):
    for table_name, suffix, column_names in (
        ("cregit_functions", "functions", ("file", "name")),
        ("cregit_calls", "calls", ("file", "caller", "callee")),
        ("cregit_includes", "includes", ("file", "include")),
        ("cregit_specifiers", "specifiers", ("file", "name", "specifier")),
        ("cregit_identifiers", "names", ("file", "function", "identifier")),
        ("cregit_macros", "macros", ("file", "name")),
    ):
        reset_table(table_name, suffix, column_names, connection, source_dir)
    cursor = connection.cursor()
    cursor.execute("CREATE INDEX idx_functions ON cregit_functions (file, name);")
    cursor.execute("CREATE INDEX idx_calls ON cregit_calls (file,caller,callee);")
    cursor.execute(
        "CREATE INDEX idx_identifiers ON cregit_identifiers (file,function,identifier);"
    )
    connection.commit()


if __name__ == "__main__":
    connection = sqlite3.connect(OUTDIR / "function_survey.db")
    reset_all(blame_parsed, connection)
