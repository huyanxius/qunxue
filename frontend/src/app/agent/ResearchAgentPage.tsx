import { ArrowUpIcon } from '@phosphor-icons/react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'

import { PageContent, PageShell } from '../ui/PageShell'
import './research-agent-page.css'

const starterQuestions = [
  '为什么同一社区里的互助正在减少？',
  '平台算法如何改变年轻人的职业选择？',
  '为什么越来越多人选择独居？',
]

const conversationStorageKey = 'qunxue.agent-conversations.v1'
const conversationHistoryLimit = 12

type AgentConversation = {
  id: string
  question: string
  createdAt: string
}

function readConversationHistory(): AgentConversation[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(conversationStorageKey) ?? '[]')

    if (!Array.isArray(stored)) return []

    return stored.filter((item): item is AgentConversation => {
      if (!item || typeof item !== 'object') return false
      const candidate = item as Partial<AgentConversation>
      return typeof candidate.id === 'string'
        && typeof candidate.question === 'string'
        && typeof candidate.createdAt === 'string'
    }).slice(0, conversationHistoryLimit)
  } catch {
    return []
  }
}

function writeConversationHistory(history: AgentConversation[]) {
  try {
    window.localStorage.setItem(conversationStorageKey, JSON.stringify(history))
  } catch {
    // 本地存储不可用时，对话预览仍可在当前页面继续使用。
  }
}

function createConversationId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return `agent-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function AgentConversationHistory({
  activeConversationId,
  conversations,
  onOpen,
}: {
  activeConversationId: string | null
  conversations: AgentConversation[]
  onOpen: (conversation: AgentConversation) => void
}) {
  return (
    <section className="agent-conversation-history" aria-label="Agent 对话记录">
      <h2>对话记录</h2>
      {conversations.length > 0 ? (
        <div className="agent-conversation-history__list">
          {conversations.map((conversation) => (
            <button
              aria-current={conversation.id === activeConversationId ? 'true' : undefined}
              key={conversation.id}
              onClick={() => onOpen(conversation)}
              title={conversation.question}
              type="button"
            >
              <span>{conversation.question}</span>
              <span aria-hidden="true">···</span>
            </button>
          ))}
        </div>
      ) : (
        <p>发送第一条消息后会保存在这里</p>
      )}
    </section>
  )
}

export function ResearchAgentPage() {
  const [draft, setDraft] = useState('')
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(null)
  const [conversations, setConversations] = useState(readConversationHistory)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)

  const canSubmit = draft.trim().length > 0

  function submitDraft() {
    const question = draft.trim()

    if (!question) return

    const conversation: AgentConversation = {
      id: createConversationId(),
      question,
      createdAt: new Date().toISOString(),
    }
    const nextConversations = [
      conversation,
      ...conversations.filter((item) => item.question !== question),
    ].slice(0, conversationHistoryLimit)

    setConversations(nextConversations)
    writeConversationHistory(nextConversations)
    setActiveConversationId(conversation.id)
    setSubmittedQuestion(question)
    setDraft('')
  }

  function openConversation(conversation: AgentConversation) {
    setActiveConversationId(conversation.id)
    setSubmittedQuestion(conversation.question)
    setDraft('')
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    submitDraft()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return

    event.preventDefault()
    submitDraft()
  }

  return (
    <PageShell
      railContent={(
        <AgentConversationHistory
          activeConversationId={activeConversationId}
          conversations={conversations}
          onOpen={openConversation}
        />
      )}
      wide
    >
      <PageContent>
        <section className="research-agent-page" aria-label="研究 Agent 对话">
          <div className="research-agent-page__inner">
            <header className="research-agent-page__heading">
              <h1 id="research-agent-title">你想研究什么？</h1>
            </header>

            <form className="research-agent-page__form" onSubmit={handleSubmit}>
              <div className="research-agent-page__composer">
                <textarea
                  aria-label="描述研究现象"
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="描述一个现象，或问一个研究问题"
                  rows={3}
                  value={draft}
                />
                <footer>
                  <span>Enter 发送 · Shift + Enter 换行</span>
                  <button
                    aria-label="发送给研究 Agent"
                    className="research-agent-page__send"
                    disabled={!canSubmit}
                    type="submit"
                  >
                    <ArrowUpIcon aria-hidden="true" size={20} weight="regular" />
                  </button>
                </footer>
              </div>

              <div className="research-agent-page__starters" aria-label="研究问题示例">
                <span>可以从这里开始</span>
                <div>
                  {starterQuestions.map((question) => (
                    <button key={question} type="button" onClick={() => setDraft(question)}>
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            </form>

            {submittedQuestion ? (
              <div
                aria-label="对话预览"
                aria-live="polite"
                className="research-agent-page__turns"
                role="log"
              >
                <div className="research-agent-page__turn research-agent-page__turn--user">
                  <span>你</span>
                  <p>{submittedQuestion}</p>
                </div>
                <div className="research-agent-page__turn">
                  <span>研究 Agent</span>
                  <p>当前只演示对话界面，尚未连接研究模型。</p>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </PageContent>
    </PageShell>
  )
}
