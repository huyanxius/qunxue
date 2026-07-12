import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SEGMENTS, TRANSCRIPT_TITLE } from '../data/demo'
import { clearDecisions } from '../store/decisions'

export default function NewTask() {
  const nav = useNavigate()
  const [mode, setMode] = useState<'open' | 'imported'>('imported')
  const [anonymized, setAnonymized] = useState(false)

  const start = () => {
    clearDecisions()
    nav('/workbench')
  }

  return (
    <main className="page-narrow">
      <p className="kicker">建立编码任务</p>
      <h1 className="serif page-title">先交稿,再开工。</h1>

      <section className="panel">
        <h2>一、访谈材料</h2>
        <div className="material-demo">
          <div>
            <b>{TRANSCRIPT_TITLE}</b>
            <p>{SEGMENTS.length} 个段落 · 单人深度访谈 · 全文虚构,仅供演示</p>
          </div>
          <span className="tag-ready">已就绪</span>
        </div>
        <p className="panel-note">上传 txt/docx 与粘贴文本为正式版功能;演示版使用内置的虚构访谈稿,让你直接体验完整流程。</p>
      </section>

      <section className="panel">
        <h2>二、编码方式</h2>
        <label className="choice">
          <input
            type="radio"
            name="mode"
            checked={mode === 'imported'}
            onChange={() => setMode('imported')}
          />
          <span>
            <b>使用既有编码簿</b>
            <i>演示内置编码簿 v0.3(7 个条目),AI 初编码将限定在这些条目内并标注出处。</i>
          </span>
        </label>
        <label className="choice">
          <input
            type="radio"
            name="mode"
            checked={mode === 'open'}
            onChange={() => setMode('open')}
          />
          <span>
            <b>开放编码(正式版功能)</b>
            <i>从材料中生成候选标签,再由你归并定稿。演示版不开放。</i>
          </span>
        </label>
      </section>

      <section className="panel">
        <h2>三、伦理确认</h2>
        <label className="choice choice-ethics">
          <input
            type="checkbox"
            checked={anonymized}
            onChange={(e) => setAnonymized(e.target.checked)}
          />
          <span>
            <b>我确认材料已完成脱敏</b>
            <i>不含真实姓名、单位、可识别个人身份的信息。这是进入工作台的必要条件,不是形式条款。</i>
          </span>
        </label>
      </section>

      <div className="task-actions">
        <button className="btn btn-solid" disabled={!anonymized} onClick={start}>
          进入编码工作台
        </button>
        {!anonymized && <span className="task-hint">勾选脱敏确认后开始</span>}
      </div>
    </main>
  )
}
