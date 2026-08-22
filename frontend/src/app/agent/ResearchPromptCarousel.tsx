import { useState } from 'react'

import { KineticCopyCycle, type KineticCopyMessage } from './KineticCopyCycle'

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

const INTRO_PROMPT = '你想研究什么？'
const researchPromptMessages: readonly KineticCopyMessage[] = [
  { lines: [INTRO_PROMPT] },
  ...researchTopicPresets.map((topic) => ({
    prefix: '试试',
    prefixClassName: 'research-agent-prompt__prefix',
    lines: [topic],
  })),
]

export function ResearchPromptCarousel({ onSelect }: { onSelect: (topic: string) => void }) {
  const [visibleMessageIndex, setVisibleMessageIndex] = useState(0)
  const topic = visibleMessageIndex > 0
    ? researchTopicPresets[visibleMessageIndex - 1]
    : null
  const prompt = topic ?? INTRO_PROMPT

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
          messages={researchPromptMessages}
          motionMode="characters"
          onMessageChange={setVisibleMessageIndex}
        />
      </button>
    </h1>
  )
}
