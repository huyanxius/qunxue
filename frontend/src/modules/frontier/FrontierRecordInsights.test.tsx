import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FrontierRecordInsights } from './FrontierRecordInsights';

function payloads(version: number, linkVersion = version) {
  const priority = { record_id: 'paper', title: 'Paper', version,
    content_hash: `hash-${version}`, reading_rule_version: 'test', reading_priority: 'abstract_supported',
    evidence_readiness: 'abstract', supported_fields: [], missing_fields: {}, basis: [],
    assessment: { status: 'unassessed', academic_value: null, rule_version: 'test', criteria: {},
      track: null, ratings: {}, score_bounds: { lower: 0, upper: 100 }, missing_reasons: {},
      evidence_readiness: 'abstract', priority: null, authorizes_publication: false }, limitations: [] };
  const links = { record_id: 'paper', record_version: linkVersion, record_content_hash: `hash-${linkVersion}`,
    knowledge_release_id: null, knowledge_release_hash: null, knowledge_release_level: null,
    status: 'no_release', match_basis: 'topic_lexical_retrieval', relationship: 'reading_lead', matches: [], limitations: [] };
  return { priority, links };
}
function response(request: Request, version: number, linkVersion = version) {
  const data = payloads(version, linkVersion);
  return new Response(JSON.stringify(new URL(request.url).pathname.endsWith('/reading-priority') ? data.priority : data.links),
    { headers: { 'Content-Type': 'application/json' } });
}
function mount(client: QueryClient) {
  return render(<QueryClientProvider client={client}><FrontierRecordInsights recordId="paper" asOf="2026-10-01"/></QueryClientProvider>);
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('rejects cross-version details and offers a manual refresh', async () => {
  vi.stubGlobal('fetch', async (request: Request) => response(request, 1, 2));
  mount(new QueryClient());
  expect(await screen.findByRole('alert')).toBeVisible();
  expect(screen.queryByRole('heading', { name: '知识阅读线索' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '刷新阅读依据' })).toBeVisible();
});
it('reuses matching cached evidence when reopening and refreshes only on request', async () => {
  let version = 1;
  const fetchMock = vi.fn(async (request: Request) => response(request, version));
  vi.stubGlobal('fetch', fetchMock);
  const client = new QueryClient();
  const first = mount(client);
  expect(await screen.findByText(/文献版本 1/)).toBeVisible();
  first.unmount();
  version = 2;
  mount(client);
  expect(screen.getByText(/文献版本 1/)).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', { name: '刷新阅读依据' }));
  expect(await screen.findByText(/文献版本 2/)).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(4);
});
