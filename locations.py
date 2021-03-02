from pathlib import Path

project_root = Path(__file__).parent

KERNEL = project_root/"linux-5.10.10"
OUTDIR = project_root/"function_survey/output/"
all_calls = OUTDIR / "cscope_all_calls.txt"
kernel_tags = OUTDIR / "kernel_tags"
test_targets = OUTDIR / "cscope_test_targets"
all_c_code = OUTDIR / "all_c_code.txt"
blame_files = project_root/"blame"
blame_parsed = OUTDIR / "blame_parsed"
