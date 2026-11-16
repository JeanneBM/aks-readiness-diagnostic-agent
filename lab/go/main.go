package main

import (
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"time"
)

func setting(key, fallback string) string {
	if value := os.Getenv(key); value != "" { return value }
	return fallback
}

// handler keeps the development text format as the default. LOG_FORMAT=json selects
// slog's JSON handler, a common production configuration whose lines carry the same
// fields in a different shape; nothing about the application behaviour changes.
func handler() slog.Handler {
	if setting("LOG_FORMAT", "text") == "json" {
		return slog.NewJSONHandler(os.Stdout, nil)
	}
	return slog.NewTextHandler(os.Stdout, nil)
}

func main() {
	slog.SetDefault(slog.New(handler()))
	address := ":" + setting("PORT", "8080")
	path := setting("READY_PATH", "/ready")
	dependency := setting("DEPENDENCY_URL", "http://dependency:8080/health")
	role := setting("ROLE", "api")
	// READY_DELAY_SECONDS holds every readiness response for a fixed time. With a probe
	// timeout shorter than the delay the kubelet reports a deadline error that the
	// diagnostic taxonomy does not cover; the lab uses this as an abstention control.
	delay, _ := strconv.Atoi(setting("READY_DELAY_SECONDS", "0"))
	client := &http.Client{Timeout: time.Second}
	mux := http.NewServeMux()
	mux.HandleFunc("/live", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "alive") })
	if role == "dependency" {
		mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "available") })
	} else {
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
			if delay > 0 {
				time.Sleep(time.Duration(delay) * time.Second)
			}
			response, err := client.Get(dependency)
			if err != nil {
				slog.Error("dependency check failed", "dependency", "inventory", "err", err)
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			defer response.Body.Close()
			if response.StatusCode != http.StatusOK {
				slog.Error("dependency check failed", "dependency", "inventory", "status", response.StatusCode)
				w.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			fmt.Fprintln(w, "ready")
		})
	}
	slog.Info("starting HTTP server", "address", address, "readiness_path", path, "role", role)
	server := &http.Server{Addr: address, Handler: mux, ReadHeaderTimeout: 3 * time.Second}
	if err := server.ListenAndServe(); err != nil { slog.Error("server stopped", "err", err); os.Exit(1) }
}
