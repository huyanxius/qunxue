import { readdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const scriptPath = fileURLToPath(import.meta.url)
const defaultSourceRoot = path.resolve(path.dirname(scriptPath), '../src')

/** Every module is declared, even when it has no dependencies. */
export const defaultBoundaryPolicy = Object.freeze({
  moduleDependencies: Object.freeze({
    account: Object.freeze([]),
    'knowledge-graph': Object.freeze([]),
    'knowledge-explorer': Object.freeze([]),
    'socio-match-workspace': Object.freeze([]),
  }),
  generatedApiAdapters: Object.freeze([
    'api/client.ts',
    'api/system.ts',
    'modules/account/accountApi.ts',
    'modules/knowledge-graph/knowledgeGraphAdapter.ts',
    'modules/knowledge-explorer/knowledgeApi.ts',
    'modules/socio-match-workspace/researchTaskApi.ts',
  ]),
  moduleApiAdapters: Object.freeze([
    'modules/account/accountApi.ts',
    'modules/knowledge-explorer/knowledgeApi.ts',
    'modules/socio-match-workspace/researchTaskApi.ts',
  ]),
  appApiAdapters: Object.freeze(['api/system.ts']),
  httpRuntimeAdapters: Object.freeze(['api/client.ts']),
})

const sourceExtension = /\.tsx?$/
const httpPackages = ['axios', 'got', 'ky', 'ofetch', 'superagent', 'undici']
const modelPackages = [
  '@ai-sdk', '@anthropic-ai/sdk', '@aws-sdk/client-bedrock-runtime',
  '@azure/openai', '@google/generative-ai', '@google/genai', '@langchain',
  '@mistralai/mistralai', 'ai', 'cohere-ai', 'groq-sdk', 'langchain',
  'ollama', 'openai', 'replicate',
]
const routerPackages = ['react-router', 'react-router-dom']
const httpCalls = new Set([
  'fetch', 'globalThis.fetch', 'navigator.sendBeacon', 'self.fetch', 'window.fetch',
])

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const target = path.join(directory, entry.name)
      if (entry.isDirectory()) return sourceFiles(target)
      return sourceExtension.test(entry.name) ? [target] : []
    }),
  )
  return nested.flat()
}

async function moduleDirectories(modulesRoot) {
  return (await readdir(modulesRoot, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
}

function isWithin(directory, target) {
  const relative = path.relative(directory, target)
  return relative === '' ||
    (!relative.startsWith('..') && !path.isAbsolute(relative))
}

const exactPaths = (root, entries) =>
  new Set(entries.map((entry) => path.resolve(root, entry)))

function moduleNameFor(target, modulesRoot, moduleNames) {
  if (!isWithin(modulesRoot, target)) return undefined
  const [name] = path.relative(modulesRoot, target).split(path.sep)
  return moduleNames.has(name) ? name : undefined
}

const packageMatches = (specifier, name) => specifier === name || specifier.startsWith(`${name}/`)

function memberPath(node) {
  if (ts.isIdentifier(node)) return node.text
  if (ts.isPropertyAccessExpression(node)) {
    const parent = memberPath(node.expression)
    return parent && `${parent}.${node.name.text}`
  }
  if (
    ts.isElementAccessExpression(node) &&
    ts.isStringLiteralLike(node.argumentExpression)
  ) {
    const parent = memberPath(node.expression)
    return parent && `${parent}.${node.argumentExpression.text}`
  }
  return undefined
}

function isBrowserRoutingMember(member = '') {
  return (
    ['window', 'globalThis', 'document'].some(
      (root) => member === `${root}.location` ||
        member.startsWith(`${root}.location.`),
    ) ||
    ['window', 'globalThis'].some(
      (root) => member === `${root}.history.pushState` ||
        member === `${root}.history.replaceState`,
    )
  )
}

function isGlobalBrowserRouting(checker, node, sourceFile) {
  if (!isBrowserRoutingMember(memberPath(node))) return false
  let root = node
  while (ts.isPropertyAccessExpression(root) ||
         ts.isElementAccessExpression(root)) root = root.expression
  const symbol = ts.isIdentifier(root) && checker.getSymbolAtLocation(root)
  return !symbol?.declarations?.some(
    (declaration) => declaration.getSourceFile() === sourceFile,
  )
}

/** AST parsing makes comments and string examples inert by construction. */
function syntaxFacts(sourceFile, checker) {
  const calls = new Set()
  const references = new Set()
  let usesBrowserRouting = false

  const visit = (node) => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier &&
          ts.isStringLiteralLike(node.moduleSpecifier)) {
        references.add(node.moduleSpecifier.text)
      }
    } else if (
      ts.isImportTypeNode(node) &&
      ts.isLiteralTypeNode(node.argument) &&
      ts.isStringLiteralLike(node.argument.literal)
    ) {
      references.add(node.argument.literal.text)
    } else if (ts.isCallExpression(node)) {
      const called = memberPath(node.expression)
      if (called) calls.add(called)
      if (node.expression.kind === ts.SyntaxKind.ImportKeyword &&
          node.arguments[0] &&
          ts.isStringLiteralLike(node.arguments[0])) {
        references.add(node.arguments[0].text)
      }
    } else if (ts.isNewExpression(node)) {
      const called = memberPath(node.expression)
      if (called) calls.add(`new:${called}`)
    }
    if ((ts.isPropertyAccessExpression(node) ||
         ts.isElementAccessExpression(node)) &&
        isGlobalBrowserRouting(checker, node, sourceFile)) {
      usesBrowserRouting = true
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return { calls, references, usesBrowserRouting }
}

function compilerContext(files, sourceRoot) {
  const options = {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    noEmit: true,
    noLib: true,
    skipLibCheck: true,
    target: ts.ScriptTarget.ESNext,
  }
  const host = ts.createCompilerHost(options, true)
  const program = ts.createProgram({ host, options, rootNames: files })
  const cache = ts.createModuleResolutionCache(
    sourceRoot, host.getCanonicalFileName, options,
  )
  const resolve = (sourceFile, specifier) =>
    ts.resolveModuleName(
      specifier, sourceFile.fileName, options, host, cache,
    ).resolvedModule?.resolvedFileName
  return { checker: program.getTypeChecker(), program, resolve }
}

function expressionSymbol(checker, node) {
  let current = node
  while (
    ts.isParenthesizedExpression(current) ||
    ts.isAsExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isNonNullExpression(current)
  ) {
    current = current.expression
  }
  if (ts.isIdentifier(current)) return checker.getSymbolAtLocation(current)
  if (ts.isPropertyAccessExpression(current))
    return checker.getSymbolAtLocation(current.name)
  if (ts.isElementAccessExpression(current))
    return checker.getSymbolAtLocation(current.argumentExpression)
  return undefined
}

/**
 * Record each declaration in an alias chain, then follow it to its terminal
 * source. That exposes adapter hops as well as two-hop value and type aliases.
 */
function symbolOrigins(checker, symbol, seen = new Set()) {
  if (!symbol || seen.has(symbol)) return new Set()
  seen.add(symbol)
  const origins = new Set(
    (symbol.declarations ?? []).map((declaration) =>
      path.resolve(declaration.getSourceFile().fileName),
    ),
  )

  if (symbol.flags & ts.SymbolFlags.Alias) {
    const target = checker.getAliasedSymbol(symbol)
    for (const origin of symbolOrigins(checker, target, seen)) {
      origins.add(origin)
    }
    return origins
  }

  for (const declaration of symbol.declarations ?? []) {
    let next
    if (ts.isVariableDeclaration(declaration) && declaration.initializer) {
      next = expressionSymbol(checker, declaration.initializer)
    } else if (ts.isTypeAliasDeclaration(declaration)) {
      const visit = (node) => {
        if (ts.isIdentifier(node)) {
          const candidate = checker.getSymbolAtLocation(node)
          if (candidate && candidate !== symbol) {
            for (const origin of symbolOrigins(checker, candidate, seen))
              origins.add(origin)
          }
        }
        ts.forEachChild(node, visit)
      }
      visit(declaration.type)
    }
    for (const origin of symbolOrigins(checker, next, seen))
      origins.add(origin)
  }
  return origins
}

function exportKind(checker, symbol) {
  const typeOnly = symbol.declarations?.some(
    (declaration) =>
      ts.isExportSpecifier(declaration) &&
      (declaration.isTypeOnly || declaration.parent.parent.isTypeOnly),
  )
  if (typeOnly) return 'type'
  const target = symbol.flags & ts.SymbolFlags.Alias
    ? checker.getAliasedSymbol(symbol)
    : symbol
  return target.flags & ts.SymbolFlags.Value ? 'value' : 'type'
}

function addExportLeaks(
  checker, sourceFile, forbidden, describe, relative, violations,
) {
  const moduleSymbol = checker.getSymbolAtLocation(sourceFile)
  const exported = moduleSymbol ? checker.getExportsOfModule(moduleSymbol) : []
  for (const symbol of exported) {
    const blocked = [...symbolOrigins(checker, symbol)].find(forbidden)
    if (blocked) {
      violations.add(
        `${relative} ${describe(blocked)} ${exportKind(checker, symbol)} ${symbol.name}`,
      )
    }
  }
}

export async function findBoundaryViolations({
  sourceRoot = defaultSourceRoot,
  policy = defaultBoundaryPolicy,
} = {}) {
  const appRoot = path.join(sourceRoot, 'app')
  const modulesRoot = path.join(sourceRoot, 'modules')
  const apiRoot = path.join(sourceRoot, 'api')
  const generatedRoot = path.join(apiRoot, 'generated')
  const files = await sourceFiles(sourceRoot)
  const discovered = await moduleDirectories(modulesRoot)
  const moduleNames = new Set(discovered)
  const dependencies = new Map(
    Object.entries(policy.moduleDependencies).map(([name, names]) => [
      name,
      new Set(names),
    ]),
  )
  const generatedAdapters = exactPaths(sourceRoot, policy.generatedApiAdapters)
  const moduleApiAdapters = exactPaths(sourceRoot, policy.moduleApiAdapters)
  const moduleAdapters = exactPaths(sourceRoot, [
    ...policy.moduleApiAdapters,
    ...policy.generatedApiAdapters.filter((entry) =>
      entry.startsWith('modules/'),
    ),
  ])
  const appAdapters = exactPaths(sourceRoot, policy.appApiAdapters)
  const httpAdapters = exactPaths(sourceRoot, policy.httpRuntimeAdapters)
  const { checker, program, resolve } = compilerContext(files, sourceRoot)
  const violations = new Set()
  const report = (condition, message) =>
    condition && violations.add(message)

  for (const name of discovered) {
    report(
      !dependencies.has(name),
      `${name} is missing an allowed dependency declaration`,
    )
    report(
      !program.getSourceFile(path.join(modulesRoot, name, 'index.ts')),
      `${name} has no public index.ts`,
    )
  }
  for (const [name, allowed] of dependencies) {
    report(!moduleNames.has(name),
      `${name} is registered but has no module directory`)
    for (const dependency of allowed) {
      report(!moduleNames.has(dependency),
        `${name} declares unknown module dependency ${dependency}`)
      report(dependency === name,
        `${name} declares itself as a dependency`)
    }
  }

  for (const sourcePath of files) {
    const sourceFile = program.getSourceFile(sourcePath)
    if (!sourceFile) continue
    const facts = syntaxFacts(sourceFile, checker)
    const relative = path.relative(sourceRoot, sourcePath).split(path.sep).join('/')
    const sourceModule = moduleNameFor(sourcePath, modulesRoot, moduleNames)
    const inApp = isWithin(appRoot, sourcePath)
    const inApi = isWithin(apiRoot, sourcePath)
    const inGenerated = isWithin(generatedRoot, sourcePath)
    const isPublicIndex =
      sourceModule &&
      sourcePath === path.join(modulesRoot, sourceModule, 'index.ts')
    const usesHttp =
      [...facts.calls].some((call) => httpCalls.has(call)) ||
      facts.calls.has('new:XMLHttpRequest')

    report(!inGenerated && usesHttp && !httpAdapters.has(sourcePath),
      `${relative} uses HTTP outside the runtime adapter`)
    report(sourceModule && facts.usesBrowserRouting,
      `${relative} uses browser routing APIs in a product module`)

    for (const specifier of facts.references) {
      const httpPackage = httpPackages.find((name) =>
        packageMatches(specifier, name),
      )
      const modelPackage = modelPackages.find((name) =>
        packageMatches(specifier, name),
      )
      report(httpPackage && !inGenerated && !httpAdapters.has(sourcePath),
        `${relative} imports ${httpPackage} as a direct HTTP client`)
      report(modelPackage,
        `${relative} imports ${modelPackage} as a model SDK`)
      report(
        sourceModule &&
          routerPackages.some((name) => packageMatches(specifier, name)),
        `${relative} imports routing in a product module`,
      )

      const target = resolve(sourceFile, specifier)
      if (!target) continue
      const targetModule = moduleNameFor(target, modulesRoot, moduleNames)
      const targetApp = isWithin(appRoot, target)
      const targetApi = isWithin(apiRoot, target)
      const targetGenerated = isWithin(generatedRoot, target)

      report(isPublicIndex && moduleAdapters.has(path.resolve(target)),
        `${relative} imports module adapter from its public index`)
      report(sourceModule && targetApp, `${relative} imports app code`)
      report(
        inApi && !inGenerated && targetApp,
        `${relative} imports app code from the API layer`,
      )
      report(inGenerated && !targetGenerated,
        `${relative} imports outside the generated API layer`)
      report(
        targetGenerated &&
          !inGenerated &&
          !generatedAdapters.has(sourcePath),
        `${relative} imports generated API outside an approved adapter`,
      )
      report(
        inApp &&
          targetApi &&
          !targetGenerated &&
          !appAdapters.has(path.resolve(target)),
        `${relative} imports API internals instead of an approved app adapter`,
      )
      report(
        sourceModule &&
          targetApi &&
          !targetGenerated &&
          !moduleApiAdapters.has(sourcePath),
        `${relative} imports API internals outside its module adapter`)
      report(inApi && !inGenerated && targetModule,
        `${relative} imports product module code from the API layer`)

      if (!targetModule || sourceModule === targetModule) continue
      report(
        sourceModule && !dependencies.get(sourceModule)?.has(targetModule),
        `${sourceModule} cannot depend on ${targetModule}`,
      )
      const publicEntry = path.join(modulesRoot, targetModule, 'index.ts')
      report(path.resolve(target) !== publicEntry,
        `${relative} bypasses ${targetModule}/index.ts`)
    }

    if (moduleAdapters.has(sourcePath)) {
      addExportLeaks(
        checker,
        sourceFile,
        (origin) => isWithin(apiRoot, origin),
        (origin) =>
          `re-exports raw ${
            isWithin(generatedRoot, origin) ? 'generated API' : 'API'
          }`,
        relative,
        violations,
      )
    }
    if (appAdapters.has(sourcePath)) {
      addExportLeaks(
        checker,
        sourceFile,
        (origin) => isWithin(generatedRoot, origin),
        () => 're-exports raw generated API',
        relative,
        violations,
      )
    }
    if (isPublicIndex) {
      addExportLeaks(
        checker,
        sourceFile,
        (origin) => moduleAdapters.has(origin),
        () => 'exports module adapter',
        relative,
        violations,
      )
    }
  }
  return [...violations].sort()
}

export async function assertModuleBoundaries(options) {
  const violations = await findBoundaryViolations(options)
  if (violations.length) {
    throw new Error(`Module boundary violations:\n${violations.join('\n')}`)
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  try {
    await assertModuleBoundaries()
    process.stdout.write('Module boundaries: ok\n')
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : error}\n`)
    process.exitCode = 1
  }
}
