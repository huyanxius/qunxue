export function ResearchStartGuide() {
  return (
    <section className="research-start-guide" role="region" aria-label="开始研究">
      <div>
        <p className="research-start-guide__eyebrow">START HERE</p>
        <h2>从一个具体现象开始</h2>
        <p className="research-start-guide__lede">
          先描述你观察到的变化，再核对现象快照。每一步都由你确认，系统不会把猜测写成结论。
        </p>
      </div>
      <ol className="research-start-guide__steps">
        <li>
          <strong>描述</strong>
          <span>写下对象、变化和你真正困惑的部分。</span>
        </li>
        <li>
          <strong>核对</strong>
          <span>检查系统整理的现象与依据，再决定是否确认。</span>
        </li>
        <li>
          <strong>继续</strong>
          <span>Agent 界面预览，尚未连接研究模型；不会自动变成研究任务。</span>
        </li>
      </ol>
      <p className="research-start-guide__boundary">
        当前版本：理论匹配与研究框架尚未开放；可用内容会明确标出来源，研究决定仍由你确认。
      </p>
    </section>
  )
}
