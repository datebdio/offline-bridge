# Offline Bridge

> **Assistant entry point:** read [`START_HERE.md`](START_HERE.md) first. It points to the current operating rules in `skills/offline-bridge/SKILL.md`.

Offline Bridge transfers repositories and support libraries into an execution environment that cannot reach the public internet. GitHub Actions performs the online download and packaging, while the connected GitHub tool downloads the resulting Artifacts directly into the execution environment. The user does not manually upload files.

## What it supports

- GitHub repository snapshots or full Git history
- public HTTPS files with optional SHA-256 pinning
- Python wheelhouses
- pnpm offline stores
- validated installation profiles for system software
- binary-safe, multi-part Artifact transfer
- end-to-end SHA-256 verification and safe extraction

## How a job works

1. The assistant reads `START_HERE.md`, then the latest `skills/offline-bridge/SKILL.md`.
2. A bridge request is committed to a temporary branch.
3. A pull request triggers `.github/workflows/offline-bridge.yml`.
4. `scripts/build_bundle.py` downloads and packages the requested content without executing cloned project code.
5. GitHub stores a manifest Artifact plus one or more binary part Artifacts.
6. The connected GitHub tool downloads those Artifacts directly into `/mnt/data`.
7. `scripts/receive_bundle.py` reconstructs, verifies, and safely extracts the payload.
8. The assistant completes the original installation or execution task and performs a functional smoke test.
9. The temporary PR is closed without merging.

## Request example

```json
{
  "version": 1,
  "request_id": "requests-2323",
  "sources": [
    {
      "type": "github",
      "repository": "psf/requests",
      "ref": "v2.32.3",
      "destination": "sources/requests",
      "include_git_history": false
    }
  ],
  "python": {
    "enabled": true,
    "requirements": ["requests==2.32.3"],
    "requirements_files": [],
    "only_binary": true
  },
  "node": {"enabled": false, "manager": "pnpm"},
  "artifact": {"part_size_mb": 400}
}
```

The request schema is in `schemas/request.schema.json`.

## Private repositories

Public repositories require no extra configuration. To download a different private repository, add a repository secret named `BRIDGE_GITHUB_TOKEN`. Use a fine-grained token limited to read-only Contents access for only the required repositories.

## Offline installation examples

Python:

```bash
python -m pip install --no-index --find-links ./python/wheelhouse -r requirements.txt
```

pnpm:

```bash
pnpm install --offline --frozen-lockfile --store-dir ./node/pnpm-store
```

## Verified transfer path

The direct Artifact-to-execution-environment path was previously tested with a 134.7 MB Artifact containing one 128 MiB binary and 1,500 small files. The production workflow adds multi-part transfer and per-file verification.
