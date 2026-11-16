# Go log provenance

go-default-startup.log is the exact startup line supplied from a real execution during the 26 October 2026 review. It captures the previous default slog format and is retained as a backward-compatibility regression case.

It is not a fabricated TextHandler output, nor evidence that the current binary ran locally during implementation.

go-text-handler.log and go-json-handler.log, with their .provenance.json files, are the unmodified stdout bytes of the current lab/go/main.go, compiled and run natively by tools/capture_go_logs.py on 16 November 2026 (text handler, then LOG_FORMAT=json). The actual application returned 200 for liveness, 503 for a real failed dependency connection and 404 for an unknown route. Source and log hashes are checked by the regression test. Ephemeral loopback ports are preserved; these are no-secret local test values.

This capture was made on a development machine, not retrieved from CI; the provenance files name the earlier CI capture (run 40381715977, artifact 12679415721, commit 6d77333e) that it supersedes. The native-go CI job regenerates both captures from the committed source on every push, so a CI-sourced replacement can be committed whenever one is preferred.

tools/capture_go_logs.py builds and starts the current application, requests real HTTP responses and records its actual stdout/stderr plus source hashes. The native-go CI job uses that capture to check both baseline diagnosis and recorder evidence selection. Generated logs are kept as CI artifacts; no expected line is manually substituted.
