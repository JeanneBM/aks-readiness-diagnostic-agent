# Go log provenance

go-default-startup.log is the exact startup line supplied from a real execution during the 26 October 2026 review. It captures the previous default slog format and is retained as a backward-compatibility regression case.

It is not a fabricated TextHandler output, nor evidence that the current binary ran locally during implementation.

tools/capture_go_logs.py builds and starts the current application, requests real HTTP responses and records its actual stdout/stderr plus source hashes. The native-go CI job uses that capture to check both baseline diagnosis and recorder evidence selection. Generated logs are kept as CI artifacts; no expected line is manually substituted.
