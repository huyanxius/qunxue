import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = path.join(frontendRoot, 'src')
const appRoot = path.join(sourceRoot, 'app')
const modulesRoot = path.join(sourceRoot, 'modules')
const generatedApiRoot = path.join(sourceRoot, 'api', 'generated')
const generatedImporterAllowlist = new Set([
  path.join(sourceRoot, 'api', 'client.ts'),
  path.join(sourceRoot, 'api', 'system.ts'),
  path.join(
    modulesRoot,
    'socio-match-workspace',
    'researchTaskApi.ts',
  ),
])
const bareFetchAllowlist = new Set([
  path.join(sourceRoot, 'api', 'client.ts'),
])
const allowedDependencies = new Map([
  ['knowledge-explorer', new Set()],
  ['socio-match-workspace', new Set()],
])

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const target = path.join(directory, entry.name)
      if (entry.isDirectory()) return sourceFiles(target)
      return /\.(ts|tsx)$/.test(entry.name) ? [target] : []
    }),
  )
  return nested.flat()
}

function isWithin(directory, target) {
  const relative = path.relative(directory, target)
  return (
    relative === '' ||
    (!relative.startsWith('..') && !path.isAbsolute(relative))
  )
}

function moduleNameFor(filePath) {
  if (!isWithin(modulesRoot, filePath)) return undefined
  return path.relative(modulesRoot, filePath).split(path.sep)[0]
}

function importedSpecifiers(source) {
  const specifiers = new Set()
  const patterns = [
    /\b(?:import|export)\s+(?:type\s+)?(?:[^;'"]*?\s+from\s+)?['"]([^'"]+)['"]/g,
    /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
    /\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)/g,
  ]

  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) {
      specifiers.add(match[1])
    }
  }
  return specifiers
}

function resolveSourceImport(sourcePath, specifier) {
  if (specifier.startsWith('.')) {
    return path.resolve(path.dirname(sourcePath), specifier)
  }
  if (specifier.startsWith('@/')) {
    return path.join(sourceRoot, specifier.slice(2))
  }
  if (specifier.startsWith('src/')) {
    return path.join(frontendRoot, specifier)
  }
  return undefined
}

const violations = []
for (const sourcePath of await sourceFiles(sourceRoot)) {
  const sourceModule = moduleNameFor(sourcePath)
  const source = await readFile(sourcePath, 'utf8')

  if (
    /\b(?:(?:globalThis|window)\.)?fetch\s*\(/.test(source) &&
    !isWithin(generatedApiRoot, sourcePath) &&
    !bareFetchAllowlist.has(sourcePath)
  ) {
    violations.push(
      `${path.relative(sourceRoot, sourcePath)} calls fetch outside the transport adapter`,
    )
  }

  for (const specifier of importedSpecifiers(source)) {
    const resolved = resolveSourceImport(sourcePath, specifier)
    if (!resolved) continue
    const targetModule = moduleNameFor(resolved)

    if (sourceModule && isWithin(appRoot, resolved)) {
      violations.push(`${path.relative(sourceRoot, sourcePath)} imports app code`)
    }

    if (
      isWithin(generatedApiRoot, resolved) &&
      !isWithin(generatedApiRoot, sourcePath) &&
      !generatedImporterAllowlist.has(sourcePath)
    ) {
      violations.push(
        `${path.relative(sourceRoot, sourcePath)} imports generated API outside an approved adapter`,
      )
    }

    if (!targetModule || sourceModule === targetModule) continue

    if (
      sourceModule &&
      !allowedDependencies.get(sourceModule)?.has(targetModule)
    ) {
      violations.push(`${sourceModule} cannot depend on ${targetModule}`)
    }
    if (resolved !== path.join(modulesRoot, targetModule)) {
      violations.push(
        `${path.relative(sourceRoot, sourcePath)} bypasses ${targetModule}/index.ts`,
      )
    }
  }
}

for (const moduleName of allowedDependencies.keys()) {
  const publicEntry = path.join(modulesRoot, moduleName, 'index.ts')
  try {
    await readFile(publicEntry, 'utf8')
  } catch {
    violations.push(`${moduleName} has no public index.ts`)
  }
}

if (violations.length > 0) {
  throw new Error(`Module boundary violations:\n${violations.join('\n')}`)
}

process.stdout.write('Module boundaries: ok\n')
