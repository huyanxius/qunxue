import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { JSDOM } from 'jsdom'

// The audited 1,203,987 B leaves about 0.5% for compression differences on Node 22.
const maxBytes = 1_210_000
const dist = new URL('../dist/', import.meta.url)
const html = readFileSync(new URL('index.html', dist), 'utf8')
const origin = 'https://bundle.invalid'
const { document } = new JSDOM(html, { url: origin }).window
const references = document.querySelectorAll('script[src], link[href]')
const assets = Array.from(references, (element) => new URL(element.src ?? element.href))
  .filter((url) => /\.(?:js|css)$/.test(url.pathname))
assert(assets.length > 0, 'No initial JS or CSS references found in dist/index.html')

let bytes = 0
for (const asset of assets) {
  assert.equal(asset.origin, origin, 'Initial asset is missing from the local build')
  bytes += gzipSync(readFileSync(new URL(`.${asset.pathname}`, dist))).length
}
console.log(
  `Initial JS/CSS gzip: ${bytes} B (limit ${maxBytes} B, ${assets.length} references, `
  + `Node ${process.versions.node}, zlib ${process.versions.zlib})`,
)
assert(bytes <= maxBytes, `Initial JS/CSS exceeds the gzip budget by ${bytes - maxBytes} B`)
