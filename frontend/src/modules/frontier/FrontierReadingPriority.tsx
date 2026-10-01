import type { ReadingPriority } from './readingInsightsApi';
import './frontier-reading-insights.css';

const fieldLabels: Record<string, string> = { research_question: '研究问题', methods: '方法', data: '数据', sample: '样本', findings: '发现', limitations: '局限' };
const criterionLabels: Record<string, string> = { question_significance: '问题意义', contribution_increment: '贡献增量', warrantedness: '论证依据', scope_and_limits: '范围与局限', scholarly_dialogue: '学术对话' };
const reasonLabels: Record<string, string> = { research_track_required: '研究路径未标明', unassessed: '缺少评审事实', passage_review_required: '尚缺原文审读', located_evidence_required: '缺少定位依据', record_snapshot_binding_required: '依据与当前版本不符', invalid_stored_rating: '评审事实无效', located_source_evidence_required: '缺少可定位的来源证据', field_not_available: '来源尚未提供' };
export function FrontierReadingPriority({ priority }: { priority: ReadingPriority }) {
  const labels = { passage_supported: '原文证据可定位', abstract_supported: '摘要证据可定位', metadata_only: '仅有元数据线索' };
  return <section className="frontier-reading-insights" aria-label="阅读依据与价值评估">
    <h3>阅读依据</h3>
    <p>{labels[priority.readinessLevel]} · 文献版本 {priority.recordVersion}</p>
    <p>{priority.academic.status === 'assessed' ? `已有审读评分：${priority.academic.value}` : priority.academic.status === 'partial' ? '学术价值部分评估，尚无总分' : '学术价值未评估'}</p>
    <p className="frontier-reading-note">阅读顺序按证据准备度组织，不代表学术质量或模型理解。</p>
    {priority.supportedFields.length > 0 && <p>来源支持：{priority.supportedFields.map(field => fieldLabels[field] ?? field).join('、')}</p>}
    {priority.sourceEvidence.map((item, index) => <div className="frontier-reading-source" key={`${item.blockId}-${index}`}>
      <p>{item.basisType === 'assistant_abstract_reading' ? '自写摘要阅读说明的来源' : item.snippet ? '来源摘录' : '来源定位'}</p>
      {item.snippet && <p>{item.snippet}</p>}<a href={item.url} target="_blank" rel="noreferrer">{item.locator} · 查看来源</a>
    </div>)}
    <details><summary>缺失字段与评分依据</summary>
      <dl>{priority.missingFields.map(({ field, reason }) => <div key={field}><dt>{fieldLabels[field] ?? field}</dt><dd>{reasonLabels[reason] ?? reason}</dd></div>)}</dl>
      <p>规则为项目草案，未知项不是零分，部分评分不重算权重。</p>
      <dl>{priority.academic.criteria.map(item => <div key={item.key}>
        <dt>{criterionLabels[item.key] ?? item.key} · 权重 {item.weight}%</dt>
        <dd>{item.score === null ? reasonLabels[item.missingReason ?? 'unassessed'] ?? item.missingReason : `${item.score}/4`}
          {item.rationale && <p>{item.rationale}</p>}
          {item.evidence.map((e, index) => <p key={index}>{e.locator} · 文献版本 {e.version} · 审读者 {e.reviewer}</p>)}
        </dd>
      </div>)}</dl>
      <small>规则：{priority.academic.ruleVersion}；评分不授权知识发布。</small>
    </details>
  </section>;
}
