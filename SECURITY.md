# Security

Offline Bridge downloads untrusted external content. Packaging must not be confused with trust.

- Repository code is cloned but not executed.
- Python uses wheels only by default to avoid source-build hooks.
- pnpm uses `pnpm fetch`, which does not run project lifecycle scripts.
- URL downloads require HTTPS and reject non-public network destinations.
- Tokens belong only in GitHub Actions secrets.
- Every part, reconstructed archive, and extracted file is verified with SHA-256.
- Extraction rejects absolute paths, traversal paths, unsafe links, device files, and FIFOs.
- Transient request pull requests should be closed without merging.
