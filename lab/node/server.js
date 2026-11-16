"use strict";
// Plain Node HTTP service with a real dependency check. No npm packages.
// Its log vocabulary follows common Node conventions and was not shared with
// the rules baseline; see docs/phase-2-protocol.md for what that does and does
// not establish.
const http = require("http");

const port = Number(process.env.PORT || 8080);
const readyPath = process.env.READY_PATH || "/ready";
const dependencyUrl = process.env.DEPENDENCY_URL || "http://dependency:8080/health";
const readyDelayMs = 1000 * Number(process.env.READY_DELAY_SECONDS || 0);

function log(level, message) {
  const line = `${new Date().toISOString()} ${level.padEnd(5)} ${message}`;
  (level === "error" ? console.error : console.log)(line);
}

function checkDependency() {
  return new Promise((resolve) => {
    const request = http.get(dependencyUrl, { timeout: 1000 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200 ? null : `inventory responded with HTTP ${response.statusCode}`);
    });
    request.on("timeout", () => request.destroy(new Error("timeout after 1000ms")));
    request.on("error", (error) => resolve(`inventory unreachable (${error.message})`));
  });
}

const server = http.createServer(async (request, response) => {
  const path = request.url.split("?")[0];
  let status = 404;
  if (path === "/live") {
    status = 200;
  } else if (path === readyPath) {
    if (readyDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, readyDelayMs));
    }
    const failure = await checkDependency();
    if (failure) {
      log("error", `readiness check failed: ${failure}`);
    }
    status = failure ? 503 : 200;
  }
  response.writeHead(status, { "content-type": "text/plain" });
  response.end(status === 200 ? "ok\n" : "not found\n");
  log("info", `${request.method} ${path} -> ${status}`);
});

server.listen(port, "0.0.0.0", () => {
  log("info", `routes mounted: GET /live, GET ${readyPath}`);
  log("info", `server listening on http://0.0.0.0:${server.address().port}`);
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
