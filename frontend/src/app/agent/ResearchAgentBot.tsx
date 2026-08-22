import './research-agent-bot.css'

export function ResearchAgentBot() {
  return (
    <span aria-hidden="true" className="research-agent-bot" data-research-agent-bot>
      <svg fill="none" viewBox="0 0 24 24">
        <g className="research-agent-bot__face">
          <rect className="research-agent-bot__frame" height="14" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" width="16" x="4" y="5" />
          <g className="research-agent-bot__gaze">
            <g className="research-agent-bot__blink" fill="currentColor">
              <rect className="research-agent-bot__eye research-agent-bot__eye--left" height="3" width="3" x="8" y="10" />
              <rect className="research-agent-bot__eye research-agent-bot__eye--right" height="3" width="3" x="13" y="10" />
            </g>
          </g>
        </g>
      </svg>
    </span>
  )
}
