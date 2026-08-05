import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

import { submitResearchTask } from '../../modules/socio-match-workspace'
import './foundation.css'
import { useSystemHealth } from './useSystemHealth'

interface RequestLikeError {
  readonly message: string
  readonly status?: number
}

function isRequestLikeError(error: unknown): error is RequestLikeError {
  return Boolean(
    error &&
      typeof error === 'object' &&
      'message' in error &&
      typeof error.message === 'string',
  )
}

function describeSubmitError(error: unknown): string {
  if (isRequestLikeError(error)) {
    if (!error.status || error.status >= 500) {
      return 'The service could not save this task. Please retry.'
    }
    return error.message
  }
  return 'The service could not save this task. Please retry.'
}

export function FoundationPage() {
  const navigate = useNavigate()
  const health = useSystemHealth()
  const [phenomenon, setPhenomenon] = useState('')
  const [researchIntent, setResearchIntent] = useState('')
  const [context, setContext] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const createTask = useMutation({
    mutationFn: () =>
      submitResearchTask({
        phenomenon,
        researchIntent,
        context,
      }),
    onSuccess: (task) => navigate(`/research/${task.taskId}`),
    onError: (error) => setFormError(describeSubmitError(error)),
  })

  const connectionLabel = health.isPending
    ? 'Checking API contract'
    : health.isError
      ? 'API currently unavailable'
      : 'API connected'

  function clearFormError() {
    if (formError) {
      setFormError(null)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (phenomenon.trim() === '') {
      setFormError('Please describe the phenomenon you want to study.')
      return
    }
    setFormError(null)
    createTask.mutate()
  }

  return (
    <main className="page-shell">
      <header className="masthead">
        <Link className="wordmark" to="/" aria-label="SocioMatch home">
          <span className="wordmark-mark" aria-hidden="true">
            SQ
          </span>
          <span>SocioMatch</span>
        </Link>
        <p>RESEARCH INTAKE</p>
      </header>

      <section className="opening">
        <div>
          <p className="eyebrow">Step 1 of the SocioMatch chain</p>
          <h1 className="display-title">Record the phenomenon before formal matching begins.</h1>
        </div>
        <p className="opening-lede">
          Start from a rough social observation. This step stores the original
          user wording, creates a recoverable task, and leaves theory matching
          for later stages.
        </p>
      </section>

      <section className="connection" aria-live="polite">
        <div>
          <span
            className={`connection-dot ${health.isError ? 'is-error' : ''}`}
            aria-hidden="true"
          />
          <strong>{connectionLabel}</strong>
        </div>
        {health.data ? (
          <dl>
            <div>
              <dt>Contract</dt>
              <dd>{health.data.contractVersion}</dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd>{health.data.runtimeMode}</dd>
            </div>
            <div>
              <dt>Persistence</dt>
              <dd>{health.data.persistence}</dd>
            </div>
          </dl>
        ) : null}
        {health.isError ? (
          <p className="connection-note">The form still keeps your text if the API request fails.</p>
        ) : null}
      </section>

      <section className="action-line action-line-form">
        <div>
          <p className="section-index">01 / Research intake</p>
          <h2>Describe the social phenomenon in your own words.</h2>
          <p>
            The phenomenon field is required. Research intent and context stay
            optional and are stored without extra judgment at this stage.
          </p>
        </div>
        <form className="intake-form" onSubmit={handleSubmit}>
          <label htmlFor="phenomenon">Phenomenon *</label>
          <textarea
            id="phenomenon"
            name="phenomenon"
            rows={7}
            value={phenomenon}
            onChange={(event) => {
              clearFormError()
              setPhenomenon(event.target.value)
            }}
          />

          <label htmlFor="research-intent">Research intent</label>
          <input
            id="research-intent"
            name="researchIntent"
            type="text"
            value={researchIntent}
            onChange={(event) => {
              clearFormError()
              setResearchIntent(event.target.value)
            }}
          />

          <label htmlFor="context">Context</label>
          <textarea
            id="context"
            name="context"
            rows={4}
            value={context}
            onChange={(event) => {
              clearFormError()
              setContext(event.target.value)
            }}
          />

          <button type="submit" disabled={createTask.isPending}>
            {createTask.isPending ? 'Saving task...' : 'Create research task'}
          </button>
          {formError ? (
            <p className="inline-error" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      </section>

      <footer className="architecture-line">
        <span>React</span>
        <i aria-hidden="true">-&gt;</i>
        <span>Generated SDK</span>
        <i aria-hidden="true">-&gt;</i>
        <span>OpenAPI</span>
        <i aria-hidden="true">-&gt;</i>
        <span>research_intake</span>
        <i aria-hidden="true">-&gt;</i>
        <span>SQLite</span>
      </footer>
    </main>
  )
}
