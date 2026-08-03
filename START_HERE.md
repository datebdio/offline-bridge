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

This is the stable entry point. Detailed behavior belongs in `skills/offline-bridge/SKILL.md` and may be updated without changing the user's short prompt.
