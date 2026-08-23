import { useMemo, useState } from 'react'

import { KineticCopyCycle, type KineticCopyMessage } from './KineticCopyCycle'
import { useAppLocale } from '../i18n/AppLocaleProvider'

const researchTopicPresets = [
  '为什么同一课堂里有人总是沉默？',
  '为什么短视频越刷越难停下来？',
  '为什么年轻人越来越害怕求助？',
  '为什么同一种规则对不同人效果不同？',
  '为什么社区里的熟人关系正在变淡？',
  '为什么加班会被理解成敬业？',
  '为什么算法推荐会让观点越来越相似？',
  '为什么毕业后同学之间的差距迅速扩大？',
  '为什么人们明知焦虑仍持续比较？',
  '为什么公共空间里陌生人很少交谈？',
  '为什么家庭期待会影响职业选择？',
  '为什么网络争论很快变成身份对立？',
  '为什么一些传统在城市里重新流行？',
  '为什么照护劳动常常被忽视？',
  '为什么同伴评价会改变自我判断？',
  '为什么组织中的规则总有例外？',
  '为什么搬到大城市后反而更孤独？',
  '为什么某些知识更容易被相信？',
  '为什么人们会为不公平寻找合理解释？',
  '为什么技术进步没有减少所有人的负担？',
] as const

const englishResearchTopicPresets = [
  'Why do some students stay silent in the same classroom?',
  'Why is it so hard to stop scrolling short videos?',
  'Why are young people increasingly afraid to ask for help?',
  'Why does the same rule affect people differently?',
  'Why are neighborhood ties becoming weaker?',
  'Why is overtime interpreted as dedication?',
  'Why do recommendation algorithms make opinions more alike?',
  'Why do gaps between classmates widen after graduation?',
  'Why do people keep comparing themselves despite the anxiety?',
  'Why do strangers rarely talk in public spaces?',
  'Why do family expectations shape career choices?',
  'Why do online debates quickly become identity conflicts?',
  'Why are some traditions becoming popular again in cities?',
  'Why is care work so often overlooked?',
  'Why does peer evaluation change self-judgment?',
  'Why do organizational rules always have exceptions?',
  'Why can moving to a large city feel more lonely?',
  'Why is some knowledge easier to believe?',
  'Why do people rationalize unfairness?',
  'Why has technological progress not reduced everyone’s burden?',
] as const

const INTRO_PROMPT = '你想研究什么？'

export function ResearchPromptCarousel({ onSelect }: { onSelect: (topic: string) => void }) {
  const { locale } = useAppLocale()
  const { introPrompt, presets, messages } = useMemo(() => {
    const isEnglish = locale === 'en-US'
    const nextIntroPrompt = isEnglish ? 'What do you want to research?' : INTRO_PROMPT
    const nextPresets = isEnglish ? englishResearchTopicPresets : researchTopicPresets
    const nextMessages: readonly KineticCopyMessage[] = [
      { lines: [nextIntroPrompt] },
      ...nextPresets.map((preset) => ({
        prefix: isEnglish ? 'Try' : '试试',
        prefixClassName: 'research-agent-prompt__prefix',
        lines: [preset],
      })),
    ]
    return {
      introPrompt: nextIntroPrompt,
      presets: nextPresets,
      messages: nextMessages,
    }
  }, [locale])
  const [visibleMessageIndex, setVisibleMessageIndex] = useState(0)
  const topic = visibleMessageIndex > 0
    ? presets[visibleMessageIndex - 1]
    : null
  const prompt = topic ?? introPrompt

  return (
    <h1 aria-label={prompt} className="research-agent-prompt" id="research-agent-title">
      <button
        aria-label={prompt}
        disabled={!topic}
        onClick={() => topic && onSelect(topic)}
        type="button"
      >
        <KineticCopyCycle
          active
          as="span"
          className="research-agent-prompt__copy"
          firstCycleMs={5_000}
          loopStartIndex={1}
          messages={messages}
          motionMode="characters"
          onMessageChange={setVisibleMessageIndex}
        />
      </button>
    </h1>
  )
}
