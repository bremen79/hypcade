#!/usr/bin/env python3
# Hypcade: Copyright (C) 2026 Francesco Orabona.
"""Fetch exact native sources; never reset an existing or modified checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "third_party"
MARKER = ".hypseus-source.json"


def git(directory, *arguments, capture=False):
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments], check=True,
        text=True, stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else None


def read_lock():
    lock = json.loads((ROOT / "dependencies.lock.json").read_text())
    if lock.get("schema") != 1:
        raise RuntimeError("Unsupported dependency lock schema")
    return lock["dependencies"]


def verify_source_bundle(directory, dependency):
    """A release source ZIP has no Git metadata; verify its recorded file hashes."""
    marker = directory / MARKER
    if not marker.is_file():
        raise RuntimeError(f"{directory} already exists without Git metadata. "
                           "Move it aside before fetching dependencies.")
    record = json.loads(marker.read_text())
    if record.get("commit") != dependency["commit"]:
        raise RuntimeError(f"Bundled version mismatch: {directory}")
    for name, expected in record.get("sha256", {}).items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise RuntimeError(f"Missing or invalid bundled source: {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Bundled source changed: {path}")
    if not record.get("sha256"):
        raise RuntimeError(f"Empty source manifest: {marker}")


def checkout(dependency, verify_only):
    destination = DEST / dependency["name"]
    expected = dependency["commit"]
    if destination.exists() and not (destination / ".git").exists():
        verify_source_bundle(destination, dependency)
        print(f"Verified bundled {dependency['name']} {dependency['version']}")
        return
    if not destination.exists():
        if verify_only:
            raise RuntimeError(f"Missing {destination}; run bootstrap-deps.py first")
        destination.mkdir(parents=True)
        git(destination, "init", "--quiet")
        git(destination, "remote", "add", "origin", dependency["url"])
        git(destination, "fetch", "--depth=1", "origin", expected)
        git(destination, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    actual = git(destination, "rev-parse", "HEAD", capture=True)
    if actual != expected:
        raise RuntimeError(f"{destination} is at {actual}, expected {expected}. "
                           "Existing checkouts are never reset automatically.")
    dirty = git(destination, "status", "--porcelain", "--untracked-files=no",
                "--ignore-submodules=all", capture=True)
    if dirty:
        raise RuntimeError(f"Tracked dependency files have local edits: {destination}")
    submodules = dependency.get("submodules", {})
    if submodules and not verify_only:
        git(destination, "submodule", "update", "--init", "--depth=1", "--",
            *submodules.keys())
    for relative, revision in submodules.items():
        subdir = destination / relative
        if not (subdir / ".git").exists():
            raise RuntimeError(f"Missing submodule {subdir}")
        actual = git(subdir, "rev-parse", "HEAD", capture=True)
        if actual != revision:
            raise RuntimeError(f"Unexpected submodule revision: {subdir}: {actual}")
        if git(subdir, "status", "--porcelain", "--untracked-files=no", capture=True):
            raise RuntimeError(f"Submodule has local edits: {subdir}")
    print(f"Verified {dependency['name']} {dependency['version']} ({expected[:12]})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Verify only; do not download")
    args = parser.parse_args()
    if not shutil.which("git"):
        raise RuntimeError("Git is required to fetch or verify dependencies")
    DEST.mkdir(exist_ok=True)
    for dependency in read_lock():
        checkout(dependency, args.verify)
    print("Android native sources are ready.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Dependency setup failed: {error}", file=sys.stderr)
        sys.exit(1)
