#!/usr/bin/env node
// docs:sync — keep generated documentation inputs in step with their sources.
//
// Copies (never fails when a source is absent, so an early clone still builds):
//   packages/core-ir/schema/system_ir.schema.json → docs/public/schema/system_ir.schema.json
//   PLAN.md                                       → docs/plan/master.md
//   PLAN.md §10 status board                      → docs/plan/status.md
//   packages|plugins|apps/*/README.md             → docs/reference/packages/<name>.md
//   and a docs/reference/packages/index.md listing.
//
// Generated files are gitignored via docs/.gitignore.

import { existsSync } from "node:fs";
import { copyFile, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const docsDir = resolve(__dirname, "..");
const root = resolve(docsDir, "..");
const REPO = "https://github.com/dtmirizzi/atomc";

const log = (msg) => process.stdout.write(`[docs:sync] ${msg}\n`);

function frontmatter(title, extra = "") {
  return `---\ntitle: ${JSON.stringify(title)}\n${extra}---\n\n`;
}

// 1. IR JSON Schema ---------------------------------------------------------
async function syncSchema() {
  const src = join(root, "packages", "core-ir", "schema", "system_ir.schema.json");
  const destDir = join(docsDir, "public", "schema");
  const dest = join(destDir, "system_ir.schema.json");
  if (!existsSync(src)) {
    log(
      "no packages/core-ir/schema/system_ir.schema.json yet — schema browser will use placeholder",
    );
    return;
  }
  await mkdir(destDir, { recursive: true });
  await copyFile(src, dest);
  log(`copied IR schema → ${relative(root, dest)}`);
}

// 2. PLAN.md → plan/master.md + plan/status.md ------------------------------
// VitePress compiles markdown as a Vue template. Raw `<tag>`-looking text outside code
// spans/fences (e.g. "WP-<phase>.<n>") would be parsed as an unclosed HTML element, so escape it.
function neutralizeVueTags(md) {
  const lines = md.split("\n");
  let inFence = false;
  return lines
    .map((line) => {
      if (/^\s*(```|~~~)/.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) {
        return line;
      }
      let out = "";
      let inCode = false;
      for (let i = 0; i < line.length; ) {
        const char = line[i];
        if (char === "`") {
          inCode = !inCode;
          out += char;
          i += 1;
          continue;
        }
        if (!inCode && char === "<") {
          const match = /^<([A-Za-z][A-Za-z0-9_-]*)>/.exec(line.slice(i));
          if (match) {
            out += `&lt;${match[1]}&gt;`;
            i += match[0].length;
            continue;
          }
        }
        out += char;
        i += 1;
      }
      return out;
    })
    .join("\n");
}

function extractStatusBoard(plan) {
  const marker = /^##\s+10\.\s+Status board\s*$/m;
  const match = marker.exec(plan);
  if (!match) {
    return null;
  }
  const rest = plan.slice(match.index + match[0].length);
  const end = rest.search(/^##\s+11\./m);
  return (end === -1 ? rest : rest.slice(0, end)).trim();
}

async function syncPlan() {
  const planPath = join(root, "PLAN.md");
  if (!existsSync(planPath)) {
    log("PLAN.md not found — skipping");
    return;
  }
  const plan = await readFile(planPath, "utf8");

  const masterHeader = frontmatter("Master plan", "editLink: false\noutline: [2, 3]\n");
  const masterNote =
    "> This page is generated from [`PLAN.md`](" +
    `${REPO}/blob/main/PLAN.md) by \`pnpm --filter @atomc/docs sync\` and is gitignored.\n` +
    "> Do not edit it here.\n\n";
  await writeFile(
    join(docsDir, "plan", "master.md"),
    masterHeader + masterNote + neutralizeVueTags(plan),
    "utf8",
  );
  log("generated docs/plan/master.md from PLAN.md");

  const board = extractStatusBoard(plan);
  if (!board) {
    log("could not locate PLAN.md §10 status board — skipping status page body");
    return;
  }
  const statusHeader = frontmatter("Work-package status", "editLink: false\n");
  const statusBody =
    "> Generated from [`PLAN.md`](" +
    `${REPO}/blob/main/PLAN.md) §10 by \`pnpm --filter @atomc/docs sync\`.\n` +
    "> The source of truth is the plan; this page is a mirror.\n\n" +
    "## Status board\n\n" +
    neutralizeVueTags(board) +
    "\n\n## Phase gate\n\n" +
    "A phase is complete when all of its work packages are merged, `ci.yml` is green on " +
    "`main`, the phase docs page is published, `PLAN.md` is updated, and a `v0.<phase>.0` " +
    "pre-release tag is cut.\n";
  await writeFile(join(docsDir, "plan", "status.md"), statusHeader + statusBody, "utf8");
  log("generated docs/plan/status.md from PLAN.md §10");
}

// 3. package READMEs → reference/packages/ ----------------------------------
const PACKAGE_PARENTS = ["packages", "plugins", "apps"];

function rewriteLinks(md) {
  // Relative markdown links to repo files resolve against GitHub rather than the docs tree.
  return md.replace(/\]\((\.\.?\/[^)]+)\)/g, (_m, target) => {
    const clean = target.replace(/^\.\.?\//, "").replace(/^\.\//, "");
    return `](${REPO}/blob/main/${clean})`;
  });
}

function firstHeading(md, fallback) {
  const match = /^#\s+(.+)$/m.exec(md);
  return match ? match[1].trim() : fallback;
}

async function syncPackages() {
  const destDir = join(docsDir, "reference", "packages");
  await rm(destDir, { recursive: true, force: true });
  await mkdir(destDir, { recursive: true });

  const indexRows = [];
  for (const parent of PACKAGE_PARENTS) {
    const parentDir = join(root, parent);
    if (!existsSync(parentDir)) {
      continue;
    }
    const entries = await readdir(parentDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) {
        continue;
      }
      const name = entry.name;
      const readme = join(parentDir, name, "README.md");
      if (!existsSync(readme)) {
        continue;
      }
      const raw = await readFile(readme, "utf8");
      const title = firstHeading(raw, name);
      const slug = `${parent.replace(/s$/, "")}-${name}`.replace(/[^a-z0-9-]/gi, "-").toLowerCase();
      const header = frontmatter(
        title,
        `editLink: ${REPO}/blob/main/${parent}/${name}/README.md\n`,
      );
      const linkNote = `> Mirrored from [\`${parent}/${name}/README.md\`](${REPO}/blob/main/${parent}/${name}/README.md).\n\n`;
      await writeFile(join(destDir, `${slug}.md`), header + linkNote + rewriteLinks(raw), "utf8");
      indexRows.push(`| \`${parent}/${name}\` | [${title}](./${slug}) |`);
      log(`mirrored ${parent}/${name}/README.md`);
    }
  }

  const indexHeader = frontmatter("Packages", "editLink: false\n");
  const indexBody =
    "# Packages\n\n" +
    "READMEs of every workspace under `packages/`, `plugins/` and `apps/`, mirrored here by " +
    "`pnpm --filter @atomc/docs sync` so the docs never drift from the source.\n\n" +
    (indexRows.length
      ? `| Workspace | README |\n| --- | --- |\n${indexRows.join("\n")}\n`
      : "_No workspace READMEs found yet — packages land in Phase 1._\n");
  await writeFile(join(destDir, "index.md"), indexHeader + indexBody, "utf8");
  log(`wrote reference/packages/index.md (${indexRows.length} packages)`);
}

async function main() {
  await syncSchema();
  await syncPlan();
  await syncPackages();
  log("done");
}

main().catch((err) => {
  console.error(`[docs:sync] failed: ${err?.stack ?? err}`);
  process.exitCode = 1;
});
