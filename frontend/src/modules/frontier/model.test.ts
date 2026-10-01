import { frontierRecords } from "./__fixtures__/catalog";
import { describe, expect, it } from "vitest";
import {
  filterFrontier,
  readFrontierState,
  sourceDate,
  writeFrontierState,
} from "./model";

const empty = readFrontierState(new URLSearchParams());
it.each(['2024-02-29', '2026-02-30', 'not-a-date', '', '9999-12-31'])('preserves explicit URL reading date %s for validation without replacing it', asOf => {
  const state = readFrontierState(new URLSearchParams({ as_of: asOf }));
  expect(state.asOf).toBe(asOf);
  expect(readFrontierState(writeFrontierState(state))).toEqual(state);
});
it('leaves the reading date absent when the URL has no historical date', () => {
  expect(readFrontierState(new URLSearchParams()).asOf).toBeUndefined();
  expect(writeFrontierState(empty).has('as_of')).toBe(false);
});
describe("frontier source catalog", () => {
  it("ships real traceable records without upgrading abstracts into verified evidence", () => {
    expect(frontierRecords).toHaveLength(12);
    expect(new Set(frontierRecords.map((record) => record.id)).size).toBe(12);
    for (const record of frontierRecords) {
      expect(new URL(record.url).protocol).toBe("https:");
      expect(record.evidence.length).toBeGreaterThan(0);
      expect(record.verification_note).toBeTruthy();
      if (record.verification_status === "lead_only")
        expect(record.published_at).toBeNull();
    }
  });
  it("combines keyword, source, type and topic filtering", () => {
    const matches = filterFrontier(frontierRecords, {
      ...empty,
      query: "养老",
      kind: "research",
      source: "社会学研究",
      topic: "老龄化",
    });
    expect(matches.length).toBeGreaterThan(0);
    expect(matches.every((record) => record.source_name === "社会学研究")).toBe(
      true,
    );
    expect(
      filterFrontier(frontierRecords, { ...empty, query: "企业" }).some(
        (record) => record.id.includes("outsourcing"),
      ),
    ).toBe(true);
    expect(
      filterFrontier(frontierRecords, { ...empty, kind: "practice" }),
    ).toHaveLength(3);
    expect(
      filterFrontier(frontierRecords, {
        ...empty,
        query: "不存在的主题abcdef",
      }),
    ).toEqual([]);
  });
  it("uses source dates for ordering and keeps unknown dates explicit", () => {
    const sorted = filterFrontier(frontierRecords, empty);
    expect(sorted[0].source_published_at).toBe("2026-09-30");
    expect(sourceDate(sorted.at(-1)!)).toBe("来源更新日期未标明");
    expect(
      frontierRecords.some((record) => !record.within_preferred_window),
    ).toBe(true);
  });
  it("round trips filters, selection and paging in the URL", () => {
    const state = {
      ...empty,
      query: "社会治理",
      kind: "practice" as const,
      source: "中国社会工作报",
      topic: "社区治理",
      record: "test-id",
      limit: 12,
    };
    expect(readFrontierState(writeFrontierState(state))).toEqual(state);
    expect(writeFrontierState(state).get("scope")).toBe("frontier");
  });
  it("bounds invalid paging and untrusted filter type", () => {
    expect(
      readFrontierState(new URLSearchParams("kind=bad&limit=99999")).kind,
    ).toBe("all");
    expect(readFrontierState(new URLSearchParams("limit=-1")).limit).toBe(6);
  });
});

it("keeps more than 150 records reachable through pagination URLs", () => {
  const state = { ...empty, limit: 201 };
  expect(readFrontierState(writeFrontierState(state)).limit).toBe(201);
});
