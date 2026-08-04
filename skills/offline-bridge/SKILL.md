---
name: offline-bridge
description: Transfer and install GitHub repositories, public HTTPS files, Python wheels, pnpm stores, databases, binaries, models, datasets, and system support libraries into an offline execution environment through GitHub Actions artifacts, with no manual user upload.
---

# Offline Bridge

Use this skill whenever work in the execution environment is blocked because a repository, package, binary, database, model, dataset, or support library cannot be downloaded directly.

## Fixed bridge repository

`datebdio/offline-bridge`

## Supported payloads

- GitHub repository snapshots at a branch, tag, or commit.
- Full Git history when explicitly requested.
- Public HTTPS files, optionally pinned by SHA-256.
- Python wheelhouses generated with `pip download`.
- pnpm offline stores generated with `pnpm fetch`.
- Versioned installation profiles under `profiles/` for software with operating-system-specific runtime dependencies.

Do not use Base64 transfer and do not ask the user to upload bridge artifacts manually.

## Mandatory environment discovery

Before constructing a request for executable software or system packages, inspect the target environment instead of guessing:

```bash
. /etc/os-release && printf '%s %s\n' "$ID" "$VERSION_ID"
uname -m
dpkg --print-architecture 2>/dev/null || true
ps -p 1 -o comm=
tr '\0' ' ' </proc/1/cmdline 2>/dev/null || true
ldd --version | head -1
```

Also check free disk space, whether the requested port is already in use, existing installations, and required shared libraries with `ldd`. The presence of `systemctl` does not mean PID 1 is systemd. Detect the actual service manager from PID 1 and its command line.

## GitHub write authorization and platform confirmations

A normal bridge job requires temporary writes only inside `datebdio/offline-bridge`:

- create one unique `bridge/job-*` branch;
- update `requests/request.json` on that branch;
- open one pull request to `main` to trigger the workflow;
- close that transient pull request without merging after completion.

The user's short invocation may explicitly authorize those temporary operations. Treat that as task-level intent, but do not claim it overrides platform safety controls.

If a GitHub write action is stopped by a platform confirmation or approval check:

1. Do not describe the bridge as failed, illegal, or impossible.
2. Ask one concise confirmation that names the exact temporary operations: branch creation, request update, PR creation, and later PR closure.
3. After approval, resume at the blocked write step. Preserve the detected environment, selected profile, request content, and original user goal.
4. Do not repeat environment discovery, ask the user to paste the long instructions again, or abandon the task.
5. Never bypass, conceal, split, or mislabel an operation to avoid a required confirmation.

If the connector returns an actual permission error rather than a confirmation request:

1. Verify that the GitHub app is connected and has write access to `datebdio/offline-bridge`.
2. Distinguish repository access failure from a temporary safety prompt.
3. Ask the user only for the minimum required action, such as reconnecting GitHub or granting access to this repository.
4. Resume from the blocked step after access is restored.

If the current conversation cannot perform GitHub writes at all, state that exact capability limitation. Do not falsely claim that improving the request JSON, changing Linux commands, or using `apt` will repair a missing GitHub permission.

## Invocation workflow

1. Inspect the target operating system, version, architecture, libc, PID 1, service manager, available disk space, existing installation, and occupied ports.
2. Check `profiles/` for a matching validated installation profile. Prefer a profile over improvising dependency lists.
3. Translate the needed files into `requests/request.json` version 1. For a profile, copy its `request.json` exactly unless a version update is required and verified.
4. Create a unique branch such as `bridge/job-YYYYMMDD-HHMMSS` from `main`.
5. Replace `requests/request.json` on that branch.
6. Open a pull request targeting `main`. The PR triggers `.github/workflows/offline-bridge.yml`.
7. Read the PR head SHA and poll `GitHub.fetch_commit_workflow_runs` until the `Offline Bridge` run completes. Do not stop after merely creating the PR.
8. If the run fails, inspect jobs and logs and fix the request or bridge implementation in the same task.
9. Call `GitHub.fetch_workflow_run_artifacts` for the successful run.
10. Download every artifact from that run using `GitHub.download_workflow_artifact`: `bridge-manifest` and all `bridge-part-*` artifacts.
11. Confirm the returned ZIP files exist under `/mnt/data`.
12. Reconstruct and verify the payload:

```bash
python scripts/receive_bundle.py \
  --artifact-dir /mnt/data/<job-artifact-directory> \
  --destination /mnt/data/offline-bridge/<request-id>
```

13. Read `OFFLINE_BRIDGE_RECEIPT.json` and confirm all hashes passed before using any file.
14. Complete the user's requested operation. For installation requests, run the matching profile installer or perform the installation, dependency resolution, service configuration, and functional test. Downloading is not completion.
15. Close the transient job PR without merging only after the requested operation and verification succeed.

## Installation completion contract

For requests such as “install MySQL in the virtual machine,” the task is complete only when all applicable checks pass:

- The intended product and exact version are installed.
- `ldd` reports no missing shared libraries for the server and primary client.
- The data or application directory is initialized.
- The service is managed by the environment's real process manager, or a documented fallback is running.
- The service reports healthy and remains running.
- The expected local port is listening on the intended address.
- A functional smoke test succeeds; for a database this must include an actual SQL write and read.
- Credentials are not printed into chat or committed to GitHub. Store generated local credentials in a root-only file.
- A machine-readable installation receipt is written when the profile provides one.

Never report success merely because an archive was downloaded, extracted, or because the server binary prints a version.

## Validated MySQL 8.0 profile

For Debian 13 amd64, use:

- Request: `profiles/mysql80/debian13-amd64/request.json`
- Installer: `profiles/mysql80/debian13-amd64/install.sh`

This profile installs MySQL Community Server 8.0.46 and handles three compatibility issues found in real execution:

1. Debian 13 provides `libaio.so.1t64`, while MySQL 8.0 expects `libaio.so.1`.
2. The MySQL 8.0 generic client requires legacy `libncurses.so.5` and `libtinfo.so.5`.
3. Some execution environments run Supervisor as PID 1 using `/etc/supervisord.conf`; writing only `/etc/supervisor/conf.d` is insufficient unless the active configuration includes it.

After the verified payload is restored, run:

```bash
bash profiles/mysql80/debian13-amd64/install.sh \
  /mnt/data/offline-bridge/mysql-8046-debian13-amd64
```

The profile binds MySQL to `127.0.0.1`, generates a root password, stores it in `/root/.my.cnf` with mode `0600`, starts the service using Supervisor, systemd, or a fallback based on the real environment, performs a SQL write/read test, and writes `/etc/mysql/OFFLINE_BRIDGE_INSTALL.json`.

Do not use this profile on another distribution, version, or architecture without creating and validating a matching profile.

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
- Never expose GitHub tokens or generated service credentials in a request, commit, PR, log summary, or chat response.
- Verify the manifest, every part SHA-256, the reconstructed archive SHA-256, and every extracted file SHA-256.
- Extract only through `scripts/receive_bundle.py`; it rejects traversal paths and unsafe special files.
- Treat downloaded code and packages as untrusted until inspected.
- Bind newly installed databases to localhost unless the user explicitly requests remote access and the security implications are handled.
