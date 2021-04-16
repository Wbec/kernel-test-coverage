import sqlite3


def make_paths_table(root, connection):
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS paths;")
    cursor.execute("CREATE TABLE paths(path, is_dir, levels);")

    def paths():
        for p in root.rglob(""):
            if p == root:
                # root of kernel is filtered out and replaced by an empty string,
                # so that path substrings can be used
                yield "", True, 0
            else:
                shortened_path = p.relative_to(root)
                yield str(shortened_path), p.is_dir(), len(shortened_path.parts)

    cursor.executemany("INSERT INTO paths VALUES (?, ?, ?)", paths())
    connection.commit()


def make_functions_view(connection):
    cursor = connection.cursor()
    cursor.execute("DROP VIEW IF EXISTS functions;")
    cursor.execute(
        """
        CREATE VIEW functions AS
            WITH definitions AS (
                SELECT *, COUNT(*) AS times_defined FROM cregit_functions
                GROUP BY file, name
            ), specifiers AS (
                SELECT file,name, COUNT(*) AS specifier_count FROM cregit_specifiers
                WHERE specifier = 'static'
                GROUP BY file, name
            ), pairs AS (SELECT definitions.file, definitions.name, times_defined,
                IFNULL(specifier_count, 0) AS specifier_count 
                FROM definitions LEFT JOIN specifiers
                ON definitions.file = specifiers.file AND definitions.name = specifiers.name
            )
        SELECT file, name, times_defined, specifier_count,
            CASE
                WHEN times_defined = specifier_count THEN 'static'
                WHEN specifier_count = 0 THEN 'non-static'
                ELSE 'varies' END
            AS is_static
        FROM pairs
        ;"""
    )
    connection.commit()


# The recursive queries for transitive dependencies are very slow, consider using a filter such as
# "call_map.file LIKE some/partial/path/%"
# to only look for calls from functions in a subset of the files.
def transitive_dependencies(connection, direct_calls, filter="1=1"):
    cursor = connection.cursor()
    cursor.execute("DROP VIEW IF EXISTS call_map;")
    cursor.execute(f"""
    CREATE VIEW call_map AS 
    WITH RECURSIVE
        direct_calls AS ({direct_calls}),
    dependencies(file, caller, callee, indicator) AS (
    SELECT file, caller, callee, 'direct' FROM direct_calls WHERE {filter}
    UNION
    SELECT direct_calls.file, direct_calls.caller, dependencies.callee, 'transitive' AS callee
    FROM direct_calls JOIN dependencies ON
        direct_calls.callee = dependencies.caller AND {filter}
    )
    SELECT * FROM dependencies
    ;""")
    connection.commit()


def transitive_calls(connection, **kwargs):
    transitive_dependencies(connection, "SELECT * FROM cregit_calls", **kwargs)


def transitive_identifiers(connection, **kwargs):
    transitive_dependencies(connection,
                            "SELECT file, function AS caller, identifier AS callee FROM cregit_identifiers",
                            **kwargs)


def aggregate_coverage(connection, tests, targets, max_levels=2):
    cursor = connection.cursor()
    if max_levels is not None:
        max_level_filter = f"AND paths.levels <= {max_levels}"
    else:
        max_level_filter = ''
    return cursor.execute(f"""
    WITH tests AS ({tests}), --tests(file, caller, callee) functions that are tests and what they call
    targets AS ({targets}),  --targets(file, name) functions that should/could be tested
    test_counts AS (
        SELECT targets.file, targets.name, COUNT(caller) AS num_tests, caller AS example_test
        FROM targets LEFT JOIN tests ON
            targets.name = tests.callee
        GROUP BY targets.file, targets.name
    )
    SELECT path, COUNT(*) AS num_functions,
        SUM(CASE WHEN num_tests > 0 THEN 1 ELSE 0 END) AS num_tested
    FROM test_counts JOIN paths
    ON (test_counts.file LIKE path || '/%'
        OR test_counts.file = path
        OR path = ''
    ) {max_level_filter}
        -- exact match for files, partial match for directories
        -- slash added so that foo/bar does not match foo/barbaz
    GROUP BY path
    ORDER BY levels;""")


TESTED_IDENTIFIERS = """SELECT file, function AS caller, identifier AS callee
        FROM cregit_identifiers WHERE function LIKE '%test%' AND file LIKE '%test%'"""
TESTED_CALLS = """SELECT * FROM cregit_calls WHERE caller LIKE '%test%' AND file LIKE '%test%'"""

NON_STATIC = "SELECT * FROM functions WHERE is_static != 'static'"
ALL_FUNCTIONS = "SELECT * FROM functions"

def setup_sql(root, outdir):
    connection = sqlite3.connect(outdir / "function_survey.db")
    make_paths_table(root, connection)
    make_functions_view(connection)
