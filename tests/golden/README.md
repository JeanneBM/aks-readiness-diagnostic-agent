# Go log provenance

go-default-startup.log is the exact startup line supplied from a real execution during the 26 October 2026 review. It captures the previous default slog format and is retained as a backward-compatibility regression case.

It is not a fabricated TextHandler output, nor evidence that the current binary ran locally during implementation.

go-text-handler.log and go-text-handler.provenance.json are the unmodified log bytes and capture metadata retrieved from native-go CI run 40381715977, artifact 12679415721, for commit 6d77333ea858eb3085ba7cefbe49285cc16e8815. The actual application returned 200 for liveness, 503 for a real failed dependency connection and 404 for an unknown route. Source and log hashes are checked by the regression test. Ephemeral loopback ports are preserved; these are no-secret local test values.

tools/capture_go_logs.py builds and starts the current application, requests real HTTP responses and records its actual stdout/stderr plus source hashes. The native-go CI job uses that capture to check both baseline diagnosis and recorder evidence selection. Generated logs are kept as CI artifacts; no expected line is manually substituted.
