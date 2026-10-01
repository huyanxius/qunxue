import { beforeEach, describe, expect, it, vi } from "vitest";
import { frontierRecords } from "./__fixtures__/catalog";
import { readFrontierDataset, topicView, corpusOverviewView } from "./frontierApi";
const sdk = vi.hoisted(() => ({
  searchFrontierRecords: vi.fn(),
  listFrontierTopics: vi.fn(),
  listFrontierSources: vi.fn(),
  getFrontierStatus: vi.fn(),
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
describe("persistent frontier adapter", () => {
  it("loads all pages and deduplicates IDs without any model dependency", async () => {
    sdk.searchFrontierRecords
      .mockResolvedValueOnce({
        data: { items: [{ ...frontierRecords[0], why_read: "从组织机制理解研究问题。", media: [{ url: "https://publisher.example/figure.png", caption: "研究机制图", source_url: "https://publisher.example/paper", kind: "figure" }] }, ...frontierRecords.slice(1, 6)], next_offset: 6 },
      })
      .mockResolvedValueOnce({
        data: { items: frontierRecords.slice(5), next_offset: null },
      });
    const result = await readFrontierDataset();
    expect(result.records).toHaveLength(12);
    expect(result.records[0].why_read).toBe("从组织机制理解研究问题。");
    expect(result.records[0].media?.[0]).toMatchObject({ url: "https://publisher.example/figure.png", kind: "figure", caption: "研究机制图" });
    expect(result.modelStatus).toBe("not_configured");
    expect(sdk.searchFrontierRecords).toHaveBeenLastCalledWith({
      client: {},
      query: { limit: 200, offset: 6, as_of: "2026-10-01" },
    });
  });
  it("reports an unavailable service rather than showing seed records as live data", async () => {
    sdk.listFrontierTopics.mockResolvedValue({ data: undefined });
    await expect(readFrontierDataset()).rejects.toThrow(
      "前沿资料服务暂时不可用",
    );
    expect(sdk.searchFrontierRecords).not.toHaveBeenCalled();
  });
  it("stops invalid pagination instead of looping forever", async () => {
    sdk.searchFrontierRecords.mockResolvedValue({
      data: { items: frontierRecords.slice(0, 1), next_offset: 0 },
    });
    await expect(readFrontierDataset()).rejects.toThrow("分页异常");
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
