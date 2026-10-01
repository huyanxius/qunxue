import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { FrontierReadingPriority } from './FrontierReadingPriority';
import { FrontierKnowledgeLinks } from './FrontierKnowledgeLinks';
import { readingPriorityView, knowledgeLinksView } from './readingInsightsApi';
type FrontierReadingPriorityResponse = Parameters<typeof readingPriorityView>[0];
type FrontierKnowledgeLinksResponse = Parameters<typeof knowledgeLinksView>[0];

afterEach(cleanup);
const priority: FrontierReadingPriorityResponse = {
  record_id: 'paper', title: '论文', version: 2, content_hash: 'sha256:paper',
  reading_rule_version: 'test', reading_priority: 'abstract_supported', evidence_readiness: 'abstract',
  supported_fields: ['research_question'], missing_fields: { methods: '未核验研究方法' },
  basis: [{ basis_type: 'located_source_excerpt', source_content_hash: 'sha256:source', block_id: 'b1', locator: '摘要第一段', url: 'https://publisher.example/article', snippet: '研究问题摘录', fields: ['research_question'] }],
  assessment: { rule_version: 'test', track: null, status: 'unassessed', ratings: {}, criteria: {},
    academic_value: null, score_bounds: { lower: 0, upper: 100 }, missing_reasons: { warrantedness: 'passage_review_required' },
    evidence_readiness: 'abstract', priority: null, authorizes_publication: false },
  limitations: ['阅读顺序按证据准备度组织。'],
};
const links: FrontierKnowledgeLinksResponse = {
  record_id: 'paper', record_version: 2, record_content_hash: 'sha256:paper',
  knowledge_release_id: 'release:test', knowledge_release_hash: 'sha256:release', knowledge_release_level: 'preview',
  status: 'low_evidence', match_basis: 'topic_lexical_retrieval', relationship: 'reading_lead',
  limitations: ['仅提供主题词阅读线索。'], matches: [{ knowledge_id: 'D1:C1', title: '社会行动', content_version: 3, matched_topics: ['行动'] }],
};
it('shows source support and missing facts while keeping academic value unassessed', () => {
  render(<FrontierReadingPriority priority={readingPriorityView(priority)}/>);
  expect(screen.getByText('学术价值未评估')).toBeVisible();
  expect(screen.getByText(/摘要证据可定位/)).toBeVisible();
  fireEvent.click(screen.getByText('缺失字段与评分依据'));
  expect(screen.getByText('未核验研究方法')).toBeVisible();
  expect(screen.getByRole('link', { name: /摘要第一段/ })).toHaveAttribute('href', 'https://publisher.example/article');
  expect(screen.queryByText(/0.*100/)).not.toBeInTheDocument();
});
it('pins knowledge navigation to its actual release and entry version', () => {
  render(<FrontierKnowledgeLinks links={knowledgeLinksView(links)}/>);
  const anchor = screen.getByRole('link', { name: '社会行动' });
  expect(anchor).toHaveAttribute('href', '/knowledge/D1%3AC1?knowledge_release_id=release%3Atest');
  expect(screen.getByText('内容版本 3')).toBeVisible();
  expect(screen.getByText(/仅凭主题元数据/)).toBeVisible();
});
it('shows no-release fallback without suggesting a fabricated relationship', () => {
  render(<FrontierKnowledgeLinks links={knowledgeLinksView({ ...links, status: 'no_release', knowledge_release_id: null, knowledge_release_hash: null, knowledge_release_level: null, matches: [] })}/>);
  expect(screen.getByText('暂无可用知识发布')).toBeVisible();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});
it('renders citation-only reading support without an empty source quote', () => {
  render(<FrontierReadingPriority priority={readingPriorityView({ ...priority, basis: priority.basis.map(item => ({ ...item, snippet: '' })) })}/>);
  expect(screen.getByText('来源定位')).toBeVisible();
  expect(screen.queryByText('研究问题摘录')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /摘要第一段/ })).toHaveAttribute('href', 'https://publisher.example/article');
});
