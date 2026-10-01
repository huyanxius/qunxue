import { afterEach, expect, it, vi } from 'vitest';
import { readRecordInsights, readReadingPriorities } from './readingInsightsApi';

afterEach(() => vi.unstubAllGlobals());
it('sends the same historical cutoff through the real generated SDK for both detail endpoints', async () => {
  const requested: string[] = [];
  vi.stubGlobal('fetch', async (request: Request) => {
    requested.push(request.url);
    return new Response(JSON.stringify({ detail: 'missing' }), { status: 404,
      headers: { 'Content-Type': 'application/json' } });
  });
  await expect(readRecordInsights('paper@v2', '2024-12-31')).rejects.toThrow('暂时无法读取');
  expect(requested).toHaveLength(2);
  for (const url of requested) {
    expect(new URL(url).searchParams.get('as_of')).toBe('2024-12-31');
    expect(decodeURIComponent(new URL(url).pathname)).toContain('/records/paper@v2/');
  }
});
it('preserves value and readiness filters through the real generated SDK', async () => {
  let requested: URL | undefined;
  vi.stubGlobal('fetch', async (request: Request) => {
    requested = new URL(request.url);
    return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 24,
      next_offset: null, as_of: '2026-10-01', sort_basis: 'evidence_readiness' }),
      { headers: { 'Content-Type': 'application/json' } });
  });
  const page = await readReadingPriorities({ readiness: 'abstract_supported', minAcademicValue: 50,
    assessmentStatus: 'assessed', asOf: '2026-10-01' });
  expect(page.total).toBe(0);
  expect(requested?.searchParams.get('min_academic_value')).toBe('50');
  expect(requested?.searchParams.get('assessment_status')).toBe('assessed');
  expect(requested?.searchParams.get('readiness')).toBe('abstract_supported');
});
