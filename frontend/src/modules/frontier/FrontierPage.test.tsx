import { testDataset } from "./__fixtures__/catalog";
import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FrontierPage } from "./FrontierPage";
import { readFrontierState, type FrontierState } from "./model";

function Harness({ initial }: { initial?: Partial<FrontierState> }) {
  const [state, setState] = useState({
    ...readFrontierState(new URLSearchParams()),
    ...initial,
  });
  return (
    <FrontierPage
      data={testDataset}
      state={state}
      onStateChange={setState}
      onOpenLibrary={vi.fn()}
    />
  );
}
afterEach(cleanup);
describe("frontier feed", () => {
  it("paginates real articles and preserves filters across details", () => {
    render(<Harness />);
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: /再看 6 条资料/ }));
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(12);
    expect(screen.getAllByText(/旧刊补充/)).toHaveLength(1);
    const scroll = document.querySelector(".frontier-scroll")!;
    fireEvent.scroll(scroll, { target: { scrollTop: 650 } });
    const first = within(
      screen.getByRole("region", { name: /最新收录|筛选结果/ }),
    ).getAllByRole("article")[0];
    fireEvent.click(
      within(first).getByRole("heading").querySelector("button")!,
    );
    expect(
      screen.getByText("来源信息"),
    ).toBeVisible();
    expect(scroll.scrollTop).toBe(0);
    expect(
      screen.getAllByRole("link", { name: "阅读原始来源" })[0],
    ).toHaveAttribute("rel", "noopener noreferrer");
    fireEvent.click(screen.getByRole("button", { name: "返回资料列表" }));
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(12);
    expect(scroll.scrollTop).toBe(650);
  });
  it("searches and recovers cleanly from an empty result", () => {
    render(<Harness />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "不可能找到的词abcdef" },
    });
    fireEvent.submit(screen.getByRole("search"));
    expect(
      screen.getByRole("heading", { name: "没有匹配的资料" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "查看全部" }));
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(6);
  });
  it("filters practice records without treating them as verified research", () => {
    render(<Harness />);
    fireEvent.click(
      within(screen.getByLabelText("资料类型")).getByRole("button", {
        name: "实践观察",
      }),
    );
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(3);
    expect(screen.queryByText("研究结论已验证")).not.toBeInTheDocument();
  });
  it("recovers from an unknown record URL", () => {
    render(<Harness initial={{ record: "missing-id" }} />);
    expect(
      screen.getByRole("heading", { name: "未找到这条资料" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "返回资料列表" }));
    expect(
      within(
        screen.getByRole("region", { name: /最新收录|筛选结果/ }),
      ).getAllByRole("article"),
    ).toHaveLength(6);
  });
});

it("uses shared library presentation with compact topic filters and no second navigation rail", () => {
  const { container } = render(<Harness />);
  expect(container.querySelector('.knowledge-library.frontier')).toBeInTheDocument();
  expect(container.querySelector('.knowledge-library__sidebar')).not.toBeInTheDocument();
  expect(container.querySelector('.knowledge-library__topbar .knowledge-library__search')).toBeInTheDocument();
  expect(screen.getByLabelText('筛选议题')).toBeVisible();
  expect(container.querySelector('.knowledge-library__main .knowledge-library__topbar')).toBeInTheDocument();
  expect(container.querySelectorAll('.knowledge-explorer__result-list > li')).toHaveLength(6);
  expect(container.querySelector('.frontier-news-grid, .frontier-card, .frontier-header')).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: '知识库栏目' })).not.toBeInTheDocument();
  expect(screen.queryByText('前沿消息')).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox', { name: /AI/ })).not.toBeInTheDocument();
});

it("retains expandable source information after filtering", () => {
  render(<Harness />);
  fireEvent.click(within(screen.getByLabelText('资料类型')).getByRole('button', { name: /实践观察/ }));
  fireEvent.click(screen.getAllByRole('button', { name: /^查看 / })[0]);
  const evidence = screen.getByText('来源信息').closest('details')!;
  expect(evidence).not.toHaveAttribute('open');
  fireEvent.click(screen.getByText('来源信息'));
  expect(evidence).toHaveAttribute('open');
});

it("keeps cross-paper briefs, topic evidence and source filters functional in the library layout", () => {
  const evidenceRecords = testDataset.records.slice(0, 2);
  const topic = {
    id: 'research:organizations', key: 'organizations', title: '组织研究', stream: 'research' as const,
    recordIds: evidenceRecords.map((record) => record.id), sourceIds: ['source-a', 'source-b'], sourceDistribution: {}, summary: '',
    counts: { total: 2, dated: 1, undated: 1, days30: 1, days90: 1, days180: 1, previous90: 0 },
    trendStatus: 'insufficient_evidence' as const, trendSignals: [], growthBaseline: null, reasons: ['历史覆盖不足'],
    editorialBrief: { title: '组织边界的新变化', summary: '两项研究共同讨论协作关系如何重塑组织边界。', whyItMatters: '从不同案例对照组织机制。', evidenceRecordIds: evidenceRecords.map((record) => record.id), basisContentHash: 'test', updatedAt: '2026-10-01' },
  };
  function TopicHarness() {
    const [state, setState] = useState(readFrontierState(new URLSearchParams()));
    return <FrontierPage data={{ ...testDataset, topics: [topic] }} state={state} onStateChange={setState} onOpenLibrary={vi.fn()} />;
  }
  render(<TopicHarness />);
  expect(screen.getByText(topic.editorialBrief.summary)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '分析 组织研究' }));
  expect(screen.getByText(topic.editorialBrief.whyItMatters)).toBeVisible();
  fireEvent.click(screen.getByRole('tab', { name: '文献' }));
  const results = screen.getByRole('region', { name: '筛选结果' });
  expect(within(results).getAllByRole('article')).toHaveLength(2);
  expect(within(results).queryByText(topic.id)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('筛选来源'), { target: { value: evidenceRecords[0].source_name } });
  expect(within(results).getAllByRole('article')).toHaveLength(evidenceRecords.filter((record) => record.source_name === evidenceRecords[0].source_name).length);
  expect(screen.queryByText('收录语料呈现增长信号')).not.toBeInTheDocument();
});

it("renders the abstract as the main content without empty findings or internal audit boilerplate", () => {
  const record = { ...testDataset.records[0], findings: [], verification_note: '内部核验过程说明', editorial_caveat: '不可作为学科总体趋势', evidence: [{ snippet: '短截取片段', locator: '#art669 .j-abstract / 前22个Unicode字符', url: testDataset.records[0].url }] };
  render(<FrontierPage data={{ ...testDataset, records: [record] }} state={{ ...readFrontierState(new URLSearchParams()), record: record.id }} onStateChange={vi.fn()} onOpenLibrary={vi.fn()} />);
  expect(screen.getByRole('heading', { name: '摘要' })).toBeVisible();
  expect(screen.getByText(record.summary)).toBeVisible();
  expect(screen.queryByRole('heading', { name: '主要发现' })).not.toBeInTheDocument();
  expect(screen.queryByText(record.verification_note)).not.toBeInTheDocument();
  expect(screen.queryByText(record.evidence[0].locator)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText('来源信息'));
  expect(screen.getByText('内容依据：摘要或官方研究简介')).toBeVisible();
});
