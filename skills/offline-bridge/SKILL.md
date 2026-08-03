---
name: offline-bridge
description: Transfer GitHub repositories, public HTTPS files, Python wheels, and pnpm stores into the offline execution environment through GitHub Actions artifacts, with no manual user upload.
---

# Offline Bridge

Use this skill whenever work in the execution environment is blocked because a repository, package, binary, model, dataset, or support library cannot be downloaded directly.

## Fixed bridge repository

`datebdio/offline-bridge`

## Supported payloads

- GitHub repository snapshots at a branch, tag, or commit.
- Full Git history when explicitly requested.
- Public HTTPS files, optionally pinned by SHA-256.
- Python wheelhouses generated with `pip download`.
- pnpm offline stores generated with `pnpm fetch`.

Do not use Base64 transfer and do not ask the user to upload bridge artifacts manually.

## Invocation workflow

1. Translate the needed files into `requests/request.json` version 1.
2. Create a unique branch such as `bridge/job-YYYYMMDD-HHMMSS` from `main`.
3. Replace `requests/request.json` on that branch.
4. Open a pull request targeting `main`. The PR triggers `.github/workflows/offline-bridge.yml`.
5. Read the PR head SHA and poll `GitHub.fetch_commit_workflow_runs` until the `Offline Bridge` run completes.
6. If the run fails, inspect jobs and logs and fix the request or bridge implementation.
7. Call `GitHub.fetch_workflow_run_artifacts` for the successful run.
8. Download every artifact from that run using `GitHub.download_workflow_artifact`. Download `bridge-manifest` and all `bridge-part-*` artifacts.
9. Confirm the returned files exist under `/mnt/data`.
10. Run:

```bash
python scripts/receive_bundle.py \
  --artifact-dir /mnt/data/<job-artifact-directory> \
  --destination /mnt/data/offline-bridge/<request-id>
```

11. Read `OFFLINE_BRIDGE_RECEIPT.json` and confirm all hashes passed before using any file.
12. Close the job PR without merging. Do not merge transient request files into `main`.

## Request construction

### GitHub source

```json
{
  "type": "github",
  "repository": "owner/repository",
  "ref": "main",
  "destination": "sources/repository",
  "include_git_history": false
}
```

Public repositories work without secrets. Accessing another private repository requires the bridge repository secret `BRIDGE_GITHUB_TOKEN` containing a fine-grained token with read-only Contents access to that repository.

### Python wheels

Default to binary wheels only:

```json
{
  "enabled": true,
  "requirements": ["requests==2.32.3"],
  "requirements_files": [],
  "only_binary": true
}
```

For a non-native target, set `platform`, `implementation`, `python_version`, and `abi`. Do not guess these values when they materially affect compatibility; inspect the target environment first.

### pnpm store

```json
{
  "enabled": true,
  "manager": "pnpm",
  "project_dir": "sources/app",
  "pnpm_version": "9",
  "production": false
}
```

The source directory must contain `pnpm-lock.yaml`. `pnpm fetch` does not run project lifecycle scripts.

### Large payloads

Use `artifact.part_size_mb` between 100 and 400 by default. The workflow supports up to eight parts. Prefer multiple parts over one multi-gigabyte artifact.

## Safety rules

- Never execute code from cloned projects during packaging.
- Keep Python `only_binary` enabled unless source distributions are explicitly required and the execution risk is accepted.
- Only credential-free HTTPS URLs are accepted; private, loopback, and link-local destinations are rejected.
- Never expose GitHub tokens in a request or commit.
- Verify the manifest, every part SHA-256, the reconstructed archive SHA-256, and every extracted file SHA-256.
- Extract only through `scripts/receive_bundle.py`; it rejects traversal paths and unsafe special files.
- Treat downloaded code and packages as untrusted until inspected.
