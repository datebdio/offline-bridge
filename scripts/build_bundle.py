#!/usr/bin/env python3
"""Build an offline-transfer bundle from a declarative request.

The script intentionally downloads and packages content without executing code from
cloned projects. Python defaults to binary wheels only. pnpm uses `pnpm fetch`,
which populates an offline store without running project lifecycle scripts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

VERSION = 1
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
MAX_PARTS = 8
DEFAULT_PART_SIZE_MB = 400
MAX_PART_SIZE_MB = 900


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    safe = ["***" if "x-access-token:" in item else item for item in cmd]
    print("+", " ".join(safe), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str, field: str) -> Path:
    if not value or "\x00" in value:
        fail(f"{field} must be a non-empty relative path")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        fail(f"{field} must not be absolute or contain '..': {value}")
    return Path(*posix.parts)


def load_request(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != VERSION:
        fail(f"request version must be {VERSION}")
    request_id = data.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        fail("request_id must be 1-80 safe filename characters")
    if not isinstance(data.get("sources", []), list):
        fail("sources must be an array")
    return data


def github_clone(item: dict[str, Any], payload: Path, records: list[dict[str, Any]]) -> None:
    repository = item.get("repository")
    if not isinstance(repository, str) or not REPO_RE.fullmatch(repository):
        fail(f"invalid GitHub repository: {repository!r}")
    ref = item.get("ref", "HEAD")
    if not isinstance(ref, str) or not ref or len(ref) > 200 or ref.startswith("-"):
        fail(f"invalid Git ref for {repository}")
    destination = safe_relative(item.get("destination", f"sources/{repository.split('/')[-1]}"), "destination")
    target = payload / destination
    if target.exists():
        fail(f"duplicate destination: {destination.as_posix()}")
    target.parent.mkdir(parents=True, exist_ok=True)

    token = os.getenv("BRIDGE_GITHUB_TOKEN", "").strip()
    if token:
        url = f"https://x-access-token:{token}@github.com/{repository}.git"
    else:
        url = f"https://github.com/{repository}.git"

    include_history = bool(item.get("include_git_history", False))
    target.mkdir(parents=True)
    run(["git", "init", "--quiet"], cwd=target)
    run(["git", "remote", "add", "origin", url], cwd=target)
    fetch_cmd = ["git", "fetch", "--quiet"]
    if not include_history:
        fetch_cmd += ["--depth", "1"]
    fetch_cmd += ["origin", ref]
    run(fetch_cmd, cwd=target)
    run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=target)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=target, text=True).strip()
    if not include_history:
        shutil.rmtree(target / ".git", ignore_errors=True)
    records.append({
        "type": "github",
        "repository": repository,
        "requested_ref": ref,
        "resolved_commit": commit,
        "destination": destination.as_posix(),
        "include_git_history": include_history,
    })


def public_https_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        fail(f"only credential-free HTTPS URLs are allowed: {url}")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        fail(f"cannot resolve download host {parsed.hostname}: {exc}")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            fail(f"download host resolves to a non-public address: {parsed.hostname} -> {address}")
    return parsed


def download_url(item: dict[str, Any], payload: Path, records: list[dict[str, Any]]) -> None:
    url = item.get("url")
    if not isinstance(url, str):
        fail("URL source requires url")
    parsed = public_https_url(url)
    default_name = Path(urllib.parse.unquote(parsed.path)).name or "download.bin"
    destination = safe_relative(item.get("destination", f"downloads/{default_name}"), "destination")
    target = payload / destination
    if target.exists():
        fail(f"duplicate destination: {destination.as_posix()}")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "offline-bridge/1"})
    expected_sha = str(item.get("sha256", "")).lower().strip()
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    actual_sha = sha256_file(target)
    if expected_sha and actual_sha != expected_sha:
        target.unlink(missing_ok=True)
        fail(f"SHA-256 mismatch for {url}: expected {expected_sha}, got {actual_sha}")
    records.append({
        "type": "url",
        "url": url,
        "destination": destination.as_posix(),
        "size": target.stat().st_size,
        "sha256": actual_sha,
    })


def pip_download(config: dict[str, Any], payload: Path, source_root: Path) -> dict[str, Any] | None:
    if not config or not config.get("enabled", True):
        return None
    requirements = config.get("requirements", [])
    requirement_files = config.get("requirements_files", [])
    if not isinstance(requirements, list) or not all(isinstance(x, str) and x for x in requirements):
        fail("python.requirements must be an array of strings")
    if not isinstance(requirement_files, list) or not all(isinstance(x, str) and x for x in requirement_files):
        fail("python.requirements_files must be an array of relative paths")
    if not requirements and not requirement_files:
        return None

    wheelhouse = payload / "python" / "wheelhouse"
    wheelhouse.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, "-m", "pip", "download", "--dest", str(wheelhouse), "--disable-pip-version-check"]
    only_binary = config.get("only_binary", True)
    if only_binary:
        base += ["--only-binary=:all:"]
    if config.get("no_deps", False):
        base += ["--no-deps"]
    for key, flag in (("platform", "--platform"), ("implementation", "--implementation"), ("python_version", "--python-version"), ("abi", "--abi")):
        value = config.get(key)
        if value:
            base += [flag, str(value)]

    if requirements:
        run(base + requirements)
    for rel in requirement_files:
        req_path = source_root / safe_relative(rel, "python.requirements_files[]")
        if not req_path.is_file():
            fail(f"requirements file not found: {rel}")
        run(base + ["-r", str(req_path)])

    files = sorted(path.name for path in wheelhouse.iterdir() if path.is_file())
    return {"wheelhouse": "python/wheelhouse", "packages": files, "only_binary": bool(only_binary)}


def pnpm_fetch(config: dict[str, Any], payload: Path, source_root: Path) -> dict[str, Any] | None:
    if not config or not config.get("enabled", False):
        return None
    manager = config.get("manager", "pnpm")
    if manager != "pnpm":
        fail("node.manager currently supports only 'pnpm'")
    project_dir = source_root / safe_relative(config.get("project_dir", "."), "node.project_dir")
    lockfile = project_dir / "pnpm-lock.yaml"
    if not lockfile.is_file():
        fail(f"pnpm-lock.yaml not found in {project_dir}")
    version = str(config.get("pnpm_version", "9"))
    run(["corepack", "enable"])
    run(["corepack", "prepare", f"pnpm@{version}", "--activate"])
    store = payload / "node" / "pnpm-store"
    store.mkdir(parents=True, exist_ok=True)
    command = ["pnpm", "fetch", "--frozen-lockfile", "--store-dir", str(store)]
    if config.get("production", False):
        command.append("--prod")
    run(command, cwd=project_dir)
    shutil.copy2(lockfile, payload / "node" / "pnpm-lock.yaml")
    package_json = project_dir / "package.json"
    if package_json.is_file():
        shutil.copy2(package_json, payload / "node" / "package.json")
    return {"manager": "pnpm", "version": version, "store": "node/pnpm-store"}


def file_manifest(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append({"path": rel, "type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            rows.append({
                "path": rel,
                "type": "file",
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "mode": path.stat().st_mode & 0o777,
            })
    return rows


def create_tar(payload: Path, archive: Path) -> None:
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(payload.rglob("*")):
            arcname = path.relative_to(payload).as_posix()
            tar.add(path, arcname=arcname, recursive=False)


def split_file(path: Path, parts_dir: Path, part_size: int) -> list[dict[str, Any]]:
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[dict[str, Any]] = []
    with path.open("rb") as source:
        index = 1
        while True:
            chunk = source.read(part_size)
            if not chunk:
                break
            if index > MAX_PARTS:
                fail(f"bundle needs more than {MAX_PARTS} parts; reduce request size or increase part_size_mb")
            name = f"bundle.part-{index:03d}"
            target = parts_dir / name
            target.write_bytes(chunk)
            parts.append({"name": name, "size": len(chunk), "sha256": sha256_file(target)})
            index += 1
    return parts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    request = load_request(args.request.resolve())
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="offline-bridge-") as temp_name:
        temp = Path(temp_name)
        payload = temp / "payload"
        payload.mkdir()
        source_records: list[dict[str, Any]] = []

        for item in request.get("sources", []):
            if not isinstance(item, dict):
                fail("every source must be an object")
            source_type = item.get("type")
            if source_type == "github":
                github_clone(item, payload, source_records)
            elif source_type == "url":
                download_url(item, payload, source_records)
            else:
                fail(f"unsupported source type: {source_type!r}")

        python_record = pip_download(request.get("python", {}), payload, payload)
        node_record = pnpm_fetch(request.get("node", {}), payload, payload)

        metadata = {
            "request_id": request["request_id"],
            "request_version": request["version"],
            "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "runner": {"platform": sys.platform, "python": sys.version},
            "sources": source_records,
            "python": python_record,
            "node": node_record,
        }
        (payload / "OFFLINE_BRIDGE_INFO.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        files = file_manifest(payload)
        archive = temp / "bundle.tar"
        create_tar(payload, archive)

        artifact_cfg = request.get("artifact", {})
        part_size_mb = int(artifact_cfg.get("part_size_mb", DEFAULT_PART_SIZE_MB))
        if not 1 <= part_size_mb <= MAX_PART_SIZE_MB:
            fail(f"artifact.part_size_mb must be between 1 and {MAX_PART_SIZE_MB}")
        parts = split_file(archive, output / "parts", part_size_mb * 1024 * 1024)

        manifest = {
            "version": VERSION,
            "request": request,
            "build": metadata,
            "payload": {
                "archive_name": "bundle.tar",
                "archive_size": archive.stat().st_size,
                "archive_sha256": sha256_file(archive),
                "part_size_mb": part_size_mb,
                "parts": parts,
                "files": files,
            },
        }
        manifest_dir = output / "manifest"
        manifest_dir.mkdir()
        (manifest_dir / "bridge-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.copy2(args.request, manifest_dir / "request.json")

    print(json.dumps({"request_id": request["request_id"], "parts": len(parts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"offline-bridge build failed: {exc}", file=sys.stderr)
        raise
