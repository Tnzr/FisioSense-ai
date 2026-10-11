// Download the quantized ONNX heads + manifest into desktop/models and verify
// sha256 against the manifest. Run after each model release.
//
//   node scripts/fetch-models.mjs [--base https://.../models] [--dir models]
import { createHash } from "node:crypto";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const arg = (name, def) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
};
const BASE = arg("--base", process.env.ASCULTO_MODELS_BASE || "");
const DIR = path.resolve(arg("--dir", "models"));

async function sha256(buf) {
  return createHash("sha256").update(buf).digest("hex");
}

async function fetchTo(url, dest) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  await writeFile(dest, buf);
  return buf;
}

async function main() {
  if (!BASE) throw new Error("set --base or ASCULTO_MODELS_BASE");
  await mkdir(DIR, { recursive: true });
  const manifestUrl = `${BASE.replace(/\/$/, "")}/onnx_manifest.json`;
  const manifestBuf = await fetchTo(manifestUrl, path.join(DIR, "onnx_manifest.json"));
  const manifest = JSON.parse(manifestBuf.toString("utf8"));

  for (const head of manifest.heads) {
    const { file, sha256: want } = head.served;
    const dest = path.join(DIR, file);
    if (existsSync(dest)) {
      const got = await sha256(await readFile(dest));
      if (got === want) {
        console.log(`ok  ${file}`);
        continue;
      }
    }
    const buf = await fetchTo(`${BASE.replace(/\/$/, "")}/${file}`, dest);
    const got = await sha256(buf);
    if (got !== want) throw new Error(`checksum mismatch for ${file}`);
    console.log(`new ${file} (${(buf.length / 1e6).toFixed(2)} MB)`);
  }
  console.log("models ready in", DIR);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
