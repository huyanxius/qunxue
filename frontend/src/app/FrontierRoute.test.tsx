import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppRoutes } from "./App";
import type { FrontierDataset } from "../modules/frontier";

// Minimal route-only data: the module's production entry never exposes seeds.
const routeDataset: FrontierDataset = {
  records: [{
    id: "route-test-outsourcing",
    title: "“组织内外包”：新药临床试验的组织管理模式研究",
    authors: null,
    source_name: "测试来源",
    source_publisher: "测试出版方",
    source_published_at: "2026-09-01",
    published_at: null,
    published_at_display: "2026年第4期",
    publication_year: 2026,
    publication_issue: 4,
    url: "https://example.com/route-test",
    summary: "用于路由测试的企业协作研究线索",
    topics: ["组织社会学"],
    verification_status: "lead_only",
    verification_note: "路由测试数据",
    editorial_caveat: "测试条目，不是研究证据",
    research_question: null,
    methods: null,
    data: null,
    findings: [],
    evidence: [],
    within_preferred_window: null,
  }],
  topics: [],
  sources: [],
  asOf: "2026-10-01",
  modelStatus: "not_configured",
};
const readDataset = vi.hoisted(() => vi.fn());
vi.mock("../modules/frontier/frontierApi", () => ({
  readFrontierDataset: readDataset,
  readFrontierCalendar: vi.fn(async () => null),
  readFrontierPeriod: vi.fn(async () => null),
}));
vi.mock("../modules/frontier/FrontierRecordInsights", () => ({ FrontierRecordInsights: () => null }));
beforeEach(() => readDataset.mockResolvedValue(routeDataset));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function HistoryControls() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <>
      <button onClick={() => navigate(-1)}>测试后退</button>
      <button onClick={() => navigate(1)}>测试前进</button>
      <output data-testid="location">{location.search}</output>
    </>
  );
}
it("keeps the frontier route offline and restores query and detail through browser history", async () => {
  const fetchMock = vi.fn(() =>
    Promise.reject(new Error("Unexpected network call")),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/knowledge?scope=frontier"]}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AppRoutes sessionState={{ status: "anonymous" }} />
        <HistoryControls />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  const searchbox = await screen.findByRole("searchbox");
  expect(screen.getByRole("heading", { name: "10月1日", level: 1 })).toBeVisible();
  expect(screen.queryByRole("navigation", { name: "知识库栏目" })).not.toBeInTheDocument();
  const navigation = within(screen.getByRole("navigation", { name: "桌面主导航" }));
  expect(navigation.getByRole("button", { name: "知识库" })).toHaveAttribute("aria-expanded", "true");
  expect(navigation.getByRole("link", { name: "学术前沿" })).toHaveAttribute("aria-current", "page");
  // The connected page mounts after an asynchronous dataset read. Flush the
  // controlled input update before submitting, including React's pending effects.
  await act(async () => {
    fireEvent.change(searchbox, { target: { value: "企业" } });
  });
  expect(searchbox).toHaveValue("企业");
  await act(async () => {
    fireEvent.submit(screen.getByRole("search"));
  });
  await waitFor(() =>
    expect(screen.getByTestId("location")).toHaveTextContent("q="),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "查看 “组织内外包”：新药临床试验的组织管理模式研究",
    }),
  );
  expect(
    await screen.findByText("来源信息"),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "测试后退" }));
  await waitFor(() =>
    expect(screen.getByRole("searchbox")).toHaveValue("企业"),
  );
  fireEvent.click(screen.getByRole("button", { name: "测试前进" }));
  expect(
    await screen.findByText("来源信息"),
  ).toBeVisible();
  expect(fetchMock).not.toHaveBeenCalled();
});
