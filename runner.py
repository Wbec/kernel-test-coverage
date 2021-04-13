import subprocess
import re
import random
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


def main():
    for tag, major, minor in tags():
        print(f"starting {tag}")
        outdir = locations.by_tag / tag
        csv_path = outdir / "coverage_by_directory.csv"
        database = outdir / "function_survey.db"
        if csv_path.exists():
            continue
        if not database.exists():
            print("making datbase")
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
        result = sql_queries.aggregate_coverage(
            connection,
            sql_queries.TESTED_IDENTIFIERS,
            sql_queries.NON_STATIC,
            max_levels=None,
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for x in result:
            writer.writerow(x)
        with open(csv_path, "w") as f:
            f.write(buffer.getvalue())


if __name__ == "__main__":
    main()
