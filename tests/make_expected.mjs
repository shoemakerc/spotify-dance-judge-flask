// Writes tests/expected.json: what the browser version's analyzer measures in
// the clip from tests/clip.py. test_analyze.py holds the NumPy port to it.
// Rerun after that analyzer changes (and port the change):
//
//   node tests/make_expected.mjs ../shoemakerc.github.io/src/lib/dance-judge/analyze.ts
//
// Node 22.18 or later runs the TypeScript file as it is.
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const { analyze } = await import(pathToFileURL(resolve(process.argv[2])).href);

// The same whole-number recipe as clip.py. Math.floor matches Python's //.
const SAMPLE_RATE = 22050;
const samples = new Float32Array(SAMPLE_RATE * 10);
let state = 12345;
const noise = () => {
  state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
  return ((state >>> 16) & 0xffff) - 32768;
};
for (let i = 0; i < samples.length; i++) {
  let chord = 0;
  for (const p of [100, 84, 67]) chord += Math.floor(((Math.abs((i % p) * 2 - p) * 2 - p) * 2000) / p);
  const beat = i % 13230;
  const half = i % 6615;
  const hit = beat < 1500 ? Math.floor(Math.floor((noise() * (1500 - beat)) / 1500) / 2) : 0;
  const hat = half < 300 && beat >= 1500 ? Math.floor(Math.floor((noise() * (300 - half)) / 300) / 8) : 0;
  samples[i] = Math.max(-32768, Math.min(32767, chord + hit + hat)) / 32768;
}

const out = new URL("./expected.json", import.meta.url);
writeFileSync(out, JSON.stringify(analyze(samples, SAMPLE_RATE), null, 1) + "\n");
console.log(`Wrote ${out.pathname}`);
