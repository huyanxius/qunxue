export interface FrontierMedia {
  url: string;
  caption: string;
  source_url: string;
  kind: "figure" | "chart" | "article_photo" | "illustration";
  alt?: string | null;
}
export interface FrontierRecord {
  id: string;
  title: string;
  authors: string[] | null;
  source_name: string;
  source_publisher: string;
  source_published_at: string | null;
  published_at: string | null;
  published_at_display: string;
  publication_year: number | null;
  publication_issue: number | null;
  url: string;
  summary: string;
  why_read?: string | null;
  media?: FrontierMedia[];
  has_media?: boolean;
  topics: string[];
  verification_status: string;
  verification_note: string;
  editorial_caveat: string;
  research_question: string | null;
  methods: string | string[] | null;
  data: string | null;
  findings: string[];
  evidence: { snippet: string | null; locator: string; url: string }[];
  within_preferred_window: boolean | null;
}

export type FrontierKind = "all" | "research" | "practice";
export interface FrontierState {
  asOf?: string;
  query: string;
  kind: FrontierKind;
  source: string;
  topic: string;
  record: string;
  landingView?: "overview" | "topics" | "papers";
  topicView?: "overview" | "analysis" | "sources";
  limit: number;
}
export function readFrontierState(params: URLSearchParams): FrontierState {
  const kind = params.get("kind");
  const limit = Number(params.get("limit"));
  return {
    // Preserve explicit invalid values too: the connected page reports them
    // instead of silently replacing a requested historical date with today.
    ...(params.has("as_of") ? { asOf: params.get("as_of")! } : {}),
    query: params.get("q")?.trim().slice(0, 200) ?? "",
    kind: kind === "research" || kind === "practice" ? kind : "all",
    source: params.get("source") ?? "",
    topic: params.get("topic") ?? "",
    record: params.get("record") ?? "",
    ...(params.get("section") === "topics" || params.get("section") === "papers" ? { landingView: params.get("section") as "topics" | "papers" } : {}),
    ...(params.get("view") === "analysis" || params.get("view") === "sources" ? { topicView: params.get("view") as "analysis" | "sources" } : {}),
    limit: Number.isInteger(limit) && limit >= 6 && limit <= 10000 ? limit : 6,
  };
}
export function writeFrontierState(state: FrontierState): URLSearchParams {
  const params = new URLSearchParams({ scope: "frontier" });
  if (state.asOf !== undefined) params.set("as_of", state.asOf);
  if (state.query.trim()) params.set("q", state.query.trim().slice(0, 200));
  if (state.kind !== "all") params.set("kind", state.kind);
  if (state.source) params.set("source", state.source);
  if (state.topic) params.set("topic", state.topic);
  if (state.record) params.set("record", state.record);
  if (state.landingView && state.landingView !== "overview") params.set("section", state.landingView);
  if (state.topic && state.topicView && state.topicView !== "overview") params.set("view", state.topicView);
  if (state.limit > 6)
    params.set("limit", String(Math.min(state.limit, 10000)));
  return params;
}
export function filterFrontier(
  records: readonly FrontierRecord[],
  state: FrontierState,
) {
  const terms = state.query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return records
    .filter((record) => {
      if (record.verification_status === "review_queue") return false;
      if (
        state.kind === "research" &&
        !["lead_only", "verified_frontier"].includes(record.verification_status)
      )
        return false;
      if (
        state.kind === "practice" &&
        record.verification_status !== "practice_signal"
      )
        return false;
      if (state.source && record.source_name !== state.source) return false;
      if (state.topic && !record.topics.includes(state.topic)) return false;
      const haystack = [
        record.title,
        record.summary,
        record.research_question ?? "",
        record.source_name,
        ...(record.authors ?? []),
        ...record.topics,
      ]
        .join(" ")
        .toLocaleLowerCase();
      return terms.every((term) => haystack.includes(term));
    })
    .toSorted((a, b) => {
      // Prefer an explicitly known publication day. Otherwise use the source
      // page date, with the distinction kept visible in every result.
      const byDate = (
        b.published_at ??
        b.source_published_at ??
        ""
      ).localeCompare(a.published_at ?? a.source_published_at ?? "");
      return byDate || a.id.localeCompare(b.id);
    });
}
export function sourceDate(record: FrontierRecord) {
  if (record.published_at) return `发表 ${record.published_at}`;
  return record.source_published_at
    ? `来源更新 ${record.source_published_at}`
    : "来源更新日期未标明";
}
