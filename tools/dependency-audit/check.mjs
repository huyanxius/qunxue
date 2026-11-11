import { execFileSync, spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const advisoryId = /^[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+$/
const npmName = /^(?:@[a-z0-9_.-]+\/)?[a-z0-9_.-]+$/
const pythonName = /^[a-z0-9]+(?:[-_.]+[a-z0-9]+)*$/i
const pythonVersion = /^[0-9][A-Za-z0-9.+!_-]*$/
const normalizePython = (name) => name.toLowerCase().replace(/[-_.]+/g, '-')
const scope = (ecosystem, name, version, id) => JSON.stringify([ecosystem, name, version, id])

function npmSemver() {
  // Match npm's range semantics using its bundled parser, without installing application packages.
  try {
    const cli = realpathSync(execFileSync('which', ['npm'], { encoding: 'utf8' }).trim())
    return createRequire(cli)('semver')
  } catch (error) {
    throw new Error(`npm audit: cannot load npm's bundled semver (${error.message})`)
  }
}

function indexExceptions(exceptions, semver) {
  if (!Array.isArray(exceptions)) throw new Error('Expected an array of dependency audit exceptions')
  const index = new Map()
  for (const entry of exceptions) {
    const { ecosystem, package: name, version, advisories, reason, expires } = entry
    const validScope = typeof name === 'string' && typeof version === 'string' &&
      (ecosystem === 'npm' ? npmName.test(name) && semver.valid(version) :
        ecosystem === 'pypi' && pythonName.test(name) && pythonVersion.test(version))
    if (!validScope || !Array.isArray(advisories) || !advisories.length ||
        !advisories.every((id) => typeof id === 'string' && advisoryId.test(id)) ||
        typeof reason !== 'string' || !reason.trim() ||
        !/^\d{4}-\d{2}-\d{2}$/.test(expires) || !Number.isFinite(Date.parse(expires)) ||
        new Date(expires).toISOString().slice(0, 10) !== expires) {
      throw new Error(`Invalid dependency audit exception for ${ecosystem} ${name} ${version}`)
    }
    for (const id of advisories) {
      const key = scope(ecosystem, ecosystem === 'pypi' ? normalizePython(name) : name, version, id)
      if (index.has(key)) throw new Error(`Duplicate dependency audit exception ${key}`)
      index.set(key, { id, expires, reason })
    }
  }
  return index
}

function scannerError(name, result, detail) {
  const diagnostic = result.error?.message || result.stderr?.trim() || result.signal
  return new Error(`${name}: ${detail} (exit ${result.status})${diagnostic ? `: ${diagnostic}` : ''}`)
}

function readReport(name, result) {
  if (![0, 1].includes(result.status)) throw scannerError(name, result, 'scanner failed')
  try {
    return JSON.parse(result.stdout)
  } catch {
    throw scannerError(name, result, 'missing or invalid JSON report')
  }
}

function record(findings, finding) {
  const key = scope(finding.ecosystem, finding.package, finding.version, finding.id)
  const previous = findings.get(key)
  if (previous) {
    previous.paths = [...new Set([...previous.paths, ...finding.paths])]
    previous.aliases = [...new Set([...previous.aliases, ...finding.aliases])]
  } else {
    findings.set(key, finding)
  }
}

function readNpm(npm, lock, findings, semver) {
  const report = readReport('npm audit', npm)
  const vulnerabilities = report?.vulnerabilities
  if (report?.error || report?.auditReportVersion !== 2 || !vulnerabilities ||
      typeof vulnerabilities !== 'object' || Array.isArray(vulnerabilities)) {
    throw scannerError('npm audit', npm, 'incomplete audit report')
  }
  const totals = report?.metadata?.vulnerabilities
  const entries = Object.entries(vulnerabilities)
  if (totals?.total !== entries.length || npm.status !== Number(entries.length > 0)) {
    throw scannerError('npm audit', npm, 'incomplete audit report')
  }

  const propagated = []
  const paths = new Set()
  for (const [name, { nodes, via }] of entries) {
    if (!Array.isArray(nodes) || !nodes.length || !Array.isArray(via) || !via.length) {
      throw scannerError('npm audit', npm, `missing nodes or advisories for ${name}`)
    }
    const upstream = via.filter((entry) => typeof entry === 'string')
    if (upstream.some((dependency) => !Object.hasOwn(vulnerabilities, dependency))) {
      throw scannerError('npm audit', npm, `missing upstream advisory for ${name}`)
    }
    // npm reports metavulnerabilities on parents. Apply policy to the advisory
    // on the affected dependency and retain its parent references in the log.
    if (upstream.length) propagated.push({ package: name, paths: nodes, via: upstream })
    for (const node of nodes) {
      paths.add(node)
      const version = lock.packages[node]?.version
      if (!semver.valid(version)) throw scannerError('npm audit', npm, `no locked version for ${node}`)
      let explained = upstream.length > 0
      for (const entry of via.filter((value) => typeof value !== 'string')) {
        if (!entry || !Number.isSafeInteger(entry.source) || !semver.validRange(entry.range)) {
          throw scannerError('npm audit', npm, `invalid advisory for ${name}`)
        }
        if (!semver.satisfies(version, entry.range, { loose: true, includePrerelease: true })) continue
        explained = true
        const id = /\/advisories\/(GHSA-[a-z0-9-]+)(?:[/?#]|$)/.exec(entry.url)?.[1] ?? `NPM-${entry.source}`
        record(findings, { ecosystem: 'npm', package: name, version, id, aliases: [],
          paths: [node], severity: entry.severity, url: entry.url })
      }
      if (!explained) throw scannerError('npm audit', npm, `no advisory matches ${node}@${version}`)
    }
  }
  return { entries: entries.length, paths: paths.size, severities: totals, propagated }
}

function readPython(pip, requirements, findings) {
  const report = readReport('pip-audit (OSV)', pip)
  if (!Array.isArray(report?.dependencies) || !report.dependencies.length) {
    throw scannerError('pip-audit (OSV)', pip, 'missing dependency results')
  }
  const parents = new Map()
  let currentParents
  for (const line of requirements.split('\n')) {
    const pin = /^([a-z0-9_.-]+)==([^\s;]+)/i.exec(line)
    const parent = /^    # (?:via |  )([a-z0-9_.-]+)$/i.exec(line)?.[1]
    if (pin) {
      const key = `${normalizePython(pin[1])}==${pin[2]}`
      if (!parents.has(key)) parents.set(key, new Set())
      currentParents = parents.get(key)
    } else if (parent) {
      currentParents?.add(parent)
    }
  }
  let rawFindings = 0
  const affected = new Set()
  for (const { name, version, vulns, skip_reason: skipped } of report.dependencies) {
    const paths = typeof name === 'string' && parents.get(`${normalizePython(name)}==${version}`)
    if (skipped || !paths || !Array.isArray(vulns)) {
      throw scannerError('pip-audit (OSV)', pip, `could not audit locked dependency ${name}: ${skipped ?? 'invalid result'}`)
    }
    rawFindings += vulns.length
    if (vulns.length) affected.add(normalizePython(name))
    for (const { id, aliases } of vulns) {
      if (typeof id !== 'string' || !advisoryId.test(id) || !Array.isArray(aliases)) {
        throw scannerError('pip-audit (OSV)', pip, `invalid advisory for ${name}`)
      }
      record(findings, { ecosystem: 'pypi', package: normalizePython(name), version, id,
        aliases, paths: [...paths] })
    }
  }
  if (pip.status !== Number(rawFindings > 0)) {
    throw scannerError('pip-audit (OSV)', pip, 'findings disagree with the exit status')
  }
  return { scanned: report.dependencies.length, affected: affected.size, rawFindings }
}

export function evaluate({ npm, pip, lock, requirements, exceptions, today }) {
  const semver = npmSemver()
  const index = indexExceptions(exceptions, semver)
  const findings = new Map()
  const npmSummary = readNpm(npm, lock, findings, semver)
  const pythonSummary = readPython(pip, requirements, findings)
  const evaluated = [...findings.values()].map((finding) => {
    const matches = [finding.id, ...finding.aliases]
      .map((id) => index.get(scope(finding.ecosystem, finding.package, finding.version, id)))
      .filter(Boolean)
    const active = matches.find((exception) => today < exception.expires)
    return { ...finding, state: active ? 'excepted' : matches.length ? 'expired' : 'unexcepted',
      exception: active ?? matches[0] }
  })
  return {
    status: Number(evaluated.some(({ state }) => state !== 'excepted')),
    findings: evaluated,
    npmSummary,
    pythonSummary,
  }
}

function run(command, args, cwd) {
  return spawnSync(command, args, { cwd, encoding: 'utf8', timeout: 240_000, maxBuffer: 16 * 1024 * 1024 })
}

function main() {
  const root = fileURLToPath(new URL('../../', import.meta.url))
  const locks = ['frontend/package-lock.json', 'backend/uv.lock']
  const sha256 = (file) => createHash('sha256').update(readFileSync(join(root, file))).digest('hex')
  const before = locks.map(sha256)
  console.log(JSON.stringify({ started: new Date().toISOString(),
    sources: ['https://registry.npmjs.org', 'https://api.osv.dev/v1/query'],
    locks: Object.fromEntries(locks.map((file, index) => [file, before[index]])) }))

  const tmp = mkdtempSync(join(tmpdir(), 'qunxue-dependency-audit-'))
  try {
    const exported = run('uv', ['export', '--locked', '--no-dev', '--no-emit-project', '--format', 'requirements-txt'],
      join(root, 'backend'))
    if (exported.status !== 0) throw scannerError('uv export', exported, 'failed to export locked production requirements')
    const requirementsFile = join(tmp, 'requirements.txt')
    writeFileSync(requirementsFile, exported.stdout)

    const npm = run('npm', ['audit', '--package-lock-only', '--omit=dev', '--audit-level=info', '--json',
      '--registry=https://registry.npmjs.org', '--fetch-retries=1'], join(root, 'frontend'))
    const pip = run('pip-audit', ['--vulnerability-service', 'osv', '--no-deps', '--disable-pip', '--require-hashes',
      '--strict', '--format', 'json', '--desc', 'off', '--aliases', 'on', '--progress-spinner', 'off',
      '-r', requirementsFile], root)
    const { status, findings, npmSummary, pythonSummary } = evaluate({
      npm, pip, requirements: exported.stdout, today: new Date().toISOString().slice(0, 10),
      lock: JSON.parse(readFileSync(join(root, locks[0]), 'utf8')),
      exceptions: JSON.parse(readFileSync(join(root, '.github/dependency-audit-exceptions.json'), 'utf8')),
    })
    const { propagated, ...npmCounts } = npmSummary
    for (const entry of propagated) console.log('npm parent:', JSON.stringify(entry))
    for (const finding of findings) console.log('advisory:', JSON.stringify(finding))
    console.log(JSON.stringify({ npm: npmCounts, python: pythonSummary, advisoryFindings: findings.length,
      excepted: findings.filter(({ state }) => state === 'excepted').length,
      blocked: findings.filter(({ state }) => state !== 'excepted').length }))
    return status
  } finally {
    rmSync(tmp, { recursive: true, force: true })
    for (const [index, file] of locks.entries()) {
      if (sha256(file) !== before[index]) throw new Error(`Dependency lock changed during audit: ${file}`)
    }
    console.log('Dependency lock hashes unchanged')
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exitCode = main()
  } catch (error) {
    console.error('Dependency audit error:', JSON.stringify(error.message))
    process.exitCode = 2
  }
}
