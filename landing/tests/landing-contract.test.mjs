import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const workspaceUrl = "https://workspace.knowledge.kotarou.quest";

async function collectFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await collectFiles(fullPath)));
    else files.push(fullPath);
  }
  return files;
}

test("exports a standalone static Next.js site", async () => {
  const config = await readFile(path.join(root, "next.config.js"), "utf8");
  assert.match(config, /output:\s*["']export["']/);
  assert.doesNotMatch(config, /rewrites|redirects|headers\s*\(/);
});

test("contains exactly three absolute workspace CTAs", async () => {
  const sourceFiles = (await collectFiles(path.join(root, "src"))).filter((file) =>
    /\.(?:ts|tsx|js|jsx)$/.test(file),
  );
  const source = (await Promise.all(sourceFiles.map((file) => readFile(file, "utf8")))).join("\n");
  assert.equal(source.split(`href="${workspaceUrl}"`).length - 1, 3);
  assert.doesNotMatch(source, /href=["']\/workspace(?:\/knowledge)?["']/);
});

test("keeps required knowledge workflow language and removes public-project residue", async () => {
  const sourceFiles = await collectFiles(path.join(root, "src"));
  const source = (await Promise.all(sourceFiles.map((file) => readFile(file, "utf8")))).join("\n");
  for (const phrase of ["来源摄取", "证据归档", "知识版本", "冲突检查", "Artifact", "Approval Flow"]) {
    assert.match(source, new RegExp(phrase));
  }
  for (const residue of ["DeerFlow", "Portfolio", "GitHub", "Star on GitHub", "Join the Community", "Blog", "Docs", "Community"]) {
    assert.doesNotMatch(source, new RegExp(residue, "i"));
  }
  assert.match(source, /© 2026/);
});

test("has no live backend or request-scoped runtime dependency", async () => {
  const sourceFiles = await collectFiles(path.join(root, "src"));
  const source = (await Promise.all(sourceFiles.map((file) => readFile(file, "utf8")))).join("\n");
  assert.doesNotMatch(source, /next\/headers|cookies\(|headers\(|\/api\/|localhost|127\.0\.0\.1|fetch\(|EventSource|WebSocket/);
});
