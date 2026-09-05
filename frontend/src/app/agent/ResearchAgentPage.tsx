import { ResearchAgentConversationPage } from './ResearchAgentConversationPage'
import './research-agent-conversation.css'

export function ResearchAgentPage({
  userId = null,
  introSessionId = null,
}: {
  userId?: string | null
  introSessionId?: string | null
}) {
  return <ResearchAgentConversationPage userId={userId} introSessionId={introSessionId} />
}
