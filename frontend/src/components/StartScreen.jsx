import { useState } from 'react'

function StartScreen({ onStart, busy, error }) {
  const [problem, setProblem] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const text = problem.trim()
    if (!text) return
    onStart(text)
  }

  return (
    <div className="start-screen">
      <h1>RESOLVE</h1>
      <p className="tagline">
        Don&apos;t just tell me what to do. Work toward resolving the problem.
      </p>
      <form className="start-form" onSubmit={handleSubmit}>
        <label htmlFor="problem">What problem can I help you resolve?</label>
        <textarea
          id="problem"
          value={problem}
          onChange={(event) => setProblem(event.target.value)}
          placeholder="For example: My laptop warranty claim was rejected after two months of normal use."
          rows={4}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !problem.trim()}>
          {busy ? 'Starting…' : 'Start Case'}
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
    </div>
  )
}

export default StartScreen