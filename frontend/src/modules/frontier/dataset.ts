import type { FrontierRecord } from "./model";

export interface FrontierEvidenceStatement {
  text: string;
  evidenceRecordIds: string[];
}
export interface FrontierResearchBrief {
  headline: string;
  development: FrontierEvidenceStatement | null;
  consensus: FrontierEvidenceStatement[];
  differences: FrontierEvidenceStatement[];
  methods: FrontierEvidenceStatement[];
  researchImplication: FrontierEvidenceStatement | null;
  priorityReads: { recordId: string; reason: string }[];
  evidenceRecordIds: string[];
  generatedBy: string;
  basisContentHash: string;
  updatedAt: string;
}
export interface FrontierMonth {
  month: string;
  recordCount: number;
  datedRecordIds: string[];
  sourceIds: string[];
  coverageComplete: boolean;
  observationBasis: string;
  isPartialMonth?: boolean;
  denominator?: number;
  sampleShare?: number | null;
  normalizedShare?: number | null;
}
export interface FrontierIssue {
  issueId: string;
  label: string;
  sourceId: string;
  publicationMonth: string;
  candidateCount: number;
  readableCount: number;
  includedCount: number;
  denominator: number;
  topicRecordCount: number;
  share: number | null;
  coverageComplete: boolean;
  evidenceRecordIds: string[];
  denominatorRecordIds: string[];
  issueUrl: string;
  comparisonGroup: string;
}
export interface FrontierTopic {
  id: string;
  key: string;
  title: string;
  stream: "research" | "practice";
  recordIds: string[];
  sourceIds: string[];
  sourceDistribution: Record<string, number>;
  summary: string;
  counts: {
    total: number;
    dated: number;
    undated: number;
    days30: number;
    days90: number;
    days180: number;
    previous90: number;
  };
  trendStatus: "insufficient_evidence" | "supported";
  trendSignals: string[];
  growthBaseline: number | null;
  reasons: string[];
  researchBrief?: FrontierResearchBrief;
  monthlySeries?: FrontierMonth[];
  issueSeries?: FrontierIssue[];
  seriesMetadata?: {
    dateBasis: string;
    unit: string;
    comparisonStatus: string;
    coverageNote: string;
    comparableSourceIds: string[];
    topicMembershipOverlaps: boolean;
  };
  editorialBrief?: {
    title: string;
    summary: string;
    whyItMatters: string;
    evidenceRecordIds: string[];
    basisContentHash: string;
    updatedAt: string;
  };
}
export interface FrontierDataset {
  records: readonly FrontierRecord[];
  topics: readonly FrontierTopic[];
  sources: readonly {
    id: string;
    name: string;
    status: string;
    lastSuccessAt: string | null;
  }[];
  asOf: string;
  modelStatus: string;
  corpusOverview?: FrontierCorpusOverview;
}

export interface FrontierCorpusDistribution {
  key: string;
  label: string;
  count: number;
  recordIds: string[];
}
export interface FrontierCorpusOverview {
  asOf: string;
  status: 'ready' | 'not_configured' | 'stale';
  overview: {
    headline: string;
    summary: string;
    sections: { id: string; title: string; statements: FrontierEvidenceStatement[] }[];
    scope: { stream: 'research'; coverageRecordIds: string[]; analyzedRecordCount: number; sourceCount: number; systematicReviewMethod: string };
    generatedBy: string;
    basisContentHash: string;
    sourceHashes: { recordId: string; contentHash: string }[];
    updatedAt: string;
  } | null;
  statistics: {
    researchCount: number;
    practiceCount: number;
    sourceDistribution: FrontierCorpusDistribution[];
    yearDistribution: FrontierCorpusDistribution[];
    topicDistribution: FrontierCorpusDistribution[];
    methodDistribution: FrontierCorpusDistribution[];
    dataDistribution: FrontierCorpusDistribution[];
  };
}
