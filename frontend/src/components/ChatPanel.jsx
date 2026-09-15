import { useState } from 'react'

function ChatPanel({ messages, onSend, busy }) {
  const [draft, setDraft] = useState('')

  function handleSubmit(event) {
    event.preventDefault()
    const text = draft.trim()

    if (!text || busy) return

    onSend(text)
    setDraft('')
  }

  return (
    <section className="chat-panel">
      <div className="chat-panel-header">
        <div>
          <span className="section-eyebrow">YOUR CASE</span>
          <h2>Conversation</h2>
          <p>Work through the details with RESOLVE.</p>
        </div>

        <span className="chat-status">
          <span className="chat-status-dot" />
          AI assistant
        </span>
      </div>

      <div className="messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <div className="chat-empty-icon">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M7 18.5 3.5 21l1.2-4.6A8.4 8.4 0 0 1 3 11.5C3 6.8 7 3 12 3s9 3.8 9 8.5-4 8.5-9 8.5c-1.8 0-3.5-.5-5-1.5Z"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <strong>Tell us what happened</strong>
            <p>
              Share the details of your dispute. RESOLVE will help organize
              the case and work toward the next step.
            </p>
          </div>
        ) : (
          <div className="message-list">
            {messages.map((message, index) => {
              const isUser = message.role === 'user'

              return (
                <div
                  key={index}
                  className={`message message-${message.role}`}
                >
                  <div className="message-avatar" aria-hidden="true">
                    {isUser ? (
                      <span>You</span>
                    ) : (
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden="true"
                      >
                        <path
                          d="M12 4.5 14 7l3-.5-.5 3L19 12l-2.5 2.5.5 3-3-.5-2 2.5-2-2.5-3 .5.5-3L5 12l2.5-2.5-.5-3 3 .5L12 4.5Z"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M9.5 12h.01M14.5 12h.01"
                          stroke="currentColor"
                          strokeWidth="2.2"
                          strokeLinecap="round"
                        />
                      </svg>
                    )}
                  </div>

                  <div className="message-body">
                    <div className="message-author">
                      {isUser ? 'You' : 'RESOLVE'}
                    </div>

                    <div className="message-text">
                      {message.content}
                    </div>
                  </div>
                </div>
              )
            })}

            {busy ? (
              <div className="message message-assistant message-busy">
                <div className="message-avatar" aria-hidden="true">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <path
                      d="M12 4.5 14 7l3-.5-.5 3L19 12l-2.5 2.5.5 3-3-.5-2 2.5-2-2.5-3 .5.5-3L5 12l2.5-2.5-.5-3 3 .5L12 4.5Z"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>

                <div className="message-body">
                  <div className="message-author">RESOLVE</div>
                  <div className="typing-indicator" aria-label="RESOLVE is thinking">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <div className="chat-input-wrap">
          <input
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask something or add more details…"
            aria-label="Message"
            disabled={busy}
          />

          <button
            type="submit"
            disabled={busy || !draft.trim()}
            aria-label="Send message"
          >
            {busy ? (
              <span className="send-spinner" aria-hidden="true" />
            ) : (
              <svg
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M5 12h13"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
                <path
                  d="m13 6 6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>

        <p className="chat-input-hint">
          RESOLVE uses your conversation to build and refine the case.
        </p>
      </form>
    </section>
  )
}

export default ChatPanel