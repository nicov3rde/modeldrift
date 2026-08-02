// One-off asset generation: favicon.ico and the default OG share image.
// Run with: node scripts/generate-images.mjs
// Not part of the build — output is committed to public/.
import sharp from 'sharp';
import { writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(root, '..', 'public');

async function makeFavicon() {
  const svg = await readFile(path.join(publicDir, 'favicon.svg'));
  const sizes = [16, 32, 48];
  const pngBuffers = await Promise.all(
    sizes.map((size) => sharp(svg, { density: 384 }).resize(size, size).png().toBuffer())
  );

  // Minimal ICO container holding PNG-encoded frames (supported by all
  // modern browsers), so we don't need a native ICO encoder dependency.
  const headerSize = 6;
  const dirEntrySize = 16;
  const offsets = [];
  let offset = headerSize + dirEntrySize * sizes.length;
  for (const buf of pngBuffers) {
    offsets.push(offset);
    offset += buf.length;
  }

  const header = Buffer.alloc(headerSize);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(sizes.length, 4);

  const dirEntries = sizes.map((size, i) => {
    const entry = Buffer.alloc(dirEntrySize);
    entry.writeUInt8(size === 256 ? 0 : size, 0);
    entry.writeUInt8(size === 256 ? 0 : size, 1);
    entry.writeUInt8(0, 2);
    entry.writeUInt8(0, 3);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(pngBuffers[i].length, 8);
    entry.writeUInt32LE(offsets[i], 12);
    return entry;
  });

  const ico = Buffer.concat([header, ...dirEntries, ...pngBuffers]);
  await writeFile(path.join(publicDir, 'favicon.ico'), ico);
  console.log('wrote favicon.ico');
}

async function makeOgImage() {
  const width = 1200;
  const height = 630;
  const unit = 45;
  let rules = '';
  for (let y = unit * 2; y < height - unit; y += unit) {
    rules += `<line x1="120" y1="${y}" x2="${width - 60}" y2="${y}" stroke="#c9d6ea" stroke-width="2" />`;
  }

  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <rect width="${width}" height="${height}" fill="#fbfbf9" />
    <line x1="90" y1="0" x2="90" y2="${height}" stroke="#d6635a" stroke-width="3" opacity="0.55" />
    ${rules}
    <text x="120" y="200" font-family="Georgia, 'Times New Roman', serif" font-size="88" fill="#23241f">ModelDrift</text>
    <text x="120" y="260" font-family="Georgia, serif" font-size="30" fill="#4b4c44">What AI answer engines say about software brands</text>
    <text x="120" y="${height - 90}" font-family="Georgia, serif" font-size="26" fill="#75766c">Presence · Accuracy · Sourcing</text>
    <text x="120" y="${height - 50}" font-family="Courier New, monospace" font-size="22" fill="#75766c">modeldrift.tech</text>
  </svg>`;

  await sharp(Buffer.from(svg)).png().toFile(path.join(publicDir, 'og-default.png'));
  console.log('wrote og-default.png');
}

await makeFavicon();
await makeOgImage();
