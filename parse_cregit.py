#!/usr/bin/env python
import argparse
import csv
import io
import itertools
import re
import sys
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path

from locations import blame_parsed, blame_files


def parse(filename, expression):
    with open(filename) as f:
        return [re.match(expression, line) for line in f]


def strict_match(pattern, line, flags=0):
    m = re.match(pattern, line, flags=flags)
    if m:
        return m
    raise ValueError(f"{pattern} did not match {line}")


def parse_blame_file(filename):
    expression = (
        r"^(?P<hash>\w{40});" r"(?P<previous_file_name>[^\s;]*);" r"\t(?P<contents>.*)$"
    )
    with open(filename) as f:
        yield from (strict_match(expression, line)["contents"].split("|") for line in f)


def parse_whole(filename):
    lines = parse_blame_file(filename)

    for start, *rest in lines:
        if start in ("begin_unit", "end_unit", ""):
            pass
        elif start.startswith("begin_"):
            item = start[len("begin_") :]
            if item == "function":
                yield "function", *parse_function(lines_in_item(lines, item))
            elif item == "include":
                yield "include", *parse_include(lines_in_item(lines, item))
            elif item == "define":
                yield "define", *parse_define(lines_in_item(lines, item))
            else:
                # function_decl will be skipped
                yield skip(lines, item)


def parse_function(lines):
    lines = iter(lines)
    function_name, specifiers = parse_function_decl(lines)
    callees, names = parse_function_body(lines)
    return function_name, specifiers, callees, names


def parse_function_decl(lines):
    specifiers = []
    function_name = None
    for start, *rest in lines:
        if start == "specifier":
            assert len(rest) == 1, rest
            specifiers += rest
        elif start == "DECL":
            assert rest[0] == "function", (start, rest)
            function_name = rest[1].split()[0]
        elif start == "name":
            pass  # we may be able to weed out the function name, and get the types if that is useful
        elif start == "parameter_list":
            if rest == ["("]:
                skip_function_parameters(lines)
            else:
                assert rest == ["()"], f"unexpected paremeter list value {rest}"
            break
        else:
            pass  # TODO: check what other declaration parts end up here
    # assert function_name is not None
    # in blame/drivers/ssb/main.c the function name_show
    # does not have it's declaration detected
    # by the blame file parser
    # This might be correctable by using the name directly before the function parameters as the function name
    # I will be ignoring this edge case for now.
    return function_name, specifiers


def skip_function_parameters(lines):
    """Skips to the end of the function parameters."""
    for start, *rest in lines:
        if start == "parameter_list" and rest == [")"]:
            return  # this marks the end of the function header
    assert False, "function parameters were not terminated."


def parse_function_body(lines):
    names = []
    callees = []

    contents = next(lines)
    # check if this holds for empty blocks
    # extend to handle function declarations
    #     assert (contents == ["block", "{"] or contents == ["block", "{}"]), "function body must start with block"

    prev_name = None
    for start, *rest in lines:
        if start == "name":
            assert len(rest) == 1
            names += rest
            prev_name = rest[0]
        elif start == "argument_list":
            if rest in [["("], ["()"]]:
                if prev_name is not None:
                    callees.append(prev_name)
            prev_name = None
        else:
            prev_name = (
                None  # assume that argument lists always follow function names directly
            )
    return callees, names


def parse_include(lines):
    assert len(lines) == 3, lines
    lines = iter(lines)
    assert next(lines) == ["include", "#"], lines
    assert next(lines) == ["directive", "include"], lines
    start, *rest = next(lines)
    assert start == "file" and len(rest) == 1, lines
    return rest  # rest is the <included/file>


def parse_define(lines):
    assert lines, "empty define not handled"
    macro_name = first_line = None
    for start, *rest in lines:
        if start == "DECL":
            assert first_line is None, "multiple declarations in one macro"
            macro, first_line = rest
            assert macro == "macro", "Non macro declaration found in a macro"
        elif start == "name" and macro_name is None:
            # extract the first name in the macro, it should be the name of the macro
            assert len(rest) == 1
            macro_name = rest[0]
        else:
            pass

    assert macro_name is not None, "Failed to extract macro name"

    # the input for some macros does not fit this constraint
    # as they lack a DECL line in their cregit tokenization

    # assert first_line is not None, "No macro declaration found"
    # assert first_line.startswith(macro_name)

    return (macro_name,)  # returns tuple to be consistent with include/function parsers


def skip(lines, item):
    """Skips to the end of a begin/end pair"""
    lines_in_item(lines, item)
    return item, "skipped"


def lines_in_item(lines, item):
    """Returns a list of all lines between the begin_? and end_? markers"""
    result = []

    start, *rest = contents = next(lines)
    try:
        while start != f"end_{item}":
            assert not start.startswith("end_"), "end of different item found"
            assert not start.startswith("begin_"), "start of different item found"
            result.append(contents)
            start, *rest = contents = next(lines)
    except StopIteration as e:
        print(result)
        raise e
    return result


# Output to csv


def output_location(input_path):
    output_path = blame_parsed / input_path.resolve().relative_to(blame_files)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


@contextmanager
def cleanup(filepaths):
    """Cleans up any files in `filepaths` if an exception occurs."""
    try:
        yield
    except Exception as e:
        for filepath in filepaths:
            filepath.unlink(missing_ok=True)
        raise e


def parse_to_file(filename):
    parsed = list(parse_whole(filename))
    output_path = output_location(filename)

    suffixes = [
        "all_items",
        "functions",
        "specifiers",
        "calls",
        "includes",
        "names",
        "macros",
    ]
    filepaths = [output_path.with_suffix("." + suffix) for suffix in suffixes]
    # buffers, writers, and files have parallel structures, but are just stored as separate dicts
    buffers = {suffix: io.StringIO() for suffix in suffixes}
    writers = {suffix: csv.writer(buffer) for suffix, buffer in buffers.items()}
    # this way of splitting up the parsing and writing is a bit awkward,
    # since it recreates the structure used in the parser. Passing the files to the parser parts might be cleaner.
    buffers["all_items"].writelines(str(x) + "\n" for x in parsed)
    for item_type, *info in parsed:
        if item_type == "function":
            function_name, specifiers, callees, used_names = info
            writers["functions"].writerow([function_name])
            for specifier in specifiers:
                writers["specifiers"].writerow([function_name, specifier])
            for callee in callees:
                writers["calls"].writerow([function_name, callee])
            for name in used_names:
                writers["names"].writerow([function_name, name])
        elif item_type == "include":
            assert len(info) == 1
            writers["includes"].writerow(info)
        elif item_type == "define":
            assert len(info) == 1
            writers["macros"].writerow(info)
        else:
            assert info[0] == "skipped"
    with ExitStack() as stack:
        files = {
            suffix: stack.enter_context(
                open(output_path.with_suffix("." + suffix), "w")
            )
            for suffix in suffixes
        }
        for suffix in suffixes:
            files[suffix].write(buffers[suffix].getvalue())


def main(files):
    failures = []
    for filename in files:
        try:
            parse_to_file(filename)
        except Exception as e:
            failures.append((filename, e))
            print(traceback.format_exc(), file=sys.stderr)
    return failures


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("files", type=str, nargs="*")
    arg_parser.add_argument("--all", action="store_true")
    args = arg_parser.parse_args()

    if args.all:
        files = [blame_files]
    else:
        files = [Path(f) for f in args.files]
    files = list(
        *(
            itertools.chain(
                f.rglob("*.c.blame")
                if f.is_dir()  # expand out directories to their contents
                else [f]  # wrap single file in a list for chaining
                for f in files
            )
        )
    )

    failures = main(files)
    if failures:
        print(f"{len(failures)} files failed to parse")
        with open("failure_log.txt", "w") as f:
            f.writelines(
                str(file) + ";" + str(message) + "\n" for file, message in failures
            )
