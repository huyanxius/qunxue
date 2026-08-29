import type { ResearchCanvasProjection } from './researchCanvasProjection'

type FormalNavigationSnapshot = {
  phenomenon_summary?: {
    phenomenon: string
    research_intent?: string | null
  } | null
} | null

type FormalEvidenceSnapshot = {
  evidence_ref_id: string
  claim: string
  excerpt?: string | null
  locator?: string | null
  source_id?: string | null
}

type FormalCandidateSnapshot = {
  candidate_id: string
  title: string
  applicability_rationale: string
  problem_focus?: string | null
  source_ids?: string[]
  supporting_evidence?: FormalEvidenceSnapshot[]
  conflicting_evidence?: FormalEvidenceSnapshot[]
}

type FormalMatchRunSnapshot = {
  candidate_page: {
    candidates: FormalCandidateSnapshot[]
  }
} | null

type FormalSectionSnapshot = {
  section_id: string
  title: string
  content: string
  status: string
  evidence_refs?: Array<{ source_id: string }>
}

type FormalTheoryDecision = {
  action: string
}

type FormalComparisonFinding = {
  kind: 'support' | 'counterexample' | 'contradict' | 'competing_explanation' | 'evidence_gap'
  statement: string
  annotation_ids?: string[]
}

type FormalCaseComparisonSnapshot = {
  comparison_id: string
  title: string
  question: string
  status: string
  findings: FormalComparisonFinding[]
  competing_explanations: string[]
  evidence_gaps: string[]
  next_steps: Array<{ kind: string; action: string; priority?: string }>
  theory_implication: string
}

type FormalAnalysisSnapshot = {
  comparisons: FormalCaseComparisonSnapshot[]
} | null

export type FormalResearchCanvasInput = {
  taskId: string | null
  mode: 'match' | 'framework'
  agentProjection: ResearchCanvasProjection
  navigation: FormalNavigationSnapshot
  matchRun: FormalMatchRunSnapshot
  pendingTheoryDecisions: Readonly<Record<string, FormalTheoryDecision>>
  sections: readonly FormalSectionSnapshot[]
  documentTitle?: string | null
  analysisSnapshot?: FormalAnalysisSnapshot
}

/** Derive formal M3/M4/M5 canvas state only from recoverable server snapshots. */
export function projectFormalResearchCanvas({
  taskId,
  mode,
  agentProjection,
  navigation,
  matchRun,
  pendingTheoryDecisions,
  sections,
  documentTitle,
  analysisSnapshot,
}: FormalResearchCanvasInput): ResearchCanvasProjection {
  const taskIdentity = taskId ?? 'unknown'
  const questionNode = agentProjection.nodes.find((node) => node.kind === 'question')
  const fallbackQuestionId = `research-question:${taskIdentity}`
  const phenomenonId = `research-phenomenon:${taskIdentity}`
  const nodes: ResearchCanvasProjection['nodes'] = questionNode
    ? [...agentProjection.nodes]
    : [
        ...agentProjection.nodes,
        {
          id: fallbackQuestionId,
          kind: 'question',
          title: navigation?.phenomenon_summary?.phenomenon ?? '当前研究问题',
          summary:
            navigation?.phenomenon_summary?.research_intent
            ?? '从已经确认的研究起点继续推进。',
          excerpt: navigation?.phenomenon_summary?.research_intent ?? null,
          status: 'grounded',
          provenance: 'user',
          citationIds: [],
        },
      ]

  if (navigation?.phenomenon_summary) {
    nodes.push({
      id: phenomenonId,
      kind: 'phenomenon',
      title: navigation.phenomenon_summary.phenomenon,
      summary:
        navigation.phenomenon_summary.research_intent
        ?? '已经确认并固定到当前研究任务的核心现象。',
      excerpt: navigation.phenomenon_summary.research_intent ?? null,
      status: 'grounded',
      provenance: 'user',
      citationIds: [],
    })
  }

  const candidates = matchRun?.candidate_page.candidates ?? []
  nodes.push(...candidates.map((candidate) => ({
    id: `research-theory:${candidate.candidate_id}`,
    kind: 'theory' as const,
    title: candidate.title,
    summary: candidate.applicability_rationale,
    excerpt: candidate.problem_focus || candidate.applicability_rationale,
    status:
      pendingTheoryDecisions[candidate.candidate_id]?.action === 'adopt'
      || pendingTheoryDecisions[candidate.candidate_id]?.action === 'combine'
        ? 'grounded' as const
        : 'developing' as const,
    provenance: 'knowledge' as const,
    citationIds: candidate.source_ids ?? [],
  })))

  const evidenceById = new Map<string, ResearchCanvasProjection['nodes'][number]>()
  for (const candidate of candidates) {
    for (const evidence of [
      ...(candidate.supporting_evidence ?? []),
      ...(candidate.conflicting_evidence ?? []),
    ]) {
      const evidenceId = `research-evidence:${evidence.evidence_ref_id}`
      evidenceById.set(evidenceId, {
        id: evidenceId,
        kind: 'evidence',
        title: evidence.claim,
        summary: evidence.excerpt ?? evidence.locator ?? '来自固定知识发布的证据。',
        excerpt: evidence.excerpt,
        status: 'verified',
        provenance: 'knowledge',
        citationIds: evidence.source_id ? [evidence.source_id] : [],
      })
    }
  }
  nodes.push(...evidenceById.values())

  const sectionNodePrefix = `research-section:${taskIdentity}:${mode}:`
  const sectionNodes: ResearchCanvasProjection['nodes'] = sections.map((section) => ({
    id: `${sectionNodePrefix}${section.section_id}`,
    kind: 'document',
    title: section.title,
    summary: section.content
      .trim()
      .replace(/[#*_`>\n]+/g, ' ')
      .replace(/\s+/g, ' ')
      .slice(0, 92),
    excerpt: section.content || null,
    status:
      section.status === 'confirmed' || section.status === 'reviewed'
        ? 'complete'
        : 'developing',
    provenance: 'user',
    citationIds: (section.evidence_refs ?? []).map((reference) => reference.source_id),
  }))
  nodes.push(...sectionNodes)

  const source = navigation?.phenomenon_summary
    ? phenomenonId
    : questionNode?.id ?? fallbackQuestionId
  const stageEdges: ResearchCanvasProjection['edges'] = []
  if (navigation?.phenomenon_summary) {
    stageEdges.push({
      id: `research-phenomenon-edge:${taskIdentity}`,
      source: questionNode?.id ?? fallbackQuestionId,
      target: phenomenonId,
      relation: 'refines',
      label: '确认现象',
    })
  }
  for (const candidate of candidates) {
    const theoryId = `research-theory:${candidate.candidate_id}`
    stageEdges.push({
      id: `research-theory-edge:${candidate.candidate_id}`,
      source,
      target: theoryId,
      relation: 'explains',
      label: '候选解释',
    })
    for (const evidence of candidate.supporting_evidence ?? []) {
      stageEdges.push({
        id: `research-support:${candidate.candidate_id}:${evidence.evidence_ref_id}`,
        source: `research-evidence:${evidence.evidence_ref_id}`,
        target: theoryId,
        relation: 'supports',
        label: '支持',
      })
    }
    for (const evidence of candidate.conflicting_evidence ?? []) {
      stageEdges.push({
        id: `research-challenge:${candidate.candidate_id}:${evidence.evidence_ref_id}`,
        source: `research-evidence:${evidence.evidence_ref_id}`,
        target: theoryId,
        relation: 'challenges',
        label: '质疑',
      })
    }
  }

  const comparisonProjection = projectConfirmedComparisons(
    analysisSnapshot?.comparisons ?? [],
    source,
  )
  nodes.push(...comparisonProjection.nodes)

  const firstLayerSize = Math.ceil(sectionNodes.length / 2)
  const sectionEdges: ResearchCanvasProjection['edges'] = sectionNodes.map((node, index) => ({
    id: `research-section-edge:${index}:${node.id}`,
    source: index < firstLayerSize ? source : sectionNodes[index - firstLayerSize].id,
    target: node.id,
    relation: 'refines',
    label: '',
  }))

  return {
    ...agentProjection,
    status: 'ready',
    question:
      navigation?.phenomenon_summary?.phenomenon
      ?? documentTitle
      ?? agentProjection.question,
    nodes,
    edges: [
      ...agentProjection.edges,
      ...stageEdges,
      ...comparisonProjection.edges,
      ...sectionEdges,
    ],
  }
}

function projectConfirmedComparisons(
  comparisons: readonly FormalCaseComparisonSnapshot[],
  source: string,
): Pick<ResearchCanvasProjection, 'nodes' | 'edges'> {
  const nodes: ResearchCanvasProjection['nodes'] = []
  const edges: ResearchCanvasProjection['edges'] = []

  for (const comparison of comparisons.filter((item) => item.status === 'confirmed')) {
    const comparisonId = `research-comparison:${comparison.comparison_id}`
    const comparisonCitationIds = distinct(
      comparison.findings.flatMap((finding) => finding.annotation_ids ?? []),
    )
    nodes.push({
      id: comparisonId,
      kind: 'synthesis',
      title: comparison.title,
      summary: comparison.question,
      excerpt: comparison.question,
      status: 'complete',
      provenance: 'user',
      citationIds: comparisonCitationIds,
    })
    edges.push({
      id: `${comparisonId}:edge`,
      source,
      target: comparisonId,
      relation: 'derives',
      label: '已确认比较',
    })

    const evidenceFindings = comparison.findings.filter((finding) => (
      finding.kind === 'support'
      || finding.kind === 'counterexample'
      || finding.kind === 'contradict'
    ))
    evidenceFindings.forEach((finding, index) => {
      const findingId = `${comparisonId}:finding:${finding.kind}:${index}`
      const label = finding.kind === 'support'
        ? '支持证据'
        : finding.kind === 'counterexample'
          ? '反例'
          : '矛盾材料'
      nodes.push({
        id: findingId,
        kind: 'evidence',
        title: finding.statement,
        summary: label,
        excerpt: finding.statement,
        status: finding.kind === 'support' ? 'verified' : 'challenged',
        provenance: 'user',
        citationIds: distinct(finding.annotation_ids ?? []),
      })
      edges.push({
        id: `${findingId}:edge`,
        source: findingId,
        target: comparisonId,
        relation: finding.kind === 'support' ? 'supports' : 'challenges',
        label,
      })
    })

    const competingExplanations = distinctByStatement([
      ...comparison.findings
        .filter((finding) => finding.kind === 'competing_explanation')
        .map((finding) => ({
          statement: finding.statement,
          annotationIds: finding.annotation_ids ?? [],
        })),
      ...comparison.competing_explanations.map((statement) => ({ statement, annotationIds: [] })),
    ])
    competingExplanations.forEach((item, index) => {
      const alternativeId = `${comparisonId}:competing:${index}`
      nodes.push({
        id: alternativeId,
        kind: 'theory',
        title: item.statement,
        summary: '与当前解释竞争，需要继续检验。',
        excerpt: item.statement,
        status: 'challenged',
        provenance: 'user',
        citationIds: distinct(item.annotationIds),
      })
      edges.push({
        id: `${alternativeId}:edge`,
        source: alternativeId,
        target: comparisonId,
        relation: 'challenges',
        label: '竞争解释',
      })
    })

    const evidenceGaps = distinctByStatement([
      ...comparison.findings
        .filter((finding) => finding.kind === 'evidence_gap')
        .map((finding) => ({
          statement: finding.statement,
          annotationIds: finding.annotation_ids ?? [],
        })),
      ...comparison.evidence_gaps.map((statement) => ({ statement, annotationIds: [] })),
    ])
    evidenceGaps.forEach((item, index) => {
      const gapId = `${comparisonId}:gap:${index}`
      nodes.push({
        id: gapId,
        kind: 'gap',
        title: item.statement,
        summary: '案例比较确认的证据缺口。',
        excerpt: item.statement,
        status: 'open',
        provenance: 'user',
        citationIds: distinct(item.annotationIds),
      })
      edges.push({
        id: `${gapId}:edge`,
        source: comparisonId,
        target: gapId,
        relation: 'derives',
        label: '证据缺口',
      })
    })

    comparison.next_steps.forEach((step, index) => {
      const nextStepId = `${comparisonId}:next-step:${index}`
      nodes.push({
        id: nextStepId,
        kind: 'gap',
        title: step.action,
        summary: [step.kind, step.priority].filter(Boolean).join(' · '),
        excerpt: step.action,
        status: 'open',
        provenance: 'user',
        citationIds: [],
      })
      edges.push({
        id: `${nextStepId}:edge`,
        source: comparisonId,
        target: nextStepId,
        relation: 'refines',
        label: '下一步研究',
      })
    })

    if (comparison.theory_implication.trim()) {
      const theoryImplicationId = `${comparisonId}:theory-implication`
      nodes.push({
        id: theoryImplicationId,
        kind: 'theory',
        title: '案例比较形成的理论判断',
        summary: comparison.theory_implication,
        excerpt: comparison.theory_implication,
        status: 'grounded',
        provenance: 'user',
        citationIds: comparisonCitationIds,
      })
      edges.push({
        id: `${theoryImplicationId}:edge`,
        source: comparisonId,
        target: theoryImplicationId,
        relation: 'refines',
        label: '修订理论判断',
      })
    }
  }

  return { nodes, edges }
}

function distinct(values: readonly string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))]
}

function distinctByStatement<T extends { statement: string; annotationIds: string[] }>(
  values: readonly T[],
): T[] {
  const byStatement = new Map<string, T>()
  for (const value of values) {
    const statement = value.statement.trim()
    if (!statement || byStatement.has(statement)) continue
    byStatement.set(statement, { ...value, statement })
  }
  return [...byStatement.values()]
}
