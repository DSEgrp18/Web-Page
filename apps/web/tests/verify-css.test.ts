import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

// Vitest runs from apps/web; under jsdom `import.meta.url` is not a file URL.
const script = resolve("scripts/verify-css.mjs");
const dirs: string[] = [];

/** Run the check over a throwaway `src/` holding these files. */
function check(files: Record<string, string>) {
  const root = mkdtempSync(join(tmpdir(), "verify-css-"));
  dirs.push(root);
  for (const [name, text] of Object.entries(files)) {
    const path = join(root, "src", name);
    mkdirSync(join(path, ".."), { recursive: true });
    writeFileSync(path, text);
  }
  const run = spawnSync(process.execPath, [script, root], { encoding: "utf8" });
  return { status: run.status, output: run.stdout + run.stderr };
}

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

const tokens = ":root {\n  --ink: #102;\n  --s4: 1rem;\n}\n";

describe("verify-css", () => {
  it("passes when every property and class resolves", () => {
    const result = check({
      "app/globals.css": `${tokens}.btn { color: var(--ink); padding: var(--s4); }\n`,
      "components/A.tsx": `export const A = () => <button className="btn">x</button>;\n`,
    });
    expect(result.output).toContain("verify-css:");
    expect(result.status).toBe(0);
  });

  it("fails on a custom property nothing defines", () => {
    const result = check({
      "app/globals.css": `${tokens}.btn { gap: var(--space-4); }\n`,
    });
    expect(result.status).toBe(1);
    expect(result.output).toContain("var(--space-4) is never defined");
  });

  it("fails on a class with no rule, in a string or an expression", () => {
    const result = check({
      "app/globals.css": `${tokens}.btn { color: var(--ink); }\n`,
      "components/A.tsx": [
        `export const A = () => <dialog className="confirm-dialog" />;`,
        `export const B = (on: boolean) => <p className={on ? "btn" : "danger"} />;`,
        "export const C = (x: string) => <p className={`btn row ${x}`} />;",
        "",
      ].join("\n"),
    });
    expect(result.status).toBe(1);
    expect(result.output).toContain('class "confirm-dialog" has no CSS rule');
    expect(result.output).toContain('class "danger" has no CSS rule');
    expect(result.output).toContain('class "row" has no CSS rule');
    expect(result.output).not.toContain('class "btn"');
  });

  it("accepts properties set by next/font and inline styles", () => {
    const result = check({
      "app/globals.css": `${tokens}body { font-family: var(--font-ui); zoom: var(--scale); }\n`,
      "app/layout.tsx": `const f = font({ variable: "--font-ui" });\n`,
      "components/P.tsx": `export const P = () => <p style={{ "--scale": 1 }} />;\n`,
    });
    expect(result.status).toBe(0);
  });

  it("fails on a hex colour outside a :root block", () => {
    const result = check({
      "app/globals.css": `${tokens}@media (prefers-color-scheme: dark) {\n  :root { --ink: #fff; }\n}\ncanvas { background: #ffffff; }\n`,
    });
    expect(result.status).toBe(1);
    expect(result.output).toContain("#ffffff outside a :root block");
    expect(result.output).not.toContain("#fff outside");
  });
});
