import re
import csv

from pathlib import Path
import argparse
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
            item = start[len("begin_"):]
            if item == "function":
                yield "function", *parse_function(lines_in_item(lines, item))
            elif item == "include":
                yield "include", *parse_include(lines_in_item(lines, item))
            else:
                # function_decl will be skipped
                yield skip(lines, item)


def parse_function(lines):
    lines = iter(lines)
    function_name, specifiers = parse_function_decl(lines)
    callees = parse_function_body(lines)
    return function_name, specifiers, callees


def parse_function_decl(lines):
    specifiers = []
    function_name = None
    for start, *rest in lines:
        if start == "specifier":
            assert len(rest) == 1, rest
            specifiers += rest
            # are there other specifiers than static
        elif start == "DECL":
            assert rest[0] == "function", (start, rest)
            function_name = rest[1].split()[0]
        elif start == "name":
            pass  # we may be able to weed out the function name, and get the types if that is usefull
        elif start == "parameter_list" and rest == [")"]:
            break  # this marks the end of the function header
        else:
            pass  # TODO: check what other declaration parts end up here
    # assert function_name is not None
    # in blame/drivers/ssb/main.c the function name_show
    # does not have it's declaration detected
    # by the blame file parser
    # This might be correctable by using the name directly before the function parameters as the function name
    # I will be ignoring this edge case for now.
    return function_name, specifiers


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
    return callees


def parse_include(lines):
    assert len(lines) == 3, lines
    lines = iter(lines)
    assert next(lines) == ["include", "#"], lines
    assert next(lines) == ["directive", "include"], lines
    start, *rest = next(lines)
    assert start == "file" and len(rest) == 1, lines
    return rest


def skip(lines, item):
    """Skips to the end of a begin/end pair"""
    lines_in_item(lines, item)
    return item, "skipped"


def lines_in_item(lines, item):
    """Returns a list of all lines between the begin_? and end_? markers"""
    result = []

    start, *rest = contents = next(lines)
    while start != f"end_{item}":
        assert not start.startswith("end_"), "end of different item found"
        assert not start.startswith("begin_"), "start of different item found"
        result.append(contents)
        start, *rest = contents = next(lines)
    return result


def output_location(input_path):
    output_path = blame_parsed / input_path.relative_to(blame_files)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def parse_to_file(filename):
    parsed = list(parse_whole(filename))
    output_path = output_location(filename)
    with open(output_path.with_suffix(".all_items"), "w") as all_items, open(
        output_path.with_suffix(".functions"), "w"
    ) as functions, open(
        output_path.with_suffix(".specifiers"), "w"
    ) as specifiers, open(
        output_path.with_suffix(".calls"), "w"
    ) as calls, open(
        output_path.with_suffix(".includes"), "w"
    ) as includes:
        all_items.writelines(str(x) + "\n" for x in parsed)  # not csv formatted
        all_items, functions, specifiers, calls, includes = (
            csv.writer(f) for f in (all_items, functions, specifiers, calls, includes)
        )
        for line in parsed:
            if line[0] == "function":
                function_name = line[1]
                functions.writerow([function_name])
                for specifier in line[2]:
                    specifiers.writerow([function_name, specifier])
                for callee in line[3]:
                    calls.writerow([function_name, callee])
            elif line[0] == "include":
                includes.writerow([line[1]])
            else:
                assert line[1] == "skipped"


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("file", type=str)
    parse_to_file(Path(arg_parser.parse_args().file))
