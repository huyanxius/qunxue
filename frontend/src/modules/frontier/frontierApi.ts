import { apiClient } from "../../api/client";
import {
  getFrontierCalendar,
  getFrontierPeriodReport,
  getFrontierKnowledgeLinks,
  getFrontierOverview,
  listFrontierSources,
  listFrontierTopics,
  listFrontierSummaries,
  getFrontierRecord,
} from "../../api/generated/sdk.gen";
import type {
  FrontierRecordResponse,
  FrontierRecordSummaryResponse,
  FrontierTopicResponse,
  FrontierTopicPageResponse,
  FrontierSourcePageResponse,
  FrontierStatusResponse,
  FrontierEvidenceStatementResponse,
  FrontierOverviewResponse,
  FrontierDistributionResponse,
} from "../../api/generated/types.gen";
import type { FrontierRecord } from "./model";
import type { FrontierDataset, FrontierTopic, FrontierEvidenceStatement, FrontierCorpusOverview } from "./dataset";

export function recordView(record: FrontierRecordResponse): FrontierRecord {
  return {
    id: record.id,
    title: record.title,
    authors: record.authors ?? null,
    source_name: record.source_name,
    source_publisher: record.source_publisher,
    source_published_at: record.source_published_at ?? null,
    published_at: record.published_at ?? null,
    published_at_display: record.published_at_display,
    publication_year: record.publication_year ?? null,
    publication_issue: record.publication_issue ?? null,
    url: record.url,
    summary: record.summary ?? "",
    why_read: record.why_read ?? null,
    media: (record.media ?? []).map((media) => ({
      url: media.url, caption: media.caption, source_url: media.source_url, kind: media.kind, alt: media.alt,
    })),
    topics: record.topics,
    verification_status: record.verification_status,
    verification_note: record.verification_note,
    editorial_caveat: record.editorial_caveat ?? "",
    research_question: record.research_question ?? null,
    methods: record.methods ?? null,
    data: record.data ?? null,
    findings: record.findings ?? [],
    evidence: record.evidence.map((item) => ({
      snippet: item.snippet ?? null,
      locator: item.locator,
      url: item.url,
    })),
    within_preferred_window: record.within_preferred_window ?? null,
  };
}
function statementView(statement: FrontierEvidenceStatementResponse): FrontierEvidenceStatement {
  return { text: statement.text, evidenceRecordIds: statement.evidence_record_ids };
}
export function topicView(topic: FrontierTopicResponse): FrontierTopic {
  const brief = topic.editorial_brief;
  const research = topic.research_brief;
  return {
    id: topic.id,
    key: topic.topic_key,
    title: topic.title,
    stream: topic.stream,
    recordIds: topic.record_ids ?? [],
    sourceIds: topic.source_ids,
    sourceDistribution: topic.source_distribution,
    summary: topic.summary,
    counts: {
      total: topic.counts.total,
      dated: topic.counts.dated,
      undated: topic.counts.undated,
      days30: topic.counts.days_30,
      days90: topic.counts.days_90,
      days180: topic.counts.days_180,
      previous90: topic.counts.prior_90_for_growth,
    },
    trendStatus: topic.trend_status,
    trendSignals: topic.trend_signals,
    growthBaseline: topic.growth_baseline,
    reasons: topic.reasons,
    researchBrief: research ? {
      headline: research.headline,
      development: research.development ? statementView(research.development) : null,
      consensus: (research.consensus ?? []).map(statementView),
      differences: (research.differences ?? []).map(statementView),
      methods: (research.methods ?? []).map(statementView),
      researchImplication: research.research_implication ? statementView(research.research_implication) : null,
      priorityReads: (research.priority_reads ?? []).map((read) => ({ recordId: read.record_id, reason: read.reason })),
      evidenceRecordIds: research.evidence_record_ids,
      generatedBy: research.generated_by,
      basisContentHash: research.basis_content_hash,
      updatedAt: research.updated_at,
    } : undefined,
    monthlySeries: (topic.monthly_series ?? []).map((month) => ({
      month: month.month, recordCount: month.record_count, datedRecordIds: month.dated_record_ids,
      sourceIds: month.source_ids, coverageComplete: month.coverage_complete, observationBasis: month.observation_basis,
      isPartialMonth: month.is_partial_month, denominator: month.denominator, sampleShare: month.sample_share, normalizedShare: month.normalized_share,
    })),
    issueSeries: (topic.issue_series ?? []).map((issue) => ({
      issueId: issue.issue_id, label: issue.label, sourceId: issue.source_id, publicationMonth: issue.publication_month,
      candidateCount: issue.candidate_count, readableCount: issue.readable_count, includedCount: issue.included_count,
      denominator: issue.denominator, topicRecordCount: issue.topic_record_count, share: issue.share,
      coverageComplete: issue.coverage_complete, evidenceRecordIds: issue.evidence_record_ids,
      denominatorRecordIds: issue.denominator_record_ids, issueUrl: issue.issue_url, comparisonGroup: issue.comparison_group,
    })),
    seriesMetadata: topic.series_metadata ? {
      dateBasis: topic.series_metadata.date_basis, unit: topic.series_metadata.unit,
      comparisonStatus: topic.series_metadata.comparison_status, coverageNote: topic.series_metadata.coverage_note,
      comparableSourceIds: topic.series_metadata.comparable_source_ids,
      topicMembershipOverlaps: topic.series_metadata.topic_membership_overlaps,
    } : undefined,
    editorialBrief: brief
      ? {
          title: brief.title,
          summary: brief.summary,
          whyItMatters: brief.why_it_matters,
          evidenceRecordIds: brief.evidence_record_ids,
          basisContentHash: brief.basis_content_hash,
          updatedAt: brief.updated_at,
        }
      : undefined,
  };
}
export function corpusOverviewView(response: FrontierOverviewResponse): FrontierCorpusOverview {
  const overview = response.overview;
  const distribution = (items: FrontierDistributionResponse[]) => items.map((item) => ({ key: item.key, label: item.label, count: item.count, recordIds: item.record_ids }));
  return {
    asOf: response.as_of, status: response.status,
    overview: overview ? {
      headline: overview.headline, summary: overview.summary,
      sections: overview.sections.map((section) => ({ id: section.id, title: section.title, statements: section.statements.map(statementView) })),
      scope: { stream: overview.scope.stream, coverageRecordIds: overview.scope.coverage_record_ids, analyzedRecordCount: overview.scope.analyzed_record_count, sourceCount: overview.scope.source_count, systematicReviewMethod: overview.scope.systematic_review_method },
      generatedBy: overview.generated_by, basisContentHash: overview.basis_content_hash,
      sourceHashes: overview.source_hashes.map((source) => ({ recordId: source.record_id, contentHash: source.content_hash })), updatedAt: overview.updated_at,
    } : null,
    statistics: { researchCount: response.statistics.research_count, practiceCount: response.statistics.practice_count,
      sourceDistribution: distribution(response.statistics.source_distribution), yearDistribution: distribution(response.statistics.year_distribution),
      topicDistribution: distribution(response.statistics.topic_distribution), methodDistribution: distribution(response.statistics.method_distribution), dataDistribution: distribution(response.statistics.data_distribution),
    },
  };
}
export interface FrontierApiSnapshot {
  records: FrontierRecordResponse[];
  topics: FrontierTopicPageResponse;
  sources: FrontierSourcePageResponse;
  status: FrontierStatusResponse;
  overview?: FrontierOverviewResponse;
}
export function datasetFromSnapshot(
  snapshot: FrontierApiSnapshot,
): FrontierDataset {
  return {
    records: snapshot.records.map(recordView),
    topics: snapshot.topics.items.map(topicView),
    sources: snapshot.sources.items.map((source) => ({
      id: source.source_id,
      name: source.name,
      status: source.status,
      lastSuccessAt: source.last_success_at,
    })),
    asOf: snapshot.topics.as_of,
    modelStatus: snapshot.status.extractor_status,
    corpusOverview: snapshot.overview ? corpusOverviewView(snapshot.overview) : undefined,
  };
}
// Lists never request full records. Detail-only fields stay empty until selection.
export function summaryView(record: FrontierRecordSummaryResponse): FrontierRecord {
  return {
    ...record, authors: record.authors ?? null, source_published_at: record.source_published_at ?? null,
    published_at: record.published_at ?? null, publication_year: record.publication_year ?? null,
    publication_issue: record.publication_issue ?? null, summary: record.summary ?? '',
    verification_note: '', editorial_caveat: '', research_question: record.research_question ?? null, methods: null,
    data: null, findings: record.findings ?? [], evidence: [], within_preferred_window: record.within_preferred_window ?? null,
  };
}
export interface FrontierListFilters {
  asOf?: string; query?: string; stream?: 'research' | 'practice'; sourceId?: string; sourceName?: string; topicId?: string; focus?: boolean; limit?: number; recordIds?: string[];
}
export async function readFrontierSummaries(filters: FrontierListFilters, offset = 0, signal?: AbortSignal) {
  const result = await listFrontierSummaries({ client: apiClient, signal, query: {
    as_of: filters.asOf, q: filters.query || undefined, stream: filters.stream,
    source_id: filters.sourceId || undefined, source_name: filters.sourceName || undefined, topic_id: filters.topicId || undefined, focus: filters.focus || undefined, record_ids: filters.recordIds, limit: filters.limit ?? 24, offset,
  } });
  if (!result.data) throw new Error('前沿资料服务暂时不可用，请稍后重试');
  const page = result.data;
  if (page.next_offset !== null && (page.next_offset <= offset || page.items.length === 0))
    throw new Error('前沿资料分页异常，请重试');
  return { records: page.items.map(summaryView), total: page.total, offset: page.offset,
    nextOffset: page.next_offset, asOf: page.as_of };
}
export async function readFrontierSources(signal?: AbortSignal) {
  const result = await listFrontierSources({ client: apiClient, signal });
  if (!result.data) throw new Error('来源暂时无法读取');
  return result.data.items.map(source => ({ id: source.source_id, name: source.name, status: source.status, lastSuccessAt: source.last_success_at }));
}
export async function readFrontierTopics(asOf: string, topicId?: string, signal?: AbortSignal) {
  const result = await listFrontierTopics({ client: apiClient, signal, query: { as_of: asOf, detail: Boolean(topicId), topic_id: topicId } });
  if (!result.data) throw new Error('议题暂时无法读取');
  return result.data.items.map(topicView);
}
export async function readFrontierOverview(asOf: string, signal?: AbortSignal) {
  const result = await getFrontierOverview({ client: apiClient, signal, query: { as_of: asOf } });
  if (!result.data) throw new Error('研究统计暂时无法读取');
  return corpusOverviewView(result.data);
}
export async function readFrontierRecord(recordId: string, asOf: string, signal?: AbortSignal) {
  const result = await getFrontierRecord({ client: apiClient, signal, path: { record_id: recordId }, query: { as_of: asOf } });
  if (result.response.status === 404) return null;
  if (!result.data) throw new Error('文献详情暂时无法读取');
  return recordView(result.data);
}

export function frontierPeriodQuery(topicKey: string, asOf: string, comparisonYear?: number) {
  const cutoff = new Date(`${asOf}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf) || Number.isNaN(cutoff.getTime()) || cutoff.toISOString().slice(0, 10) !== asOf)
    throw new Error("请选择有效统计日期");
  topicKey = topicKey.replace(/-research$/, "");
  if (topicKey.endsWith("-practice")) throw new Error("期次报告仅比较研究资料");
  if (comparisonYear !== undefined) {
    if (!Number.isInteger(comparisonYear) || comparisonYear < 1000 || comparisonYear >= cutoff.getUTCFullYear())
      throw new Error("请选择已结束的完整年度");
    return {
      previous_start: `${comparisonYear - 1}-01-01`, previous_end: `${comparisonYear - 1}-12-31`,
      current_start: `${comparisonYear}-01-01`, current_end: `${comparisonYear}-12-31`,
      topic_key: topicKey, as_of: asOf,
    };
  }
  const end = new Date(Date.UTC(cutoff.getUTCFullYear(), cutoff.getUTCMonth(), 0));
  const year = end.getUTCFullYear();
  return {
    previous_start: `${year - 1}-01-01`,
    previous_end: new Date(Date.UTC(year - 1, end.getUTCMonth() + 1, 0)).toISOString().slice(0, 10),
    current_start: `${year}-01-01`, current_end: end.toISOString().slice(0, 10),
    topic_key: topicKey, as_of: asOf,
  };
}
export async function readFrontierPeriod(topicKey: string, asOf: string, comparisonYear?: number, signal?: AbortSignal) {
  const result = await getFrontierPeriodReport({ client: apiClient, signal, query: frontierPeriodQuery(topicKey, asOf, comparisonYear) });
  if (!result.data) throw new Error("时期报告暂时无法读取");
  return result.data;
}
export async function readFrontierCalendar(asOf: string, signal?: AbortSignal) {
  const result = await getFrontierCalendar({ client: apiClient, signal, query: { year: Number(asOf.slice(0,4)), as_of: asOf }});
  if (!result.data) throw new Error("发表日历暂时无法读取");
  return result.data;
}
export async function readFrontierKnowledgeLinks(recordId: string) {
  const result = await getFrontierKnowledgeLinks({ client: apiClient, path: {record_id: recordId} });
  if (!result.data) throw new Error("知识阅读线索暂时无法读取");
  return result.data;
}
