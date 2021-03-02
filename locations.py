from pathlib import Path


KERNEL = Path("linux-5.10.10")
OUTDIR = Path("function_survey/output/")
all_calls = OUTDIR / "cscope_all_calls.txt"
kernel_tags = OUTDIR / "kernel_tags"
test_targets = OUTDIR / "cscope_test_targets"
all_c_code = OUTDIR / "all_c_code.txt"
blame_files = Path("blame")
blame_parsed = Path(OUTDIR / "blame_parsed")
