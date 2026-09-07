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
      <div className="panel-heading">
        <h2>Conversation</h2>
      </div>
      <div className="messages">
        {messages.length === 0 ? (
          <p className="empty-hint">No messages yet.</p>
        ) : (
          messages.map((message, index) => (
            <div key={index} className={`message message-${message.role}`}>
              <span className="message-author">
                {message.role === 'user' ? 'You' : 'RESOLVE'}
              </span>
              <div className="message-text">{message.content}</div>
            </div>
          ))
        )}
        {busy ? (
          <div className="message message-assistant message-busy">
            <span className="message-author">RESOLVE</span>
            <div className="message-text">…</div>
          </div>
        ) : null}
      </div>
      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type a message…"
          aria-label="Message"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}

export default ChatPanel