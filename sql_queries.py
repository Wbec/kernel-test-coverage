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
                yield '', True, 0
            else:
                shortened_path = p.relative_to(root)
                yield str(shortened_path), p.is_dir(), len(shortened_path.parts)

    cursor.executemany("INSERT INTO paths VALUES (?, ?, ?)", paths())
    connection.commit()

def make_functions_view(connection):
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE VIEW IF NOT EXISTS functions AS
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


def setup_sql(root, outdir):
    connection = sqlite3.connect(outdir / "function_survey.db")
    make_paths_table(root, connection)
    make_functions_view(connection)