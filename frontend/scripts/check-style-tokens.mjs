import { globSync, readFileSync } from 'node:fs'
import { relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ident, tokenize, tokenTypes } from 'css-tree'
import postcss from 'postcss'
import baseline from './frontend-check-baseline.json' with { type: 'json' }

const scriptPath = fileURLToPath(import.meta.url)
const sourceRoot = fileURLToPath(new URL('../src/', import.meta.url))
const workbench = resolve(sourceRoot, 'app/research-workspace/research-document-workbench.css')
const tailwindTheme = fileURLToPath(import.meta.resolve('tailwindcss/theme.css'))

// The legacy literal checks apply to the migrated workbench stylesheet.
const structuralChecks = [
  { label: 'raw type size', property: /^font-size$/, allowed: /^(?:var\(|inherit$)/ },
  { label: 'raw radius', property: /^border-radius$/, allowed: /^(?:var\(|50%$|999px$|99px$)/ },
  {
    label: 'raw control size',
    property: /^(?:min-)?height$/,
    allowed: /^(?!(?:1\.8rem|1\.9rem|2rem|2\.25rem|32px|36px)$)/,
  },
]

const parseFile = (file) => postcss.parse(readFileSync(file, 'utf8'), { from: file })

function definedProperties(roots) {
  const defined = new Set()
  for (const root of roots) {
    root.walkDecls((declaration) => {
      const name = ident.decode(declaration.prop)
      if (name.startsWith('--')) defined.add(name)
    })
    root.walkAtRules('property', (rule) => defined.add(ident.decode(rule.params.trim())))
  }
  return defined
}

function missingVariables(value, defined) {
  const tokens = []
  tokenize(value, (type, start, end) => {
    if (type !== tokenTypes.WhiteSpace && type !== tokenTypes.Comment) {
      tokens.push({ type, text: value.slice(start, end) })
    }
  })

  const missing = []
  for (const [index, token] of tokens.entries()) {
    if (token.type !== tokenTypes.Function || ident.decode(token.text.slice(0, -1)).toLowerCase() !== 'var') continue
    const nameToken = tokens[index + 1]
    // A comma introduces a fallback, including the valid empty fallback in var(--name,).
    // An unresolved var() inside that fallback is checked independently.
    if (nameToken?.type !== tokenTypes.Ident || tokens[index + 2]?.type !== tokenTypes.RightParenthesis) continue
    const name = ident.decode(nameToken.text)
    if (name.startsWith('--') && !defined.has(name)) missing.push(name)
  }
  return missing
}

export function findStyleViolations(
  files = globSync('**/*.css', { cwd: sourceRoot }).sort().map((file) => resolve(sourceRoot, file)),
  { structuralFiles = [workbench], definitionFiles = [tailwindTheme], relativeTo = sourceRoot } = {},
) {
  const roots = files.map(parseFile)
  const defined = definedProperties([...roots, ...definitionFiles.map(parseFile)])
  const violations = []
  for (const root of roots) {
    const file = root.source.input.file
    const displayPath = relative(relativeTo, file).split(sep).join('/')
    root.walkDecls((declaration) => {
      const context = declaration.parent.type === 'rule'
        ? declaration.parent.selector.replace(/\s+/g, ' ')
        : `@${declaration.parent.name} ${declaration.parent.params}`.trim()
      const report = (reason) => violations.push({
        key: `${displayPath} | ${context} | ${declaration.prop} | ${reason}`,
        message: `${displayPath}:${declaration.source.start.line} ${reason} (${declaration.prop})`,
      })

      for (const variable of missingVariables(declaration.value, defined)) {
        report(`undefined custom property ${variable}`)
      }
      if (structuralFiles.includes(file)) {
        for (const check of structuralChecks) {
          if (check.property.test(declaration.prop) && !check.allowed.test(declaration.value)) {
            report(`${check.label}: ${declaration.value}`)
          }
        }
      }
    })
  }
  return violations
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  const files = process.argv.slice(2).map((file) => resolve(file))
  const project = files.length === 0
  const violations = project
    ? findStyleViolations()
    : findStyleViolations(files, { structuralFiles: files, definitionFiles: [], relativeTo: process.cwd() })
  const existing = project ? [...baseline.styleTokens] : []
  const failures = []
  for (const { key, message } of violations) {
    const index = existing.indexOf(key)
    if (index === -1) failures.push(message)
    else existing.splice(index, 1)
  }

  if (failures.length) {
    console.error(failures.join('\n'))
    process.exitCode = 1
  } else {
    console.log('Style tokens: ok')
  }
}

