// Generate TypeScript types from the combined contract JSON Schema.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { compile } from "json-schema-to-typescript";

const [src, out] = process.argv.slice(2);
const schema = JSON.parse(await readFile(src, "utf8"));
const banner = `/* GENERATED from schema/ (Pydantic) by \`make schema\`. Do not edit. schema_version ${schema["x-schema-version"]} */`;
const ts = await compile(schema, "Contract", {
  bannerComment: banner,
  additionalProperties: false,
  unreachableDefinitions: true,
  strictIndexSignatures: true,
  format: true,
});
await mkdir(dirname(out), { recursive: true });
await writeFile(out, ts);
console.log(`wrote ${out}`);
