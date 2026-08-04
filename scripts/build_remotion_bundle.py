#!/usr/bin/env python3
"""Build an Offline Bridge bundle with a self-contained Remotion node_modules tree.

This helper reuses the validated bridge builder and only replaces the Node step.
Dependencies are resolved on GitHub Actions with lifecycle scripts disabled, then
copied into the payload so the restricted target does not need npm or pnpm access.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import build_bundle as base


def install_node_project(
    config: dict[str, Any], payload: Path, source_root: Path
) -> dict[str, Any] | None:
    if not config or not config.get("enabled", False):
        return None

    manager = config.get("manager", "pnpm")
    if manager != "pnpm":
        base.fail("node.manager currently supports only 'pnpm'")

    project_dir = source_root / base.safe_relative(
        config.get("project_dir", "."), "node.project_dir"
    )
    package_json = project_dir / "package.json"
    if not package_json.is_file():
        base.fail(f"package.json not found in {project_dir}")

    version = str(config.get("pnpm_version", "10.20.0"))
    base.run(["corepack", "enable"])
    base.run(["corepack", "prepare", f"pnpm@{version}", "--activate"])

    lockfile = project_dir / "pnpm-lock.yaml"
    if not lockfile.is_file():
        base.run(
            [
                "pnpm",
                "install",
                "--lockfile-only",
                "--ignore-scripts",
                "--no-frozen-lockfile",
            ],
            cwd=project_dir,
        )

    store = payload / "node" / "pnpm-store"
    store.mkdir(parents=True, exist_ok=True)
    command = [
        "pnpm",
        "install",
        "--ignore-scripts",
        "--frozen-lockfile",
        "--store-dir",
        str(store),
    ]
    if config.get("production", False):
        command.append("--prod")
    base.run(command, cwd=project_dir)

    target = payload / "node" / "project"
    # copytree follows pnpm links and writes regular files/directories, yielding a
    # portable, self-contained tree accepted by the safe receiver.
    shutil.copytree(project_dir, target, symlinks=False)

    # The installation source still contains pnpm's relative links. It is already
    # duplicated safely above, so remove the linked tree before manifest creation.
    shutil.rmtree(project_dir / "node_modules", ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)

    remaining_links = [str(path) for path in target.rglob("*") if path.is_symlink()]
    if remaining_links:
        base.fail(f"portable node project still contains symlinks: {remaining_links[:5]}")

    return {
        "manager": "pnpm",
        "version": version,
        "project": "node/project",
        "production": bool(config.get("production", False)),
        "lifecycle_scripts": False,
        "symlinks": 0,
    }


base.pnpm_fetch = install_node_project

if __name__ == "__main__":
    raise SystemExit(base.main())
