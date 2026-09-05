/** An open rectangular face: the canvas remains visible through the outline. */
export function ResearchLibraryBot() {
  return <svg className="research-library-bot" viewBox="0 0 80 72" fill="none" aria-hidden="true">
    <g className="research-library-bot__paper" stroke="currentColor" strokeWidth="2.4">
      <rect x="60" y="46" width="16" height="22" />
      <path d="M64 53h8M64 59h6" />
    </g>
    <g className="research-library-bot__head">
      <rect x="22" y="20" width="36" height="27" stroke="currentColor" strokeWidth="2.4" />
      <g className="research-library-bot__gaze">
        <g className="research-library-bot__eyes" fill="currentColor">
          <rect x="31" y="30" width="5" height="5" />
          <rect x="44" y="30" width="5" height="5" />
        </g>
      </g>
    </g>
  </svg>
}
