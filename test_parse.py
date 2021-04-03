from locations import tokenized_kernel, test_output
import parse_cregit
from hypothesis import given, strategies, settings
import random


all_files = list(tokenized_kernel.rglob("*.c"))


@given(strategies.sampled_from(all_files))
@settings(max_examples=1000, deadline=1000)
def test_bad_cases(file):
    parse_cregit.parse_to_file(file, output_dir=test_output)


def test_sample():
    files = random.sample(all_files, 500)
    for file in files:
        parse_cregit.parse_to_file(file, output_dir=test_output)

