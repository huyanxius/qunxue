import { XIcon } from '@phosphor-icons/react'

import { formatMaterialLocator } from './researchMaterialsModel'
import type { ResearchMaterialSelectionDraft } from './researchMaterialSelection'

type AnnotationKind = 'descriptive' | 'researcher_reflection'

const KIND_OPTIONS: ReadonlyArray<{ readonly value: AnnotationKind; readonly label: string; readonly hint: string }> = [
  { value: 'descriptive', label: '描述性材料', hint: '记录材料里发生了什么' },
  { value: 'researcher_reflection', label: '研究者反思', hint: '记录我对它的判断和警觉' },
]

type MaterialAnnotationDrawerProps = {
  readonly draft: ResearchMaterialSelectionDraft
  readonly kind: AnnotationKind
  readonly note: string
  readonly reflection: string
  readonly caseLabel: string
  readonly observedAt: string
  readonly saving: boolean
  readonly onKindChange: (kind: AnnotationKind) => void
  readonly onNoteChange: (value: string) => void
  readonly onReflectionChange: (value: string) => void
  readonly onCaseLabelChange: (value: string) => void
  readonly onObservedAtChange: (value: string) => void
  readonly onCancel: () => void
  readonly onSave: () => void
}

/**
 * 片段标记抽屉：把划中的一句原文变成一条证据。
 *
 * 字段顺序照研究者的思路排——先看清引了什么，再定这是描述还是反思，然后写，最后补背景。
 * 反思两种类型下都留着：描述性材料也允许附一句反思，只是不强制；标反思却不写反思才是没写完。
 * 抽屉从右侧滑出而不是接在正文下面：正文接一段表单会把阅读位置整个推走，回头找不到自己
 * 划的是哪句。抽屉会盖住部分正文，所以引文和定位符原样留在抽屉头部。
 */
export function MaterialAnnotationDrawer({
  draft,
  kind,
  note,
  reflection,
  caseLabel,
  observedAt,
  saving,
  onKindChange,
  onNoteChange,
  onReflectionChange,
  onCaseLabelChange,
  onObservedAtChange,
  onCancel,
  onSave,
}: MaterialAnnotationDrawerProps) {
  const reflectionRequired = kind === 'researcher_reflection'
  const canSave = Boolean(note.trim()) && (!reflectionRequired || Boolean(reflection.trim())) && !saving

  return (
    <aside className="qx-annotation" role="region" aria-label="片段标记">
      <header className="qx-annotation__head">
        <div>
          <span className="qx-eyebrow">已选原文</span>
          <p className="qx-annotation__quote">{draft.quote}</p>
          <small className="qx-annotation__locator">{formatMaterialLocator(draft.locator)}</small>
        </div>
        <button type="button" className="qx-icon-button" aria-label="取消片段标记" onClick={onCancel}>
          <XIcon size={15} aria-hidden="true" />
        </button>
      </header>

      <div className="qx-annotation__body">
        <div className="qx-field">
          <span className="qx-field__label" id="annotation-kind-label">标记类型</span>
          <div className="qx-segmented" role="radiogroup" aria-labelledby="annotation-kind-label">
            {KIND_OPTIONS.map((option) => (
              <button
                type="button"
                key={option.value}
                role="radio"
                aria-checked={kind === option.value}
                className={kind === option.value ? 'is-active' : undefined}
                onClick={() => onKindChange(option.value)}
              >
                <strong>{option.label}</strong>
                <small>{option.hint}</small>
              </button>
            ))}
          </div>
        </div>

        <label className="qx-field">
          <span className="qx-field__label">材料描述</span>
          <textarea
            aria-label="材料描述"
            value={note}
            rows={3}
            placeholder="这段原文在说什么"
            onChange={(event) => onNoteChange(event.target.value)}
          />
        </label>

        <label className="qx-field">
          <span className="qx-field__label">
            研究者反思
            <small>{reflectionRequired ? '必填' : '可选'}</small>
          </span>
          <textarea
            aria-label="研究者反思"
            value={reflection}
            rows={2}
            placeholder="我从这里读出了什么，又该警惕什么"
            onChange={(event) => onReflectionChange(event.target.value)}
          />
        </label>

        <div className="qx-field">
          <span className="qx-field__label">补充背景<small>可选</small></span>
          <div className="qx-annotation__context">
            <label>
              <span>案例</span>
              <input aria-label="案例" value={caseLabel} placeholder="如：家庭 A" onChange={(event) => onCaseLabelChange(event.target.value)} />
            </label>
            <label>
              <span>时间</span>
              <input aria-label="时间" value={observedAt} placeholder="如：迁移后" onChange={(event) => onObservedAtChange(event.target.value)} />
            </label>
          </div>
        </div>
      </div>

      <footer className="qx-annotation__foot">
        <button type="button" className="qx-button" onClick={onCancel}>取消</button>
        <button type="button" className="qx-button qx-button--primary" disabled={!canSave} onClick={onSave}>
          {saving ? '正在保存' : '保存片段标记'}
        </button>
      </footer>
    </aside>
  )
}

export type { AnnotationKind }
