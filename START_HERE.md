# Offline Bridge — Assistant Entry Point

When a task in an offline or restricted execution environment needs software, dependencies, source code, binaries, models, datasets, fonts, system libraries, or any other external resource, immediately read and follow:

`skills/offline-bridge/SKILL.md`

Treat that file as the current source of truth. Do not rely on remembered instructions.

Key requirements:

- Inspect the target operating system, architecture, runtime, PID 1, service manager, disk space, existing installation, ports, and shared-library requirements before choosing packages.
- Prefer a matching validated profile under `profiles/`.
- Use the GitHub Actions Artifact bridge; do not ask the user to download or upload transfer files manually.
- Continue through dependency resolution, installation, startup, and a real functional smoke test. Downloading or extracting files is not completion.
- If new dependencies are discovered, run additional bridge jobs until the original task succeeds.
- Verify all hashes and close transient job pull requests without merging them.
- Ask the user only for genuinely necessary authorization, secrets, licenses, irreversible choices, destructive changes, or public-network exposure.

## GitHub write confirmation

Offline Bridge jobs normally require these temporary writes in `datebdio/offline-bridge`:

1. create a temporary `bridge/job-*` branch;
2. replace `requests/request.json` on that branch;
3. open a pull request to trigger GitHub Actions;
4. close the pull request without merging when the task finishes.

A repository instruction cannot override platform-level safety checks. If the platform requires confirmation for one of these writes:

- do not report the bridge as failed or impossible;
- ask for one concise confirmation covering the exact temporary branch, request update, PR creation, and later PR closure;
- after approval, resume from the blocked step in the same task;
- do not repeat environment discovery or ask the user to restate the original request;
- never bypass or disguise a required confirmation.

Distinguish confirmation from permission failure:

- **Confirmation required:** ask once, then continue after approval.
- **Permission denied or repository unavailable:** verify the connected GitHub app can write to `datebdio/offline-bridge`; ask the user only to reconnect or grant repository access.

The canonical short invocation is stored in `SHORT_PROMPT.md`.

This is the stable entry point. Detailed behavior belongs in `skills/offline-bridge/SKILL.md` and may be updated without changing the user's short prompt.
