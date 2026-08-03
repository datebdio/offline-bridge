#!/usr/bin/env python3
"""Reconstruct, verify and safely extract Offline Bridge artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member(name: str) -> Path:
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise RuntimeError(f"unsafe archive path: {name}")
    return Path(*pure.parts)


def extract_zip(zip_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            rel = safe_member(info.filename)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                with archive.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def discover_manifest(root: Path) -> Path:
    candidates = list(root.rglob("bridge-manifest.json"))
    if len(candidates) != 1:
        raise RuntimeError(f"expected exactly one bridge-manifest.json, found {len(candidates)}")
    return candidates[0]


def verify_tar_members(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        safe_member(member.name)
        if member.ischr() or member.isblk() or member.isfifo():
            raise RuntimeError(f"special files are not allowed: {member.name}")
        if member.issym() or member.islnk():
            link = PurePosixPath(member.linkname.replace("\\", "/"))
            if link.is_absolute() or ".." in link.parts:
                raise RuntimeError(f"unsafe link target: {member.name} -> {member.linkname}")


def extract_tar_safely(tar_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:") as archive:
        verify_tar_members(archive)
        archive.extractall(destination, filter="data")


def verify_payload(destination: Path, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        path = destination / safe_member(row["path"])
        kind = row["type"]
        if kind == "file":
            if not path.is_file():
                raise RuntimeError(f"missing file: {row['path']}")
            if path.stat().st_size != row["size"]:
                raise RuntimeError(f"size mismatch: {row['path']}")
            actual = sha256_file(path)
            if actual != row["sha256"]:
                raise RuntimeError(f"SHA-256 mismatch: {row['path']}")
            mode = row.get("mode")
            if isinstance(mode, int):
                path.chmod(mode & 0o777)
        elif kind == "symlink":
            if not path.is_symlink() or os.readlink(path) != row["target"]:
                raise RuntimeError(f"symlink mismatch: {row['path']}")
        else:
            raise RuntimeError(f"unknown manifest file type: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path, help="Directory containing downloaded artifact ZIP files")
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()

    artifact_dir = args.artifact_dir.resolve()
    zip_files = sorted(artifact_dir.glob("*.zip"))
    if not zip_files:
        raise RuntimeError(f"no ZIP artifacts found in {artifact_dir}")

    work_parent = artifact_dir / ".offline-bridge-work"
    if work_parent.exists():
        shutil.rmtree(work_parent)
    work_parent.mkdir(parents=True)
    expanded = work_parent / "expanded"
    expanded.mkdir()
    for zip_path in zip_files:
        extract_zip(zip_path, expanded)

    manifest_path = discover_manifest(expanded)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = manifest["payload"]

    located: dict[str, Path] = {}
    for file in expanded.rglob("bundle.part-*"):
        located[file.name] = file

    tar_path = work_parent / payload["archive_name"]
    with tar_path.open("wb") as output:
        for part in payload["parts"]:
            name = part["name"]
            source = located.get(name)
            if source is None:
                raise RuntimeError(f"missing bundle part: {name}")
            if source.stat().st_size != part["size"] or sha256_file(source) != part["sha256"]:
                raise RuntimeError(f"bundle part verification failed: {name}")
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)

    if tar_path.stat().st_size != payload["archive_size"]:
        raise RuntimeError("reconstructed archive size mismatch")
    if sha256_file(tar_path) != payload["archive_sha256"]:
        raise RuntimeError("reconstructed archive SHA-256 mismatch")

    destination = args.destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"destination must be empty: {destination}")
    extract_tar_safely(tar_path, destination)
    verify_payload(destination, payload["files"])

    result = {
        "request_id": manifest["request"]["request_id"],
        "destination": str(destination),
        "files_verified": len(payload["files"]),
        "archive_size": payload["archive_size"],
        "archive_sha256": payload["archive_sha256"],
    }
    (destination / "OFFLINE_BRIDGE_RECEIPT.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

    if not args.keep_work:
        shutil.rmtree(work_parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
