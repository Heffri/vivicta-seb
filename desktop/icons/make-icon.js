'use strict'
// Generates icon.ico: a placeholder mark ("AR" in a 5x7 dot-matrix font on a dark rounded
// square, accent-blue letters) using only Node built-ins (zlib for PNG's DEFLATE stream, a
// hand-rolled CRC32) so this one static asset doesn't need an image-library dependency.
// Regenerate with: node icons/make-icon.js (run from desktop/)
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')

const SIZE = 256
const RADIUS = 46
const BG = [0x13, 0x18, 0x30, 255] // docs/acrylic/DESIGN.md dark --wallpaper mid-stop
const FG = [0x7a, 0xa2, 0xf7, 255] // docs/acrylic/DESIGN.md dark accent (#7aa2f7)

const GLYPH_A = ['01110', '10001', '10001', '11111', '10001', '10001', '10001']
const GLYPH_R = ['11110', '10001', '10001', '11110', '10100', '10010', '10001']

function buildPixels() {
  const pixels = new Uint8Array(SIZE * SIZE * 4)
  const SUB = 2 // 2x2 supersampling, for an antialiased rounded-square silhouette

  function insideRoundedRect(x, y) {
    const cx = Math.min(Math.max(x, RADIUS), SIZE - RADIUS)
    const cy = Math.min(Math.max(y, RADIUS), SIZE - RADIUS)
    const dx = x - cx
    const dy = y - cy
    return dx * dx + dy * dy <= RADIUS * RADIUS
  }

  const scale = 20
  const glyphWidth = 11 * scale // 5 + 1-column gap + 5
  const glyphHeight = 7 * scale
  const originX = (SIZE - glyphWidth) / 2
  const originY = (SIZE - glyphHeight) / 2

  function glyphOn(x, y) {
    if (x < originX || y < originY) return false
    const gx = Math.floor((x - originX) / scale)
    const gy = Math.floor((y - originY) / scale)
    if (gy < 0 || gy >= 7) return false
    if (gx >= 0 && gx < 5) return GLYPH_A[gy][gx] === '1'
    if (gx >= 6 && gx < 11) return GLYPH_R[gy][gx - 6] === '1'
    return false
  }

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      let coverage = 0
      for (let sy = 0; sy < SUB; sy++) {
        for (let sx = 0; sx < SUB; sx++) {
          if (insideRoundedRect(x + (sx + 0.5) / SUB, y + (sy + 0.5) / SUB)) coverage++
        }
      }
      const alpha = coverage / (SUB * SUB)
      if (alpha === 0) continue
      const useFg = glyphOn(x + 0.5, y + 0.5)
      const [r, g, b, a] = useFg ? FG : BG
      const idx = (y * SIZE + x) * 4
      pixels[idx] = r
      pixels[idx + 1] = g
      pixels[idx + 2] = b
      pixels[idx + 3] = Math.round(a * alpha)
    }
  }
  return pixels
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function pngChunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii')
  const lenBuf = Buffer.alloc(4)
  lenBuf.writeUInt32BE(data.length, 0)
  const crcBuf = Buffer.alloc(4)
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0)
  return Buffer.concat([lenBuf, typeBuf, data, crcBuf])
}

function encodePng(pixels, size) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type: truecolor + alpha

  const stride = size * 4
  const pixelBuf = Buffer.from(pixels.buffer, pixels.byteOffset, pixels.byteLength)
  const raw = Buffer.alloc((stride + 1) * size)
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0 // per-row filter type "none"
    pixelBuf.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride)
  }
  const idat = zlib.deflateSync(raw, { level: 9 })

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', idat),
    pngChunk('IEND', Buffer.alloc(0)),
  ])
}

function encodeIco(pngBuffer, size) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(1, 4)

  const entry = Buffer.alloc(16)
  entry[0] = size >= 256 ? 0 : size
  entry[1] = size >= 256 ? 0 : size
  entry.writeUInt16LE(1, 4) // planes
  entry.writeUInt16LE(32, 6) // bit count
  entry.writeUInt32LE(pngBuffer.length, 8)
  entry.writeUInt32LE(22, 12) // offset: 6-byte header + 16-byte entry

  return Buffer.concat([header, entry, pngBuffer])
}

const pixels = buildPixels()
const png = encodePng(pixels, SIZE)
const ico = encodeIco(png, SIZE)
fs.writeFileSync(path.join(__dirname, 'icon.ico'), ico)
fs.writeFileSync(path.join(__dirname, 'icon.png'), png)
console.log(`wrote ${path.join(__dirname, 'icon.ico')} (${ico.length} bytes) and icon.png (${png.length} bytes)`)
