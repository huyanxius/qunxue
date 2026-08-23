import { ResearchAgentConversationPage } from './ResearchAgentConversationPage'
import './research-agent-conversation.css'

export function ResearchAgentPage({ userId = null }: { userId?: string | null }) {
  return <ResearchAgentConversationPage userId={userId} />
}
