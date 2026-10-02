import { apiClient } from '../../api/client';
import { getFrontierKnowledgeLinks, getFrontierReadingPriority, listFrontierReadingPriorities } from '../../api/generated/sdk.gen';
import type { FrontierKnowledgeLinksResponse, FrontierReadingPriorityResponse } from '../../api/generated/types.gen';

export function readingPriorityView(item: FrontierReadingPriorityResponse) {
  return {
    recordId: item.record_id, title: item.title, recordVersion: item.version,
    snapshotHash: item.content_hash, readinessLevel: item.reading_priority,
    supportedFields: item.supported_fields,
    missingFields: Object.entries(item.missing_fields).map(([field, reason]) => ({ field, reason })),
    sourceEvidence: item.basis.map(e => ({ blockId: e.block_id, locator: e.locator, url: e.url, snippet: e.snippet, basisType: e.basis_type })),
    academic: { status: item.assessment.status, value: item.assessment.academic_value,
      ruleVersion: item.assessment.rule_version,
      criteria: Object.entries(item.assessment.criteria).map(([key, criterion]) => ({
        key, weight: criterion.weight, score: criterion.score, rationale: criterion.rationale,
        missingReason: criterion.missing_reason,
        evidence: criterion.evidence.map(e => ({ locator: e.locator, version: e.version, reviewer: e.reviewed_by })),
      })),
    },
    limitations: item.limitations,
  };
}
export function knowledgeLinksView(item: FrontierKnowledgeLinksResponse) {
  return { recordId: item.record_id, recordVersion: item.record_version, snapshotHash: item.record_content_hash,
    release: item.knowledge_release_id ? { id: item.knowledge_release_id, hash: item.knowledge_release_hash,
      level: item.knowledge_release_level } : null,
    state: item.status,
    matches: item.matches.map(match => ({ id: match.knowledge_id, title: match.title,
      version: match.content_version, topics: match.matched_topics })), limitations: item.limitations,
  };
}
export type ReadingPriority = ReturnType<typeof readingPriorityView>;
export type KnowledgeReadingLinks = ReturnType<typeof knowledgeLinksView>;
export async function readRecordInsights(recordId: string, asOf?: string, signal?: AbortSignal) {
  const query = asOf ? { as_of: asOf } : undefined;
  const path = { record_id: recordId };
  const [priority, links] = await Promise.all([
    getFrontierReadingPriority({ client: apiClient, path, query, signal }),
    getFrontierKnowledgeLinks({ client: apiClient, path, query, signal }),
  ]);
  if (!priority.data || !links.data) throw new Error('阅读依据暂时无法读取，请重试');
  return { priority: readingPriorityView(priority.data), links: knowledgeLinksView(links.data) };
}
export async function readReadingPriorities(options: {
  q?: string; asOf?: string; readiness?: ReadingPriority['readinessLevel'];
  assessmentStatus?: ReadingPriority['academic']['status']; minAcademicValue?: number; offset?: number; limit?: number;
} = {}) {
  const result = await listFrontierReadingPriorities({ client: apiClient, query: {
    q: options.q, as_of: options.asOf, readiness: options.readiness,
    assessment_status: options.assessmentStatus, min_academic_value: options.minAcademicValue, offset: options.offset, limit: options.limit,
  } });
  if (!result.data) throw new Error('阅读优先级暂时无法读取，请重试');
  return { items: result.data.items.map(readingPriorityView), total: result.data.total,
    offset: result.data.offset, nextOffset: result.data.next_offset, asOf: result.data.as_of,
    sortBasis: result.data.sort_basis };
}
