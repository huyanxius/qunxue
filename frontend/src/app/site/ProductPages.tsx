import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'
import { SiteHeader } from './SiteHeader'
import { featureLinks, docLinks } from './siteNavigation'
import './product-pages.css'

function usePagePosition() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' })
    else window.scrollTo(0, 0)
  }, [pathname, hash])
}

function ResearchFigure() {
  return <figure className="product-figure product-figure--research">
    <div className="product-note"><span>研究问题 · 示例</span><p>社区中的互助，为什么有时难以持续？</p></div>
    <div className="product-research-flow"><div><small>研究计划</small><h3>先界定“持续”的含义</h3><p>比较不同社区的组织方式，区分参与机会与参与意愿。</p></div>
      <div><small>证据与解释</small><h3>让判断回到材料</h3><p>检查支持证据、反例与来源，再修订研究问题。</p><span className="product-source-tag">原文位置 ↗</span></div></div>
    <figcaption>研究步骤示意，非真实研究结果。实际报告由当前研究任务生成。</figcaption>
  </figure>
}

function ModelsFigure() {
  return <figure className="product-figure product-figure--models">
    <div className="product-model-row"><span>研究对话</span><strong>理解问题与组织研究</strong><small>由已配置的语言模型服务处理</small></div>
    <svg viewBox="0 0 420 84" role="img" aria-label="语音波形示意"><path d="M0 42h420" />{Array.from({ length: 48 }, (_, i) => {
      const height = 8 + Math.abs(Math.sin(i * .73) * Math.cos(i * .21)) * 60
      return <line key={i} x1={12 + i * 8.4} x2={12 + i * 8.4} y1={42 - height / 2} y2={42 + height / 2} />
    })}</svg>
    <div className="product-model-row"><span>音视频转写</span><strong>把访谈转成可核对的文本</strong><small>服务可用时转写；完成后仍需人工校正</small></div>
    <figcaption>处理分工示意。语言模型与转写服务是两项独立配置。</figcaption>
  </figure>
}

function KnowledgeFigure() {
  return <figure className="product-figure product-figure--knowledge">
    <span className="product-figure-label">理论阅读 · 结构示意</span>
    <div className="product-book"><small>从一个概念进入</small><h3>社会资本</h3><p>理解关系网络中的资源，比较不同理论对行动的解释。</p><div><span>概念与命题</span><span>适用情境</span><span>来源文献</span></div></div>
    <div className="product-reading-note"><span>研究者的下一步</span><p>这种解释适合我的材料吗？<br />还需要比较哪些理论？</p></div>
    <figcaption>内容仅作阅读结构示意；实际条目、出处与关系以知识库为准。</figcaption>
  </figure>
}

function GraphFigure() {
  return <figure className="product-figure product-figure--graph">
    <svg viewBox="0 0 540 320" role="img" aria-label="概念、理论、证据之间的关系示意">
      <g className="product-graph-lines"><path d="M270 150 125 72M270 150 420 66M270 150 120 240M270 150 420 248M125 72 420 66M420 66 420 248" /></g>
      <g className="product-graph-nodes"><circle cx="270" cy="150" r="45" /><circle cx="125" cy="72" r="32" /><circle cx="420" cy="66" r="32" /><circle cx="120" cy="240" r="32" /><circle cx="420" cy="248" r="32" /></g>
      <g className="product-graph-text"><text x="270" y="155">研究问题</text><text x="125" y="77">概念</text><text x="420" y="71">理论</text><text x="120" y="245">材料</text><text x="420" y="253">解释</text></g>
    </svg>
    <figcaption>原创关系示意，不代表知识库中的真实关系或统计结论。</figcaption>
  </figure>
}

function ProductFooter() {
  return <footer className="product-footer"><Link to="/welcome">群学致知</Link><span>最终判断由研究者完成。</span><Link to="/docs">使用手册 ↗</Link></footer>
}

export function FeaturesPage({ authenticated = false }: { authenticated?: boolean }) {
  usePagePosition()
  return <div className="product-site"><SiteHeader authenticated={authenticated} /><main id="site-main" className="product-main">
    <div className="product-intro"><span className="product-eyebrow">群学的功能</span><h1>让研究问题，<br />有材料可依。</h1><p>整理困惑、查找理论、比较证据，再形成自己的判断。了解群学如何参与你的研究过程。</p>
      <Link className="product-button" to={authenticated ? '/agent' : '/register'}>开始体验 ↗</Link><Link className="product-inline-link" to="/docs#quick-start">阅读快速开始</Link></div>
    <nav className="product-chapters" aria-label="功能页目录">{featureLinks.map((item) => <Link key={item.id} to={`#${item.id}`}>{item.title}</Link>)}</nav>
    <section className="product-section" id="deep-research" aria-labelledby="deep-research-title">
      <div className="product-section__copy"><span className="product-eyebrow">深入研究</span><h2 id="deep-research-title">把一段困惑，<br />展开成研究计划。</h2><p>在研究对话中选择深入研究，说明你想研究的现象、已有材料和范围。先审阅计划，再确认开始；研究结果可以沿着来源继续核对。</p><ul><li>补充背景与限制，让研究范围更明确。</li><li>确认计划后开展研究，查看进度与结果。</li><li>从报告回到证据，继续追问或修订。</li></ul><Link to="/agent" className="product-inline-link">进入研究对话 ↗</Link><Link to="/docs#research" className="product-inline-link">查看操作步骤</Link></div><ResearchFigure />
    </section>
    <section className="product-section" id="models" aria-labelledby="models-title">
      <div className="product-section__copy"><span className="product-eyebrow">群学的模型接入</span><h2 id="models-title">对话与转写，<br />各自完成合适的工作。</h2><p>语言模型帮助理解问题和组织研究。音视频转写服务将访谈转换为文本，方便定位、校正与后续阅读。实际可用能力取决于当前服务配置。</p><p>群学接入外部模型服务。转写尚无固定的产品模型名；服务未配置时，可以保留原件并导入转写文本。</p><Link to="/docs#models" className="product-inline-link">了解模型与转写</Link></div><ModelsFigure />
    </section>
    <section className="product-section" id="knowledge" aria-labelledby="knowledge-title">
      <div className="product-section__copy"><span className="product-eyebrow">知识库</span><h2 id="knowledge-title">找到理论，<br />也找到它的出处。</h2><p>按关键词查找知识条目，阅读概念、命题和来源。把理论放回适用情境，比较它能解释什么、还有什么没有解释。</p><p>知识库支持从列表进入条目详情；知识图谱提供另一种浏览关系的方式。是否适合你的研究，仍需要结合原文和材料判断。</p><Link to="/knowledge" className="product-inline-link">浏览知识库 ↗</Link><Link to="/docs#sources" className="product-inline-link">如何核对引用</Link></div><KnowledgeFigure />
    </section>
    <section className="product-section" id="visualization" aria-labelledby="visualization-title">
      <div className="product-section__copy"><span className="product-eyebrow">可视化图表</span><h2 id="visualization-title">从关系与分布，<br />寻找下一步线索。</h2><p>在知识图谱中查看条目连接，进入节点阅读详情；在学术前沿中查看文献分布与分析，结合筛选范围理解图表。</p><p>图谱连线需要回到具体关系核对。文献分布只覆盖当前收录范围，不能直接当作整个学科的统计结论。</p><Link to="/knowledge/graph" className="product-inline-link">打开知识图谱 ↗</Link><Link to="/knowledge?scope=frontier" className="product-inline-link">查看学术前沿 ↗</Link></div><GraphFigure />
    </section>
    <aside className="product-boundary"><h2>关于图片与图表</h2><p>当前研究材料支持文档和音视频，暂不支持上传图片进行理解。图谱与前沿图表来自现有功能；聊天中没有通用的交互图表生成入口。</p><Link to="/docs#limits">查看支持格式与限制 ↗</Link></aside>
    <div className="product-closing"><h2>从你正在想的问题开始。</h2><Link className="product-button" to={authenticated ? '/agent' : '/register'}>开始体验 ↗</Link></div>
  </main><ProductFooter /></div>
}

export function DocsPage({ authenticated = false }: { authenticated?: boolean }) {
  usePagePosition()
  return <div className="product-site"><SiteHeader authenticated={authenticated} /><main id="site-main" className="docs-main">
    <div className="docs-intro"><span className="product-eyebrow">群学使用手册</span><h1>Docs</h1><p>从第一次提问，到检查来源与研究材料。这里按实际操作说明使用方法与边界。</p></div>
    <div className="docs-layout"><nav className="docs-index" aria-label="手册目录">{docLinks.map((item) => <Link key={item.id} to={`#${item.id}`}>{item.title}</Link>)}<Link to="#models">模型与转写</Link></nav>
      <article className="docs-article">
        <section id="quick-start"><span className="product-eyebrow">开始使用</span><h2>快速开始</h2><ol><li><Link to="/register">创建账号</Link>，或使用已有账号<Link to="/login">登录</Link>。登录后从工作台进入研究对话。</li><li>写下一个具体困惑。补充研究对象、情境、已知事实，以及你希望理解的部分。</li><li>阅读回复，核对来源；补充材料或继续追问。需要更完整的研究时，再选择深入研究。</li></ol><div className="docs-example"><span>提问示例</span><p>我观察到社区互助活动中，固定参与者逐渐减少。我有三份访谈记录，想比较时间压力和组织方式的影响。请先帮我厘清需要补充的证据。</p></div><p>示例只说明如何交代背景，不代表群学已经得出研究结论。</p></section>
        <section id="research"><span className="product-eyebrow">实际操作</span><h2>开展研究对话</h2><h3>选择模式与确认计划</h3><p>进入<Link to="/agent">研究对话</Link>，打开输入框旁的 Agent 模式选择，切换为深入研究。发送需求后审阅研究计划，补充范围或限制，再点击“开始深入研究”。计划待确认时，研究尚未开始。</p><h3>使用自己的材料</h3><p>从输入框的附件入口直接上传，或从当前任务的材料库选择已有材料。等待解析完成，再确认附件已加入本轮输入后发送。移除附件会改变当前轮次使用的材料范围。</p><h3>查看结果与继续研究</h3><p>根据界面显示检查研究进度、报告和来源。对不确定的结论继续追问；需要中止时使用停止入口。已有研究可以从工作台重新打开，继续使用同一任务的材料。</p><p>研究任务和深入研究对话是不同入口。需要建立研究起点时，可使用<Link to="/research/new">新建研究</Link>；已经有方案时，可使用<Link to="/research/existing">已有研究入口</Link>。</p></section>
        <section id="sources"><span className="product-eyebrow">核对证据</span><h2>来源与引用</h2><p>知识库条目提供来源信息。研究对话中的来源可能来自知识库、网页或你添加的材料。核对时先看原文，再判断它是否支持当前说法。</p><ul><li>文档材料可能提供页码、段落、行号或标题位置，具体取决于解析结果。</li><li>转写材料可能提供时间片段和说话人信息；这取决于服务返回的内容。</li><li>网页引用需核对作者、发布时间与正文。无法读取的网页不应视为已经验证的证据。</li><li>生成的摘要、报告或引用格式仍需人工检查，不能代替阅读原文。</li></ul><p>知识图谱的关系不等同于因果关系。点开相关条目，检查关系说明与出处。</p></section>
        <section id="limits"><span className="product-eyebrow">使用边界</span><h2>附件与图表限制</h2><div className="docs-table-wrap"><table><caption>研究材料支持范围</caption><thead><tr><th scope="col">类型</th><th scope="col">支持格式</th><th scope="col">使用前需要确认</th></tr></thead><tbody><tr><th scope="row">文档</th><td>PDF、DOCX、TXT、Markdown</td><td>解析已完成，正文可读取。扫描 PDF 需要先做 OCR，当前没有内置 OCR 服务。</td></tr><tr><th scope="row">音视频</th><td>MP3、M4A、WAV、MP4、WebM</td><td>上传仅保存原件；需完成转写或导入文本后才能检索正文。</td></tr><tr><th scope="row">图片</th><td>暂不支持</td><td>不能把图片附件或视频原件当作图像理解入口。</td></tr></tbody></table></div><p>附件仅在获授权的当前任务与本轮选择范围内使用。上传失败或解析失败时，按界面原因处理并重试；不要将“原件已保存”当作“正文已可用”。</p><h3>图表覆盖范围</h3><p>知识图谱展示已收录条目之间的连接。学术前沿展示当前收录文献的分布与分析；筛选范围与缺失数据会影响结果。当前没有任意上传数据自动生成交互图表的通用入口。</p></section>
        <section id="models"><span className="product-eyebrow">服务能力</span><h2>模型与语音转写</h2><p>群学接入配置好的语言模型服务开展研究对话。仓库默认语言模型配置为 DeepSeek；这不代表每个部署都使用相同模型，也不代表群学训练了自有基础模型。</p><p>转写支持 DashScope 或兼容 OpenAI 转写接口的服务接入。具体模型由部署配置决定，仓库没有固定的转写模型名称。服务未配置或不可用时，界面会显示相应状态；可先上传原件，再导入已有转写文本。</p><p>转写后检查说话人、时间片段、专有名词和遗漏。人工校正有助于后续分析，但不能把模型生成内容当作访谈原话。</p></section>
        <section id="faq"><span className="product-eyebrow">排查问题</span><h2>常见问题</h2><details><summary>为什么上传成功后仍不能使用材料？</summary><p>上传保存原件，解析生成可检索的正文。检查材料状态；扫描 PDF 需要 OCR，音视频需要转写。先等待处理完成，或按提示补充可读取的文本。</p></details><details><summary>为什么深入研究还没有开始？</summary><p>检查是否停留在计划确认阶段。审阅并点击“开始深入研究”后才会启动。若界面显示服务错误，保留当前任务并按提示重试。</p></details><details><summary>转写按钮不可用怎么办？</summary><p>当前部署可能未配置可用转写服务。可以保存原件并导入已有文本；需要恢复自动转写时，请联系站点管理员检查服务配置。</p></details><details><summary>报告的引用能直接用于论文吗？</summary><p>使用前核对原文、页码、作者与年份，并按你的写作规范整理。生成内容和引用都需要研究者确认。</p></details><details><summary>手机可以使用吗？</summary><p>可以通过同一网站登录、查看手册并进入工作台。官网“功能”和“Docs”使用点击展开。复杂图谱与长文档建议在较大屏幕核对。</p></details><details><summary>重新打开页面后如何继续？</summary><p>登录原账号，从工作台打开已有研究。材料与对话按任务管理；开始新任务前，先确认是否需要延续原研究。</p></details></section>
      </article>
    </div>
  </main><ProductFooter /></div>
}
