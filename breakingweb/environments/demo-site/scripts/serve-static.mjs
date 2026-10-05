#!/usr/bin/env node

import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { createServer } from "node:http";
import { cwd, env } from "node:process";

const rootDir = join(cwd(), "out");
const port = Number(env.PORT || 3000);
const host = env.HOST || "127.0.0.1";

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function safeJoin(pathname) {
  const cleanPath = normalize(decodeURIComponent(pathname)).replace(/^(\.\.(\/|\\|$))+/, "");
  return join(rootDir, cleanPath);
}

function candidatePaths(pathname) {
  const trimmed = pathname.replace(/\/+$/, "") || "/";
  const base = safeJoin(trimmed);

  if (extname(trimmed)) {
    return [base];
  }

  if (trimmed === "/") {
    return [join(rootDir, "index.html")];
  }

  return [
    `${base}.html`,
    join(base, "index.html"),
    base,
  ];
}

function resolveFile(pathname) {
  for (const candidate of candidatePaths(pathname)) {
    if (existsSync(candidate) && statSync(candidate).isFile()) {
      return candidate;
    }
  }

  return null;
}

function sendFile(res, filePath, statusCode = 200) {
  const type = contentTypes[extname(filePath).toLowerCase()] || "application/octet-stream";
  res.writeHead(statusCode, { "Content-Type": type });
  createReadStream(filePath).pipe(res);
}

const server = createServer((req, res) => {
  const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  const filePath = resolveFile(url.pathname);

  if (filePath) {
    sendFile(res, filePath);
    return;
  }

  const notFound = join(rootDir, "404.html");
  if (existsSync(notFound)) {
    sendFile(res, notFound, 404);
    return;
  }

  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Not found");
});

server.on("error", (error) => {
  console.error(`Failed to serve static export on http://${host}:${port}`);
  console.error(error);
  process.exit(1);
});

server.listen(port, host, () => {
  console.log(`Serving static export from ${rootDir} at http://${host}:${port}`);
});
