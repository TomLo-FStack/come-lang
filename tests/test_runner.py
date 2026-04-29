#!/usr/bin/env python3
import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NC = "\x1b[0m"
RED = "\x1b[1;38;2;255;255;255;48;2;200;0;0m"
GREEN = "\x1b[1;38;2;255;255;255;48;2;0;150;0m"


def is_windows():
    return os.name == "nt"


def exe_suffix():
    return ".exe" if is_windows() else ""


def rel(root, path):
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def run(cmd, cwd, label=None):
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    if proc.stdout:
        for line in proc.stdout.splitlines():
            if line.strip():
                print(f"    {line}")
    if proc.returncode != 0 and label:
        print(f"    [{RED}FAIL{NC}] {label}")
    return proc.returncode


def compiler_path(root):
    compiler = root / "build" / f"come{exe_suffix()}"
    if not compiler.exists() and not is_windows():
        compiler = root / "build" / "come"
    return compiler


def run_e2e_tests(root):
    test_files = sorted((root / "tests" / "test_files").glob("*.co"))
    if not test_files:
        print("No test files found in tests/test_files/")
        return True

    compiler = compiler_path(root)
    if not compiler.exists():
        print(f"    [{RED}FAIL{NC}] Compiler not found at {compiler}")
        return False

    passed = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="come-e2e-") as td:
        tmp = Path(td)
        for source_file in test_files:
            print(source_file.name)
            expected = []
            for line in source_file.read_text(encoding="utf-8").splitlines():
                if "// EXPECT:" in line:
                    expected.append(line.split("// EXPECT:", 1)[1].strip())

            if not expected:
                print(f"    [SKIP] No expected output defined in {rel(root, source_file)}")
                passed += 1
                continue

            bin_name = tmp / f"{source_file.stem}{exe_suffix()}"
            if run([compiler, "build", source_file, "-o", bin_name], root, "Compilation failed") != 0:
                failed += 1
                continue

            proc = subprocess.run(
                [str(bin_name)],
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
            output = proc.stdout.strip()
            expected_str = "\n".join(expected)
            if proc.returncode == 0 and output == expected_str:
                print(f"    [{GREEN}PASS{NC}]")
                passed += 1
            else:
                print(f"    [{RED}FAIL{NC}] Output mismatch")
                print(f"      Expected:\n{expected_str}")
                print(f"      Got:\n{output}")
                failed += 1

    print(f"\nE2E Summary: {passed} passed, {failed} failed")
    return failed == 0


def unit_specs(root):
    build_tests = root / "build" / "tests"
    return [
        (
            "test_lexer",
            [root / "tests" / "test_lexer.c", root / "src" / "core" / "lexer.c"],
            build_tests / f"test_lexer{exe_suffix()}",
        ),
        (
            "test_parser",
            [
                root / "tests" / "test_parser.c",
                root / "src" / "core" / "parser.c",
                root / "src" / "core" / "lexer.c",
            ],
            build_tests / f"test_parser{exe_suffix()}",
        ),
        (
            "test_codegen",
            [
                root / "tests" / "test_codegen.c",
                root / "src" / "core" / "parser.c",
                root / "src" / "core" / "lexer.c",
                root / "src" / "core" / "codegen.c",
                root / "src" / "core" / "utils.c",
            ],
            build_tests / f"test_codegen{exe_suffix()}",
        ),
        (
            "test_string",
            [
                root / "tests" / "test_string.c",
                root / "src" / "string" / "string.c",
                root / "src" / "mem" / "talloc.c",
                root / "src" / "core" / "utils.c",
            ],
            build_tests / f"test_string{exe_suffix()}",
        ),
    ]


def run_unit_tests(root):
    gcc = shutil.which("gcc")
    if not gcc:
        print(f"    [{RED}FAIL{NC}] gcc not found")
        return False

    build_tests = root / "build" / "tests"
    build_tests.mkdir(parents=True, exist_ok=True)

    include_flags = [
        "-Wall",
        "-g",
        "-D__STDC_WANT_LIB_EXT1__=1",
        "-Isrc/include",
        "-Isrc/core/include",
        "-Isrc/external/talloc/lib/talloc",
        "-Isrc/external/talloc/lib/replace",
    ]

    passed = 0
    failed = 0
    for name, sources, output in unit_specs(root):
        print(name)
        cmd = [gcc, *include_flags, *sources]
        if name == "test_string" and not is_windows():
            cmd.append(root / "src" / "external" / "talloc" / "lib" / "talloc" / "talloc.c")
        cmd.extend(["-o", output])
        if not is_windows():
            cmd.append("-ldl")

        if run(cmd, root, "Compilation failed") != 0:
            failed += 1
            continue
        if run([output], root, "Execution failed") != 0:
            failed += 1
            continue

        print(f"    [{GREEN}PASS{NC}]")
        passed += 1

    print(f"\nUnit Summary: {passed} passed, {failed} failed")
    return failed == 0


def run_come_tests(root):
    compiler = compiler_path(root)
    if not compiler.exists():
        print(f"    [{RED}FAIL{NC}] Compiler not found at {compiler}")
        return False

    tests = sorted((root / "src").glob("**/t/*.co"))
    if not tests:
        print("No COME language tests found under src/**/t/")
        return True

    passed = 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="come-lang-") as td:
        tmp = Path(td)
        for source in tests:
            print(rel(root, source))
            bin_path = tmp / f"{source.parent.parent.name}_{source.stem}{exe_suffix()}"
            if run([compiler, "build", source, "-o", bin_path], root, "Compilation failed") != 0:
                failed += 1
                continue
            if run([bin_path], root, "Runtime failed") != 0:
                failed += 1
                continue
            print(f"    {GREEN}PASS{NC}")
            passed += 1

    print(f"\nCOME Summary: {passed} passed, {failed} failed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--unit", action="store_true")
    parser.add_argument("--e2e", action="store_true")
    parser.add_argument("--come", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    selected = args.all or not (args.unit or args.e2e or args.come)

    ok = True
    print(f"Platform: {platform.system()}")
    if selected or args.e2e:
        ok = run_e2e_tests(root) and ok
    if selected or args.come:
        ok = run_come_tests(root) and ok
    if selected or args.unit:
        ok = run_unit_tests(root) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
