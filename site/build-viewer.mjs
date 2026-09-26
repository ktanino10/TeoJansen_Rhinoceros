import { build } from "esbuild";
import path from "node:path";
import { copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const site = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(process.argv[2] || path.join(site, "dist/TeoJansen_Rhinoceros"));
if (!output.startsWith(`${path.join(site, "dist")}${path.sep}`)) {
  throw new Error("Viewer output must be a named child of site/dist");
}
await build({
  entryPoints: [path.join(site, "viewer.js")],
  outfile: path.join(output, "assets/viewer-engine.js"),
  bundle: true,
  minify: true,
  format: "esm",
  target: ["es2022"],
  sourcemap: false,
  legalComments: "inline",
  logLevel: "warning",
});
await copyFile(
  path.join(site, "node_modules/three/LICENSE"),
  path.join(output, "assets/three-LICENSE.txt"),
);
