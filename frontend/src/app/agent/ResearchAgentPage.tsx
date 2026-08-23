import { ResearchAgentConversationPage } from './ResearchAgentConversationPage'
import { AppLocaleProvider } from '../i18n/AppLocaleProvider'
import { useAccount } from '../../modules/account'
import './research-agent-conversation.css'

export function ResearchAgentPage({ userId = null }: { userId?: string | null }) {
  const account = useAccount()
  const authenticatedUserId = account.sessionState.status === 'authenticated'
    ? account.sessionState.session.user.userId
    : null
  return (
    <AppLocaleProvider>
      <ResearchAgentConversationPage userId={userId ?? authenticatedUserId} />
    </AppLocaleProvider>
  )
}
