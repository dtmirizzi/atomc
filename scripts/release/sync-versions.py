#!/usr/bin/env python3
"""Keep every package version in lock-step with ``scripts/release/VERSION``.

PLAN.md §5.2: the monorepo has a *single* version line. The source of truth is
``scripts/release/VERSION``; this script mirrors it into:

* every ``*/python/pyproject.toml`` (the ``[project].version`` field), and
* every ``@atomc/*`` ``package.json`` (the ``version`` field).

Usage::

    python3 scripts/release/sync-versions.py            # write
    python3 scripts/release/sync-versions.py --check    # verify, exit 1 on drift

The ``--check`` mode is run in CI (see .github/workflows/ci.yml and the release
workflows) so that a forgotten bump fails fast instead of publishing a mixed set.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = Path(__file__).resolve().parent / "VERSION"

PYPROJECT_GLOBS = (
    "packages/*/python/pyproject.toml",
    "plugins/*/python/pyproject.toml",
    "apps/*/python/pyproject.toml",
)
PACKAGE_JSON_GLOBS = (
    "packages/*/ts/package.json",
    "plugins/*/ts/package.json",
    "apps/*/package.json",
    "docs/package.json",
)

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_VERSION_RE = re.compile(r'^(?P<prefix>\s*version\s*=\s*)"(?P<value>[^"]*)"(?P<suffix>.*)$')


def read_version() -> str:
    """Return the single source-of-truth version."""
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise SystemExit(f"invalid version in {VERSION_FILE}: {version!r}")
    return version


def discover() -> tuple[list[Path], list[Path]]:
    """Return ``(pyprojects, package_jsons)`` that should be version-stamped."""
    pyprojects: list[Path] = []
    for pattern in PYPROJECT_GLOBS:
        pyprojects.extend(sorted(ROOT.glob(pattern)))
    packages: list[Path] = []
    seen: set[Path] = set()
    for pattern in PACKAGE_JSON_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise SystemExit(f"{path}: invalid JSON: {exc}") from exc
            if str(data.get("name", "")).startswith("@atomc/"):
                packages.append(path)
    return pyprojects, packages


def read_pyproject_version(path: Path) -> str | None:
    in_project = False
    for line in path.read_text(encoding="utf-8").splitlines():
        section = _SECTION_RE.match(line)
        if section:
            in_project = section.group("name") == "project"
            continue
        if in_project:
            match = _VERSION_RE.match(line)
            if match:
                return match.group("value")
    return None


def write_pyproject_version(path: Path, version: str) -> bool:
    """Set ``[project].version`` in *path*. Return True if the file changed."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project = False
    for index, line in enumerate(lines):
        section = _SECTION_RE.match(line.rstrip("\n"))
        if section:
            in_project = section.group("name") == "project"
            continue
        if not in_project:
            continue
        match = _VERSION_RE.match(line.rstrip("\n"))
        if not match:
            continue
        if match.group("value") == version:
            return False
        newline = "\n" if line.endswith("\n") else ""
        lines[index] = f'{match.group("prefix")}"{version}"{match.group("suffix")}{newline}'
        path.write_text("".join(lines), encoding="utf-8")
        return True
    raise SystemExit(f"{path}: could not find [project].version (dynamic version unsupported)")


def write_package_version(path: Path, version: str) -> bool:
    """Set the ``version`` field of a ``package.json``. Return True if changed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") == version:
        return False
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every package matches VERSION instead of writing",
    )
    parser.add_argument(
        "--print",
        dest="print_version",
        action="store_true",
        help="print the source-of-truth version and exit",
    )
    args = parser.parse_args(argv)

    version = read_version()
    if args.print_version:
        print(version)
        return 0

    pyprojects, packages = discover()
    stale: list[str] = []
    changed: list[str] = []

    for path in pyprojects:
        current = read_pyproject_version(path)
        rel = path.relative_to(ROOT)
        if current is None:
            raise SystemExit(f"{rel}: could not find [project].version")
        if args.check:
            if current != version:
                stale.append(f"{rel}: {current} != {version}")
            continue
        if write_pyproject_version(path, version):
            changed.append(str(rel))

    for path in packages:
        rel = path.relative_to(ROOT)
        if args.check:
            current = json.loads(path.read_text(encoding="utf-8")).get("version")
            if current != version:
                stale.append(f"{rel}: {current} != {version}")
            continue
        if write_package_version(path, version):
            changed.append(str(rel))

    if args.check:
        if stale:
            print(f"version drift detected (VERSION={version}):")
            for line in stale:
                print(f"  - {line}")
            print("run: python3 scripts/release/sync-versions.py")
            return 1
        print(f"all {len(pyprojects) + len(packages)} package version(s) match VERSION={version}")
        return 0

    if changed:
        print(f"updated {len(changed)} file(s) to {version}:")
        for line in changed:
            print(f"  - {line}")
    else:
        print(f"all {len(pyprojects) + len(packages)} package version(s) already at {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
