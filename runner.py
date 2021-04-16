import subprocess
import re
import pandas as pd
import sqlite3
import io
import csv

import locations
import parse_cregit
import csv_to_sql, sql_queries


def all_tags():
    result = subprocess.run(
        "git tag", cwd=locations.tokenized_kernel, capture_output=True, shell=True
    )
    return str(result.stdout, "utf-8").strip().split("\n")


def tags():
    result = []
    for tag in all_tags():
        m = re.match(r"^v(\d+)\.(\d+)$", tag)
        if m:
            major, minor = m.groups()
            result.append((tag, int(major), int(minor)))
    return sorted(result, key=lambda x: x[1:3])


def csv_suffix(static=False, transitive=False, identifiers=True):
    return f"{'s' if static else 'ns'}_{'t' if transitive else 'nt'}_{'i' if identifiers else 'ni'}"


def make_csv_path(outdir, static=False, transitive=False, identifiers=True):
    return outdir / f"coverage_by_directory_{csv_suffix(static, transitive, identifiers)}.csv"


def process_tag(tag, static=False, transitive=False, identifiers=True):
    """(Re)generates the parser output, sql database and csv summary data for `tag`, if it is missing.

    This function does not check times that files were modified,
    and treats the parser data as a subtask for making the sql database"""
    print(f"starting {tag}")
    outdir = locations.by_tag / tag
    csv_path = make_csv_path(outdir, static, transitive, identifiers)
    database = outdir / "function_survey.db"
    if not database.exists():
        print("making database")
        subprocess.run(
            f"git checkout -f {tag}",
            cwd=locations.tokenized_kernel,
            shell=True,
            check=True,
        )

        outdir.mkdir(exist_ok=True)
        parse_cregit.parse_all(outdir)

        connection = sqlite3.connect(database)
        csv_to_sql.reset_all(source_dir=outdir, connection=connection)
        sql_queries.make_paths_table(
            root=locations.tokenized_kernel, connection=connection
        )
        sql_queries.make_functions_view(connection)
    else:
        connection = sqlite3.connect(database)
    if not csv_path.exists():
        print("making csv")
        if transitive:
            tests_table = "SELECT * FROM call_map"
            if identifiers:
                sql_queries.transitive_identifiers(connection)
            else:
                sql_queries.transitive_calls(connection)
        elif identifiers:
            tests_table = sql_queries.TESTED_IDENTIFIERS
        else:
            tests_table = sql_queries.TESTED_CALLS

        result = sql_queries.aggregate_coverage(
            connection,
            tests_table,
            sql_queries.ALL_FUNCTIONS if static else sql_queries.NON_STATIC,
            max_levels=None,
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for x in result:
            writer.writerow(x)
        with open(csv_path, "w") as f:
            f.write(buffer.getvalue())


def main(static=False, transitive=False, identifiers=True):
    for tag, major, minor in tags():
        process_tag(tag, static, transitive, identifiers)
    dfs = []
    for tag, major, minor in tags():
        outdir = locations.by_tag / tag
        with open(make_csv_path(outdir, static, transitive, identifiers)) as f:
            temp_df = pd.read_csv(f,
                                  names=["directory",
                                         "functions" if static else "non_static",
                                         "tested"]
                                  ).fillna("")
            temp_df["tag"] = tag
            dfs.append(temp_df)

    df = pd.concat(dfs, ignore_index=True)
    df.to_csv(locations.OUTDIR / f"coverage_by_tag_{csv_suffix(static, transitive, identifiers)}.csv", index=False)


if __name__ == "__main__":
    # warning transitive=True is VERY slow
    main(static=True, transitive=True, identifiers=True)
