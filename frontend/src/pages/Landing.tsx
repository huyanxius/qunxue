import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div className="site">
      <header className="site-header">
        <div className="container site-header-inner">
          <Link to="/" className="site-brand">
            <span className="seal">群学<br />致知</span>
            <span className="site-brand-text">
              <b className="serif">群学致知</b>
              <i>社会学垂类模型与智能体平台</i>
            </span>
          </Link>
          <nav className="site-nav" aria-label="站内导航">
            <a href="#product">产品</a>
            <a href="#method">方法</a>
            <a href="#team">团队</a>
            <a href="#faq">常见问题</a>
          </nav>
          <Link to="/new" className="btn btn-solid site-cta">进入演示</Link>
        </div>
      </header>

      <main>
        {/* ---- 英雄区 ---- */}
        <section className="hero">
          <div className="container hero-inner">
            <div className="hero-copy">
              <p className="kicker">面向社会学质性研究</p>
              <h1 className="serif">
                人是审稿人,<br />AI 是投稿人。
              </h1>
              <p className="hero-sub">
                访谈编码的 AI 第二编码者:初编码每一条带原文与出处,采纳与驳回全程留痕,
                人机一致性算成 Cohen&rsquo;s Kappa——你的编码信度,第一次可以拿数字摆给审稿人看。
              </p>
              <div className="hero-actions">
                <Link to="/new" className="btn btn-solid">进入演示工作台</Link>
                <a href="#method" className="btn btn-quiet">先看方法</a>
              </div>
              <p className="hero-note">演示使用虚构访谈材料,无需注册。</p>
            </div>

            {/* 纯 CSS 工作台缩影:稿件 + 页边批注 */}
            <div className="hero-mock" aria-hidden="true">
              <div className="mock-paper">
                <div className="mock-title">骑手访谈 · W-03</div>
                <p className="mock-line">早上九点多上线,一直跑到晚上九、十点吧。中午最忙,系统一单接一单地压过来,<mark>倒计时就在屏幕上跳,你眼睛根本不敢离开手机</mark>。</p>
                <p className="mock-line dim">超时一分钟就扣钱,顾客再点个"未送达",这单基本白跑……</p>
              </div>
              <div className="mock-note">
                <div className="mock-note-head">
                  <span>算法时间压力</span>
                  <span className="ai-mark">AI 初编</span>
                </div>
                <p>依据:"倒计时就在屏幕上跳……"</p>
                <p className="mock-note-src">出处:编码簿 v0.3 · 条目 01</p>
                <div className="mock-note-actions">
                  <em>采纳</em><em>修改</em><em className="rej">驳回</em>
                </div>
              </div>
              <div className="mock-kappa num">κ = 0.78</div>
            </div>
          </div>
        </section>

        {/* ---- 痛点 ---- */}
        <section className="pains" id="product">
          <div className="container">
            <p className="kicker">为什么做这个</p>
            <h2 className="serif">质性编码这道工序,压着三块石头。</h2>
            <div className="pain-grid">
              <article>
                <span className="pain-no serif">壹</span>
                <h3>逐段贴标签是苦役</h3>
                <p>几十万字访谈稿,一段一段读、一条一条编。编码不是研究的目的,却吃掉研究者最多的时间。</p>
              </article>
              <article>
                <span className="pain-no serif">贰</span>
                <h3>单人编码,信度无法自证</h3>
                <p>一个人的诠释劳动,看材料只看得见自己预期的东西。审稿人问一句"编码可靠吗",拿不出证据。</p>
              </article>
              <article>
                <span className="pain-no serif">叁</span>
                <h3>真人第二编码者太贵</h3>
                <p>标准做法是请第二位编码者背靠背编码、算一致性——多数学生和课题组请不起,也等不起。</p>
              </article>
            </div>
          </div>
        </section>

        {/* ---- 工作流 ---- */}
        <section className="method" id="method">
          <div className="container">
            <p className="kicker">怎么工作</p>
            <h2 className="serif">三步,从访谈稿到信度报告。</h2>
            <ol className="steps">
              <li>
                <span className="step-no num">01</span>
                <h3>交稿</h3>
                <p>上传或粘贴脱敏后的访谈稿,选择开放编码或导入你已有的编码簿。脱敏声明是进入前的必经关卡,不是可跳过的弹窗。</p>
              </li>
              <li>
                <span className="step-no num">02</span>
                <h3>审稿</h3>
                <p>AI 逐段给出初编码:标签、依据的原文引文、编码簿出处、置信说明,每一条带明显的"AI 初编"标识。你逐条采纳、修改或驳回——驳回必须给理由,像审稿人退稿一样。</p>
              </li>
              <li>
                <span className="step-no no-line num">03</span>
                <h3>拿报告</h3>
                <p>编码簿、人机一致性(Cohen&rsquo;s Kappa,给完整计算过程)、逐条分歧报告,一键导出。这份报告可以直接进论文附录。</p>
              </li>
            </ol>
            {/* 图片占位:产品工作台实拍截图,由后续图片资源替换 */}
            <div className="img-slot img-slot-wide" data-slot="workbench-screenshot">
              <span>图片占位 · 编码工作台界面截图(16:9)</span>
            </div>
          </div>
        </section>

        {/* ---- 立场:透明性 ---- */}
        <section className="stance">
          <div className="container stance-inner">
            <div className="stance-lead">
              <p className="kicker">我们的立场</p>
              <h2 className="serif">我们不请你相信 AI。</h2>
              <p>市面上的工具都在说"相信我的 AI 更聪明"。我们反过来:这个系统假定 AI 会出错,并把每一次可能的出错摆在明处,交给你裁决。</p>
            </div>
            <ul className="stance-list">
              <li><b>每条标签带出处。</b>初编码必须给出依据的原文引文和编码簿条目,给不出出处的判断不会出现在你面前。</li>
              <li><b>AI 产出有统一标识。</b>凡是 AI 生成的内容,界面上一律带"AI 初编"标记,人的裁决与机器的建议在视觉上永远分得开。</li>
              <li><b>分歧不是误差,是发现。</b>你驳回的每一条都被完整记录:AI 标了什么、你改成什么、为什么。分歧报告恰恰是你自己给不出的第二双眼睛。</li>
              <li><b>一致性给过程,不只给分数。</b>Kappa 的观察一致率、期望一致率逐项列出,审稿人看得懂,你也讲得清。</li>
            </ul>
          </div>
        </section>

        {/* ---- 概念查询(第二功能) ---- */}
        <section className="concepts-teaser">
          <div className="container concepts-inner">
            <div className="concepts-copy">
              <p className="kicker">第二件事</p>
              <h2 className="serif">概念,给带坐标的答案。</h2>
              <p>
                社会学的概念没有一句话的标准答案,只有带立场、时代、出处与分歧的坐标。
                概念查询接入项目知识库的九百余个词条,把一个概念在不同学派、不同年代的位置摆出来,分歧处标明分歧。
              </p>
              <Link to="/concepts" className="btn">查一个概念试试</Link>
            </div>
            <div className="concepts-card" aria-hidden="true">
              <div className="cc-term serif">社会资本</div>
              <div className="cc-axes">
                <div><i>立场</i><span>结构功能 / 批判理论 / 理性选择</span></div>
                <div><i>时代</i><span>1980s 概念化 → 2000s 测量之争</span></div>
                <div><i>分歧</i><span className="cc-conflict">是个人资源,还是集体属性?</span></div>
              </div>
            </div>
          </div>
        </section>

        {/* ---- 团队(全真话) ---- */}
        <section className="team" id="team">
          <div className="container">
            <p className="kicker">我们是谁</p>
            <h2 className="serif">一支为这道工序组起来的队伍。</h2>
            <div className="team-facts">
              <div>
                <b className="num">10</b>
                <span>名学生,来自 6 所高校:社会学、数学、计算机、心理学、中文</span>
              </div>
              <div>
                <b className="num">3</b>
                <span>位指导教师,含社会学教授全程把关方法论</span>
              </div>
              <div>
                <b className="serif team-flag">挑战杯</b>
                <span>"揭榜挂帅"擂台赛参赛作品,华中师范大学推报</span>
              </div>
            </div>
            {/* 图片占位:团队合照或工作照,由后续图片资源替换 */}
            <div className="img-slot" data-slot="team-photo">
              <span>图片占位 · 团队照片(3:2)</span>
            </div>
            <p className="team-note">本页不放用户证言——产品还没有用户证言。第一批真实用户访谈正在进行,结果会如实放在这里。</p>
          </div>
        </section>

        {/* ---- FAQ ---- */}
        <section className="faq" id="faq">
          <div className="container faq-inner">
            <h2 className="serif">常见问题</h2>
            <details>
              <summary>访谈数据安全吗?</summary>
              <p>系统只接收脱敏后的材料,上传前有强制的脱敏确认;演示环境全部使用虚构材料。正式版本的数据边界与存储方案会在部署文档中完整公开。</p>
            </details>
            <details>
              <summary>AI 会不会编造出处?</summary>
              <p>会,这正是系统存在的理由。所有出处限定在封闭的编码簿与知识库内,给不出可核对出处的编码不会展示;你仍应像对待第二编码者一样抽查它。</p>
            </details>
            <details>
              <summary>它会替代研究者的诠释吗?</summary>
              <p>不会,机制上就不允许:AI 只有建议权,没有裁决权。每一条编码都要经你采纳或驳回,最终编码簿署你的名。</p>
            </details>
            <details>
              <summary>和 NVivo、MAXQDA 有什么不同?</summary>
              <p>它们是通用质性分析软件,第二编码者仍需要你另请一个人。我们只做一件事:让"第二编码者+一致性检验"这个标准流程,一个人也能完成。</p>
            </details>
            <details>
              <summary>Kappa 值意味着什么?</summary>
              <p>Cohen&rsquo;s Kappa 是排除随机一致后的人机一致性系数。我们不承诺高 Kappa——低 Kappa 同样有价值,它说明这批材料的诠释空间大,分歧报告会告诉你分歧在哪。</p>
            </details>
          </div>
        </section>

        {/* ---- 收束 CTA ---- */}
        <section className="closing">
          <div className="container closing-inner">
            <h2 className="serif">下一份访谈稿,<br />带一位不知疲倦的第二编码者。</h2>
            <Link to="/new" className="btn btn-solid">进入演示工作台</Link>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container footer-inner">
          <div className="footer-brand">
            <span className="seal">群学<br />致知</span>
            <p>群学致知 · 面向一流学科建设的社会学垂类大模型与智能体平台<br />挑战杯"揭榜挂帅"擂台赛作品(榜题 XH-202620)</p>
          </div>
          <div className="footer-ethics">
            <b>伦理承诺</b>
            <p>不接收未脱敏的个人数据;不伪造学术数据与文献;AI 生成内容在系统内带明显标识。演示环境所有访谈材料均为虚构。</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
