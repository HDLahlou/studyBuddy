// Emit SCHEMA_VERSION constants for TypeScript and Dart from the contract schema.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const [src, tsOut, dartOut] = process.argv.slice(2);
const version = JSON.parse(await readFile(src, "utf8"))["x-schema-version"];
if (!/^\d+\.\d+$/.test(version)) throw new Error(`bad x-schema-version: ${version}`);
const banner = "GENERATED from schema/ (Pydantic) by `make schema`. Do not edit.";
const files = {
  [tsOut]: `/* ${banner} */\nexport const SCHEMA_VERSION = "${version}";\n`,
  [dartOut]: `// ${banner}\nconst String schemaVersion = '${version}';\n`,
};
for (const [path, text] of Object.entries(files)) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, text);
  console.log(`wrote ${path}`);
}
