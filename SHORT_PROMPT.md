# Canonical Short Prompt

Use this at the beginning of another conversation:

> 需要外部资源时，请读取并遵循 `datebdio/offline-bridge/START_HERE.md`。我授权你在该仓库创建、更新和关闭完成任务所需的临时 `bridge/job-*` 分支和 Pull Request；自动完成原始任务，不要让我手动中转文件。

Notes for the assistant:

- This expresses the user's intent for the normal temporary bridge writes.
- It does not override platform-level confirmation prompts or repository permissions.
- If confirmation is still required, ask once for the exact temporary operations, then resume after approval instead of abandoning the task.
