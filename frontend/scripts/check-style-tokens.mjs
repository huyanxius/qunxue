import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/*
 * 这个检查只约束结构：字阶、控件高度和圆角。页面 shader、数据色和局部氛围色
 * 不属于它的管辖范围，避免把不同页面强行涂成同一种颜色。
 */
const files = process.argv.slice(2).map((file) => resolve(file))

if (files.length === 0) {
  console.error('Usage: node scripts/check-style-tokens.mjs <migrated.css> [...]')
  process.exit(2)
}

const checks = [
  { label: 'raw type size', pattern: /font-size\s*:\s*([^;}]+)/g, allowed: /^(?:var\(|inherit$)/ },
  { label: 'raw radius', pattern: /border-radius\s*:\s*([^;}]+)/g, allowed: /^(?:var\(|50%$|999px$|99px$)/ },
  {
    label: 'raw control size',
    pattern: /(?:^|[;{]\s*)((?:min-)?height)\s*:\s*([^;}]+)/gm,
    valueIndex: 2,
    allowed: /^(?!(?:1\.8rem|1\.9rem|2rem|2\.25rem|32px|36px)$)/,
  },
]

const failures = []
for (const file of files) {
  const source = readFileSync(file, 'utf8')
  for (const check of checks) {
    for (const match of source.matchAll(check.pattern)) {
      const value = match[check.valueIndex ?? 1].trim()
      if (check.allowed.test(value)) continue
      const line = source.slice(0, match.index).split('\n').length
      failures.push(`${file}:${line} ${check.label}: ${match[0].trim()}`)
    }
  }
}

if (failures.length > 0) {
  console.error(failures.join('\n'))
  process.exit(1)
}

console.log('Style tokens: ok')

