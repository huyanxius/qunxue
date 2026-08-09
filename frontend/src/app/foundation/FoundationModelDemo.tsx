import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

const questionFlow = [
  [
    '为什么同样的制度在不同社区会产生不同结果？',
    '我已经有一个理论框架，怎样找到真正可证伪的问题？',
    '访谈材料互相矛盾时，我应该先补哪一种证据？',
  ],
  [
    '为什么熟人网络扩大后，合作意愿反而降低？',
    '怎样区分身份认同与利益计算的作用？',
    '现象、机制和规范判断混在一起，应该先拆哪个？',
  ],
  [
    '平台规则改变之后，劳动者为什么仍沿用旧有策略？',
    '两个概念很相似，怎样判断它们是否属于同一个理论机制？',
    '我的案例只有一次事件，还能做比较研究吗？',
  ],
  [
    '怎样寻找能够推翻当前解释的反例？',
    '成员流动是原因，还是关系变化的结果？',
    '什么材料才能区分社会资本与集体行动的解释？',
  ],
  [
    '一个看似个人的选择，如何放回组织与制度中理解？',
    '当受访者的说法与实际行为不同时，哪一个才是研究对象？',
    '理论可以解释所有事，是不是反而说明它无法被验证？',
  ],
  [
    '我应该比较人、时间，还是比较不同场域？',
    '某种行为减少了，怎样避免直接把它写成价值判断？',
    '我手里的日志、访谈和政策文本，哪一种先进入分析？',
  ],
  [
    '如果理论候选都能说通，下一步要观察什么？',
    '如何判断我看到的变化是短期波动，还是结构性转变？',
    '我能不能从一个已经成熟的结论往回找它忽略的问题？',
  ],
  [
    '两组访谈对同一件事的记忆不同，差异本身能否成为证据？',
    '怎样把“越来越少”变成能够被观察和比较的变化？',
    '理论预期与材料相反时，我应该改问题还是改解释？',
  ],
]

function demonstrationReply(input: string) {
  const characters = Array.from(input)
  const excerpt = characters.slice(0, 18).join('')
  const suffix = characters.length > 18 ? '…' : ''
  return `请再补充：“${excerpt}${suffix}”发生在哪些对象、时间与情境中？`
}

export function FoundationQuestionFlow() {
  return (
    <div className="foundation-question-flow" aria-label="合成社会科学研究提问流">
      <p>背景为合成研究提问样本，不是真实用户记录。</p>
      <div aria-hidden="true">
        {questionFlow.map((questions, laneIndex) => (
          <div className={`foundation-question-flow__lane foundation-question-flow__lane--${laneIndex + 1}`} key={questions[0]}>
            <div className="foundation-question-flow__track">
              {[0, 1, 2].map((groupIndex) => (
                <div className="foundation-question-flow__group" key={groupIndex}>
                  {questions.map((question, questionIndex) => (
                    <span key={`${groupIndex}:${question}`}>
                      <i>{String(laneIndex * 3 + questionIndex + 1).padStart(2, '0')}</i>
                      {question}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FoundationModelDemo() {
  const [draft, setDraft] = useState('')
  const [prompt, setPrompt] = useState('例如：同一社区中的互助为什么逐渐减少？')
  const [responding, setResponding] = useState(false)
  const responseTimer = useRef<number | null>(null)

  useEffect(() => () => {
    if (responseTimer.current !== null) window.clearTimeout(responseTimer.current)
  }, [])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const content = draft.trim()
    if (!content || responding) return

    setDraft('')
    setResponding(true)
    responseTimer.current = window.setTimeout(() => {
      setPrompt(demonstrationReply(content))
      setResponding(false)
      responseTimer.current = null
    }, 620)
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  return (
    <div className="foundation-model" role="region" aria-label="学科垂直模型对话演示">
      <form className="foundation-model__field foundation-model__field--standalone" onSubmit={submit}>
        <textarea
          aria-label="输入一个研究现象"
          id="foundation-model-prompt"
          maxLength={240}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={submitOnEnter}
          placeholder={responding ? '正在区分现象、解释与证据…' : prompt}
          rows={1}
          value={draft}
        />
        <button
          aria-label={responding ? '正在整理问题' : '发送'}
          type="submit"
          disabled={!draft.trim() || responding}
        >
          <span aria-hidden="true">{responding ? '···' : '↑'}</span>
        </button>
      </form>
    </div>
  )
}
