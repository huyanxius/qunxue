import { ToolboxIcon } from '@phosphor-icons/react'

import qualitativeCodingImage from '../../assets/research-tools/qualitative-coding.webp'
import dataCleaningImage from '../../assets/research-tools/data-cleaning.webp'
import surveyAnalysisImage from '../../assets/research-tools/survey-analysis.webp'
import interviewNotesImage from '../../assets/research-tools/interview-notes.webp'
import { PageContent, PageShell } from '../ui/PageShell'
import '../home/app-home.css'
import { ResearchToolsShader } from './ResearchToolsShader'
import './research-tools.css'

const tools = [
  {
    title: '质性编码',
    description: '标记原文，建立编码与主题',
    image: qualitativeCodingImage,
  },
  {
    title: '数据清洗',
    description: '处理缺失、重复与异常',
    image: dataCleaningImage,
  },
  {
    title: '问卷分析',
    description: '查看分布、交叉与量表结果',
    image: surveyAnalysisImage,
  },
  {
    title: '访谈整理',
    description: '转写、分段并整理访谈',
    image: interviewNotesImage,
  },
]

export function ResearchToolsPage() {
  return (
    <PageShell workspace>
      <PageContent>
        <section className="research-tools-page" aria-label="研究工具列表" role="region">
          <ResearchToolsShader />
          <header className="research-tools-page__identity">
            <ToolboxIcon size={18} weight="regular" aria-hidden="true" />
            <h1>研究工具</h1>
          </header>

          <div className="research-tools-page__grid">
            {tools.map(({ title, description, image }) => (
              <article className="workbench-destination research-tools-page__card" key={title}>
                <img className="workbench-destination__image" src={image} alt="" aria-hidden="true" />
                <span className="workbench-destination__shade" aria-hidden="true" />
                <span className="workbench-destination__copy">
                  <h2>{title}</h2>
                  <small>{description}</small>
                </span>
                <span className="workbench-destination__arrow" aria-hidden="true">↗</span>
              </article>
            ))}
          </div>
        </section>
      </PageContent>
    </PageShell>
  )
}
