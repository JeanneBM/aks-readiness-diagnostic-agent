package main

import (
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"
)

func setting(key, fallback string) string {
	if value := os.Getenv(key); value != "" { return value }
	return fallback
}

func main() {
	path := setting("READY_PATH", "/ready")
	dependency := setting("DEPENDENCY_URL", "http://dependency:8080/health")
	role := setting("ROLE", "api")
	client := &http.Client{Timeout: time.Second}
	mux := http.NewServeMux()
	mux.HandleFunc("/live", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "alive") })
	if role == "dependency" {
		mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "available") })
	} else {
		mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
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
	slog.Info("starting HTTP server", "address", ":8080", "readiness_path", path, "role", role)
	server := &http.Server{Addr: ":8080", Handler: mux, ReadHeaderTimeout: 3 * time.Second}
	if err := server.ListenAndServe(); err != nil { slog.Error("server stopped", "err", err); os.Exit(1) }
}
