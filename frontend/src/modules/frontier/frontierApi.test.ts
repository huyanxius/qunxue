import { beforeEach, describe, expect, it, vi } from "vitest";
import { frontierRecords } from "./__fixtures__/catalog";
import { readFrontierSummaries, readFrontierRecord, readFrontierTopics, readFrontierPeriod, readFrontierCalendar, readFrontierKnowledgeLinks, topicView, corpusOverviewView } from "./frontierApi";
const sdk = vi.hoisted(() => ({
  listFrontierSummaries: vi.fn(),
  getFrontierRecord: vi.fn(),
  listFrontierTopics: vi.fn(),
  listFrontierSources: vi.fn(),
  getFrontierStatus: vi.fn(),
  getFrontierCalendar: vi.fn(),
  getFrontierPeriodReport: vi.fn(),
  getFrontierKnowledgeLinks: vi.fn(),
  getFrontierOverview: vi.fn(),
}));
vi.mock("../../api/generated/sdk.gen", () => sdk);
vi.mock("../../api/client", () => ({ apiClient: {} }));
beforeEach(() => {
  vi.clearAllMocks();
  sdk.getFrontierOverview.mockResolvedValue({ data: undefined });
  sdk.listFrontierTopics.mockResolvedValue({
    data: { items: [], as_of: "2026-10-01" },
  });
  sdk.listFrontierSources.mockResolvedValue({ data: { items: [] } });
  sdk.getFrontierStatus.mockResolvedValue({
    data: { extractor_status: "not_configured" },
  });
});
describe("lightweight frontier adapter", () => {
  it("requests only one 24-record summary page with server filters and cancellation", async () => {
    const signal = new AbortController().signal;
    sdk.listFrontierSummaries.mockResolvedValue({ data: { items: [{ ...frontierRecords[0], source_id: 'journal' }], total: 50, offset: 0, next_offset: 24, as_of: '2026-10-01' } });
    const result = await readFrontierSummaries({ asOf: '2026-10-01', query: '养老', stream: 'research', sourceId: 'journal', topicId: 'care-research' }, 0, signal);
    expect(result).toMatchObject({ total: 50, nextOffset: 24, asOf: '2026-10-01' });
    expect(result.records[0]).toMatchObject({ findings: frontierRecords[0].findings, evidence: [], research_question: frontierRecords[0].research_question });
    expect(sdk.listFrontierSummaries).toHaveBeenCalledExactlyOnceWith({ client: {}, signal, query: { q: '养老', stream: 'research', source_id: 'journal', source_name: undefined, topic_id: 'care-research', focus: undefined, record_ids: undefined, limit: 24, offset: 0, as_of: '2026-10-01' } });
    expect(sdk.getFrontierRecord).not.toHaveBeenCalled();
    expect(sdk.listFrontierTopics).not.toHaveBeenCalled();
    expect(sdk.getFrontierOverview).not.toHaveBeenCalled();
  });
  it("does not substitute seed records or accept a broken next-page pointer", async () => {
    sdk.listFrontierSummaries.mockResolvedValueOnce({ data: undefined });
    await expect(readFrontierSummaries({})).rejects.toThrow('前沿资料服务暂时不可用');
    sdk.listFrontierSummaries.mockResolvedValueOnce({ data: { items: [frontierRecords[0]], next_offset: 24 } });
    await expect(readFrontierSummaries({}, 24)).rejects.toThrow('分页异常');
  });
  it("loads topic detail only when explicitly selected", async () => {
    const signal = new AbortController().signal;
    await readFrontierTopics('2026-10-01', undefined, signal);
    expect(sdk.listFrontierTopics).toHaveBeenLastCalledWith({ client: {}, signal, query: { as_of: '2026-10-01', detail: false, topic_id: undefined } });
    await readFrontierTopics('2026-10-01', 'care-research', signal);
    expect(sdk.listFrontierTopics).toHaveBeenLastCalledWith({ client: {}, signal, query: { as_of: '2026-10-01', detail: true, topic_id: 'care-research' } });
  });
  it("requests one historical record and distinguishes unavailable from missing", async () => {
    const signal = new AbortController().signal;
    sdk.getFrontierRecord.mockResolvedValueOnce({ data: frontierRecords[0], response: { status: 200 } });
    expect((await readFrontierRecord('one', '2026-09-28', signal))?.id).toBe(frontierRecords[0].id);
    expect(sdk.getFrontierRecord).toHaveBeenLastCalledWith({ client: {}, signal, path: { record_id: 'one' }, query: { as_of: '2026-09-28' } });
    sdk.getFrontierRecord.mockResolvedValueOnce({ response: { status: 404 } });
    expect(await readFrontierRecord('gone', '2026-09-28')).toBeNull();
    sdk.getFrontierRecord.mockResolvedValueOnce({ response: { status: 503 } });
    await expect(readFrontierRecord('one', '2026-09-28')).rejects.toThrow('文献详情暂时无法读取');
  });
});

it('maps grounded research briefs and dated series without losing citation IDs or coverage status', () => {
  const topic: Parameters<typeof topicView>[0] = {
    id: 'research:care', topic_key: 'care', title: '照护关系', stream: 'research', record_ids: ['paper-1'], source_ids: ['journal'], source_distribution: { journal: 1 }, summary: '', summary_method: 'editorial', method: 'offline', novelty_status: 'known', evidence: [], growth_baseline: null, reasons: [], trend_status: 'insufficient_evidence', trend_signals: [], time_windows: {},
    counts: { total: 1, dated: 1, undated: 0, future_dated: 0, days_30: 1, days_90: 1, days_180: 1, previous_90: 0, prior_90_for_growth: 0, prior_90_for_persistence: 0 },
    research_brief: { headline: '照护中的角色形成', development: { text: '角色在互动中形成。', evidence_record_ids: ['paper-1'] }, research_implication: { text: '关注责任如何组织。', evidence_record_ids: ['paper-1'] }, priority_reads: [{ record_id: 'paper-1', reason: '先理解研究对象。' }], evidence_record_ids: ['paper-1'], generated_by: 'offline_editorial', basis_content_hash: 'hash', updated_at: '2026-10-01' },
    monthly_series: [{ month: '2026-10', record_count: 1, dated_record_ids: ['paper-1'], source_ids: ['journal'], coverage_complete: false, observation_basis: 'sample', is_partial_month: true, denominator: 3, denominator_record_ids: ['paper-1', 'paper-2', 'paper-3'], denominator_source_ids: ['journal'], sample_share: 1 / 3, normalized_share: null }],
    issue_series: [{ issue_id: 'journal:4', label: '2026年第4期', source_id: 'journal', publication_month: '2026-08', candidate_count: 3, readable_count: 3, included_count: 3, denominator: 3, topic_record_count: 1, share: 1 / 3, coverage_complete: true, evidence_record_ids: ['paper-1'], denominator_record_ids: ['paper-1', 'paper-2', 'paper-3'], issue_url: 'https://example.org/issue/4', comparison_group: 'journal' }],
    series_metadata: { date_basis: 'exact_publication_date', unit: 'deduplicated_records', comparison_status: 'sample_distribution_only', coverage_note: 'partial', comparable_source_ids: [], topic_membership_overlaps: true },
  };
  const view = topicView(topic);
  expect(view.researchBrief?.development).toEqual({ text: '角色在互动中形成。', evidenceRecordIds: ['paper-1'] });
  expect(view.researchBrief?.consensus).toEqual([]);
  expect(view.researchBrief?.priorityReads[0]).toEqual({ recordId: 'paper-1', reason: '先理解研究对象。' });
  expect(view.monthlySeries?.[0]).toMatchObject({ isPartialMonth: true, coverageComplete: false, normalizedShare: null });
  expect(view.issueSeries?.[0]).toMatchObject({ share: 1 / 3, coverageComplete: true, denominatorRecordIds: ['paper-1', 'paper-2', 'paper-3'] });
});

it('maps a full-corpus overview with exact coverage, references and statistic membership', () => {
  const response: Parameters<typeof corpusOverviewView>[0] = {
    as_of: '2026-10-01', status: 'ready', overview: {
      headline: '跨论文总述', summary: '由全量研究形成的实质总结', sections: [{ id: 'shared_focus', title: '共性关注', statements: [{ text: '制度与关系共同塑造参与。', evidence_record_ids: ['r1'] }] }],
      scope: { stream: 'research', coverage_record_ids: ['r1', 'r2'], analyzed_record_count: 2, source_count: 1, systematic_review_method: 'all_records' },
      generated_by: 'assistant_evidence_synthesis', evidence_record_ids: ['r1'], basis_content_hash: 'hash', source_hashes: [{ record_id: 'r1', content_hash: 'a' }, { record_id: 'r2', content_hash: 'b' }], updated_at: '2026-10-01',
    },
    statistics: { research_count: 2, practice_count: 1, source_distribution: [], year_distribution: [], topic_distribution: [], method_distribution: [{ key: 'field', label: '实地调查', count: 1, record_ids: ['r1'] }], data_distribution: [], classification_method: 'record_fields', overlapping_categories: true },
  };
  const result = corpusOverviewView(response);
  expect(result.overview?.scope.coverageRecordIds).toEqual(['r1', 'r2']);
  expect(result.overview?.sections[0].statements[0].evidenceRecordIds).toEqual(['r1']);
  expect(result.statistics.methodDistribution[0].recordIds).toEqual(['r1']);
  expect(result.statistics.practiceCount).toBe(1);
});

it("loads real calendar, period report and read-only knowledge leads through the SDK", async () => {
  sdk.getFrontierCalendar.mockResolvedValue({data:{year:2026,days:[]}});
  sdk.getFrontierPeriodReport.mockResolvedValue({data:{current_share:null,semantic_status:"not_assessed"}});
  sdk.getFrontierKnowledgeLinks.mockResolvedValue({data:{record_id:"r",matches:[]}});
  expect((await readFrontierCalendar("2026-01-20")).year).toBe(2026);
  expect((await readFrontierPeriod("youth-research","2026-01-20")).current_share).toBeNull();
  expect((await readFrontierKnowledgeLinks("r")).record_id).toBe("r");
  expect(sdk.getFrontierCalendar).toHaveBeenCalledWith({client:{},signal:undefined,query:{year:2026,as_of:"2026-01-20"}});
  expect(sdk.getFrontierPeriodReport.mock.calls[0][0].query).toMatchObject({topic_key:"youth",as_of:"2026-01-20",previous_start:"2024-01-01",current_start:"2025-01-01",previous_end:"2024-12-31",current_end:"2025-12-31"});
  expect(sdk.getFrontierKnowledgeLinks.mock.calls[0][0].path).toEqual({record_id:"r"});
});

it('requests explicit complete annual windows for a real topic ID and historical cutoff', async () => {
  sdk.getFrontierPeriodReport.mockResolvedValue({data:{comparability:'complete_common_cohort',coverage_scope:'fixed_issue_sample'}});
  await readFrontierPeriod('organization-research', '2026-01-20', 2024);
  expect(sdk.getFrontierPeriodReport.mock.calls[0][0].query).toEqual({
    previous_start:'2023-01-01', previous_end:'2023-12-31',
    current_start:'2024-01-01', current_end:'2024-12-31',
    topic_key:'organization', as_of:'2026-01-20',
  });
});

it('does not accept an open comparison year or malformed as_of', async () => {
  await expect(readFrontierPeriod('organization-research', '2026-01-20', 2026)).rejects.toThrow();
  await expect(readFrontierPeriod('organization-research', '2026-02-30', 2024)).rejects.toThrow();
  expect(sdk.getFrontierPeriodReport).not.toHaveBeenCalled();
});
