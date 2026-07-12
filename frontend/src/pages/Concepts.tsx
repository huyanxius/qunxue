import { useEffect, useMemo, useState } from 'react'

// 词条来自项目知识库 concepts.json(随前端静态分发,fetch 按需加载,不进打包体积)。
interface Concept {
  id: string
  title: string
  periods: Record<string, string>
  section: string
  subsection: string
}

const PERIODS: Array<[key: string, axis: string]> = [
  ['萌发期', '萌发'],
  ['经典表述', '经典'],
  ['争辩与阐发', '争辩'],
  ['当代发展', '当代'],
]

const SUGGESTIONS = ['社会资本', '民族志', '扎根理论', '科层制', '内卷化']

export default function Concepts() {
  const [all, setAll] = useState<Concept[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState<Concept | null>(null)

  useEffect(() => {
    fetch('/concepts.json')
      .then((r) => r.json())
      .then((d) => setAll(d.concepts as Concept[]))
      .catch(() => setFailed(true))
  }, [])

  const hits = useMemo(() => {
    if (!all) return []
    const s = q.trim()
    if (!s) return []
    return all.filter((c) => c.title.includes(s)).slice(0, 10)
  }, [all, q])

  const suggestions = useMemo(
    () => (all ? SUGGESTIONS.map((s) => all.find((c) => c.title.includes(s))).filter(Boolean) as Concept[] : []),
    [all],
  )

  return (
    <main className="page-narrow concepts-page">
      <p className="kicker">概念查询</p>
      <h1 className="serif page-title">不给标准答案,给带坐标的答案。</h1>

      <div className="concept-search">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="输入一个社会学概念,如:社会资本"
          aria-label="概念检索"
        />
      </div>
      <p className="panel-note">
        {failed
          ? '知识库加载失败,请刷新重试。'
          : all
            ? `已接入项目知识库 ${all.length} 个词条,按「萌发—经典—争辩—当代」四段学术史呈现;查不到的词条会明说,不会现编。`
            : '正在加载知识库……'}
      </p>

      {q.trim() && hits.length > 0 && (
        <ul className="concept-hits">
          {hits.map((c) => (
            <li key={c.id}>
              <button className={sel?.id === c.id ? 'is-sel' : ''} onClick={() => setSel(c)}>
                <b className="serif">{c.title}</b>
                <span>{c.section} · {c.subsection}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {q.trim() && all && hits.length === 0 && (
        <div className="concept-miss">
          <p className="serif">「{q.trim()}」不在知识库中。</p>
          <p>当前知识库覆盖 {all.length} 个概念;查不到时如实告知,不即兴生成。</p>
        </div>
      )}

      {!q.trim() && suggestions.length > 0 && (
        <div className="concept-suggest">
          <span>试试:</span>
          {suggestions.map((c) => (
            <button key={c.id} className="btn btn-quiet" onClick={() => { setSel(c); setQ(c.title.split('（')[0]) }}>
              {c.title.split('（')[0]}
            </button>
          ))}
        </div>
      )}

      {sel && (
        <article className="concept-entry">
          <header className="concept-head">
            <h2 className="serif">{sel.title}</h2>
            <span className="ai-mark">知识库词条 · {sel.id}</span>
          </header>
          <p className="concept-crumb">{sel.section} / {sel.subsection}</p>

          {PERIODS.map(([key, axis]) =>
            sel.periods[key] ? (
              <section className="coord" key={key}>
                <h3><i className="coord-axis">{axis}</i>{key}</h3>
                <p>{sel.periods[key]}</p>
              </section>
            ) : null,
          )}

          <section className="coord">
            <h3><i className="coord-axis">出处</i>本词条依据</h3>
            <p className="concept-src">
              项目知识库条目 {sel.id}(七维知识库 · {sel.section});文献级溯源在正式版中逐条链接到可核对的文献记录。
            </p>
          </section>
        </article>
      )}
    </main>
  )
}
