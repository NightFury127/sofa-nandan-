"""
Stallion Project Health Check
==============================
Runs a systematic sweep of the whole project and writes one report:
    docs/health_report.md

This does NOT fix anything. It finds and categorizes problems so they
can be fixed deliberately, one at a time, with review -- not silently
patched by a script.

Usage (from the Stallion project root, inside the venv):
    python scripts/health_check.py

Checks performed:
  1. Python syntax errors (compileall) across every .py file
  2. Broken imports (each src/ module imported in isolation)
  3. Full pytest suite run with captured output
  4. requirements.txt vs. actually-installed package versions
  5. Hardcoded absolute paths (Windows/Unix) in source files
  6. Bare `except:` / `except Exception:` blocks with no logging
  7. TODO / FIXME / HACK markers
  8. Missing __init__.py in src/ (import ambiguity risk)
  9. Orphaned files referenced in code but missing on disk
     (e.g. models/sofa_detector.pt, data/*.csv paths)
"""

import ast
import importlib
import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
REPORT_PATH = ROOT / "docs" / "health_report.md"

report_sections = []


def section(title):
    report_sections.append(f"\n## {title}\n")


def line(text):
    report_sections.append(text)


def find_py_files(base):
    return [p for p in base.rglob("*.py") if ".venv" not in p.parts]


# ---------------------------------------------------------------------------
# 1. Syntax errors
# ---------------------------------------------------------------------------
def check_syntax():
    section("1. Syntax Errors")
    files = find_py_files(ROOT)
    errors = []
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"- `{f.relative_to(ROOT)}`: {e.msg}")
    if errors:
        line(f"**{len(errors)} file(s) failed to compile:**\n")
        report_sections.extend(errors)
    else:
        line(f"✅ All {len(files)} Python files compiled cleanly.")


# ---------------------------------------------------------------------------
# 2. Broken imports (import each src/ module in isolation)
# ---------------------------------------------------------------------------
def check_imports():
    section("2. Import Check (src/ modules)")
    if not SRC.exists():
        line("⚠️ No src/ directory found.")
        return
    sys.path.insert(0, str(SRC))
    modules = [p.stem for p in SRC.glob("*.py") if p.stem != "__init__"]
    errors = []
    for mod in modules:
        result = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            cwd=str(SRC),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(f"- `{mod}.py`:\n```\n{result.stderr.strip()[-500:]}\n```")
    if errors:
        line(f"**{len(errors)} module(s) failed to import:**\n")
        report_sections.extend(errors)
    else:
        line(f"✅ All {len(modules)} src/ modules imported cleanly (in isolation).")


# ---------------------------------------------------------------------------
# 3. Full pytest run
# ---------------------------------------------------------------------------
def check_tests():
    section("3. Test Suite")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--tb=short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr)[-4000:]
    line(f"Exit code: `{result.returncode}`\n")
    line("```")
    report_sections.append(output)
    line("```")


# ---------------------------------------------------------------------------
# 4. requirements.txt vs installed versions
# ---------------------------------------------------------------------------
def check_requirements():
    section("4. requirements.txt vs Installed Versions")
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        line("⚠️ No requirements.txt found at project root.")
        return
    mismatches = []
    missing = []
    for raw_line in req_file.read_text().splitlines():
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith("#") or "==" not in raw_line:
            continue
        pkg, _, pinned_version = raw_line.partition("==")
        pkg = pkg.strip()
        pinned_version = pinned_version.strip()
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            missing.append(pkg)
            continue
        match = re.search(r"Version:\s*(\S+)", result.stdout)
        installed_version = match.group(1) if match else "UNKNOWN"
        if installed_version != pinned_version:
            mismatches.append(f"- `{pkg}`: pinned=`{pinned_version}` installed=`{installed_version}`")
    if missing:
        line(f"**{len(missing)} package(s) in requirements.txt are NOT installed:**\n")
        report_sections.extend(f"- `{m}`" for m in missing)
    if mismatches:
        line(f"\n**{len(mismatches)} version mismatch(es):**\n")
        report_sections.extend(mismatches)
    if not missing and not mismatches:
        line("✅ All pinned requirements match installed versions.")


# ---------------------------------------------------------------------------
# 5. Hardcoded absolute paths
# ---------------------------------------------------------------------------
def check_hardcoded_paths():
    section("5. Hardcoded Absolute Paths")
    pattern = re.compile(r"""["'](?:[A-Za-z]:\\|/home/|/Users/|/mnt/)[^"']*["']""")
    hits = []
    for f in find_py_files(ROOT):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, l in enumerate(text.splitlines(), 1):
            if pattern.search(l):
                hits.append(f"- `{f.relative_to(ROOT)}:{i}`: `{l.strip()[:120]}`")
    if hits:
        line(f"**{len(hits)} hardcoded absolute path(s) found:**\n")
        report_sections.extend(hits)
    else:
        line("✅ No hardcoded absolute paths found.")


# ---------------------------------------------------------------------------
# 6. Silent exception handling
# ---------------------------------------------------------------------------
def check_bare_excepts():
    section("6. Silent / Bare Exception Handling")
    hits = []
    for f in find_py_files(ROOT):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                body_is_trivial = (
                    len(node.body) == 1
                    and isinstance(node.body[0], (ast.Pass,))
                ) or (
                    len(node.body) == 1
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                )
                if node.type is None or body_is_trivial:
                    hits.append(f"- `{f.relative_to(ROOT)}:{node.lineno}`")
    if hits:
        line(f"**{len(hits)} bare/silent except block(s) found:**\n")
        report_sections.extend(hits)
    else:
        line("✅ No bare or silently-swallowing except blocks found.")


# ---------------------------------------------------------------------------
# 7. TODO / FIXME / HACK markers
# ---------------------------------------------------------------------------
def check_todos():
    section("7. TODO / FIXME / HACK Markers")
    pattern = re.compile(r"#\s*(TODO|FIXME|HACK)\b(.*)", re.IGNORECASE)
    hits = []
    for f in find_py_files(ROOT):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, l in enumerate(text.splitlines(), 1):
            m = pattern.search(l)
            if m:
                hits.append(f"- `{f.relative_to(ROOT)}:{i}`: {m.group(0).strip()}")
    if hits:
        line(f"**{len(hits)} marker(s) found:**\n")
        report_sections.extend(hits)
    else:
        line("✅ No TODO/FIXME/HACK markers found.")


# ---------------------------------------------------------------------------
# 8. Missing __init__.py
# ---------------------------------------------------------------------------
def check_init_files():
    section("8. Package Structure")
    if SRC.exists() and not (SRC / "__init__.py").exists():
        line(f"⚠️ `src/__init__.py` is missing. Not necessarily a bug (namespace "
             f"packages work without it), but confirm this is intentional.")
    else:
        line("✅ src/ package structure looks fine.")


# ---------------------------------------------------------------------------
# 9. Referenced files that don't exist on disk
# ---------------------------------------------------------------------------
def check_referenced_files():
    section("9. Referenced Files Missing on Disk")
    pattern = re.compile(r"""["'](data/[^"']+\.(csv|json|pt)|models/[^"']+\.pt)["']""")
    hits = []
    checked = set()
    for f in find_py_files(ROOT):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in pattern.finditer(text):
            rel = m.group(1)
            if rel in checked:
                continue
            checked.add(rel)
            if not (ROOT / rel).exists():
                hits.append(f"- `{rel}` (referenced in `{f.relative_to(ROOT)}`) does not exist")
    if hits:
        line(f"**{len(hits)} referenced file(s) missing on disk:**\n")
        report_sections.extend(hits)
    else:
        line("✅ All referenced data/model file paths exist on disk.")


def main():
    report_sections.append("# Stallion Project Health Report\n")
    report_sections.append(f"Generated by `scripts/health_check.py`. This report finds problems;\n"
                            f"it does not fix them. Review each section and fix deliberately.\n")

    check_syntax()
    check_imports()
    check_requirements()
    check_hardcoded_paths()
    check_bare_excepts()
    check_todos()
    check_init_files()
    check_referenced_files()
    check_tests()  # run last: slowest, and other checks are more actionable first

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_sections), encoding="utf-8")
    print(f"\nHealth report written to: {REPORT_PATH}")
    print("Open it and work through each section top to bottom.")


if __name__ == "__main__":
    main()
