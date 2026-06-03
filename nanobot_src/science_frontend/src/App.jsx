import { useState, useRef, useCallback, useEffect } from 'react'
import { streamChat, resetSession } from './api/hermes.js'
import Header from './components/Header.jsx'
import Welcome from './components/Welcome.jsx'
import PromptCards from './components/PromptCards.jsx'
import CapabilityGrid from './components/CapabilityGrid.jsx'
import ConversationHistory from './components/ConversationHistory.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ActionBar from './components/ActionBar.jsx'
import InputBar from './components/InputBar.jsx'

const STORAGE_KEY = 'science_frontend_conversations'

function loadConversations() {
  try { const raw = localStorage.getItem(STORAGE_KEY); return raw ? JSON.parse(raw) : [] } catch { return [] }
}

function saveConversations(convs) {
  try {
    const compact = convs.map(c => ({
      ...c,
      messages: c.messages.map(m => {
        if (m.role === 'assistant') { const { trajectoryEvents, ...r } = m; return { ...r, _trajectoryCount: trajectoryEvents?.length || 0 } }
        return m
      }),
    }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(compact))
  } catch {}
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [showHome, setShowHome] = useState(true)
  const [conversations, setConversations] = useState(loadConversations)
  const [sending, setSending] = useState(false)
  const [activeTool, setActiveTool] = useState(null)
  const cancelRef = useRef(null)
  const currentConvIdRef = useRef(null)  // 当前对话的 id（用于回存）

  useEffect(() => () => cancelRef.current?.(), [])

  /** 保存当前对话到历史，回到首页 */
  function saveAndGoHome() {
    if (messages.length > 0) {
      const convId = currentConvIdRef.current || Date.now().toString()
      const firstUser = messages.find(m => m.role === 'user')
      const title = firstUser ? firstUser.content.slice(0, 40) : '新对话'
      setConversations(prev => {
        const filtered = prev.filter(c => c.id !== convId)
        return [{ id: convId, title, messages: [...messages], createdAt: Date.now() }, ...filtered]
      })
    }
    currentConvIdRef.current = null
    resetSession()
    setMessages([])
    setShowHome(true)
  }

  /** 从历史打开对话 */
  function openConversation(conv) {
    currentConvIdRef.current = conv.id
    setMessages(conv.messages)
    setShowHome(false)
  }

  /** 删除历史对话 */
  function deleteConversation(id) {
    setConversations(prev => prev.filter(c => c.id !== id))
  }

  const handleSend = useCallback((input) => {
    const text = typeof input === 'string' ? input : input.prompt
    const label = typeof input === 'string' ? null : input.label

    if (!text.trim() || sending) return

    setShowHome(false)
    setSending(true)
    setActiveTool(null)

    const userMsg = { role: 'user', content: text }
    if (label) userMsg.displayLabel = label
    const aiMsg = { role: 'assistant', content: '', toolCalls: [], reasonings: [], trajectoryEvents: [], running: true }

    // 构建完整消息列表（历史 + 新消息）
    const allMsgs = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))
    setMessages(prev => [...prev, userMsg, aiMsg])

    cancelRef.current?.()
    cancelRef.current = streamChat({
      messages: allMsgs,
      onDelta(delta) {
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant' && l.running) n[n.length - 1] = { ...l, content: l.content + delta }; return n })
      },
      onReasoning(text) {
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, reasonings: [...(l.reasonings || []), text] }; return n })
      },
      onToolStart(event) {
        setActiveTool(event.tool_name)
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, toolCalls: [...(l.toolCalls || []), { type: 'tool_start', tool_name: event.tool_name, preview: event.preview, timestamp: Date.now() }] }; return n })
      },
      onToolComplete(event) {
        setActiveTool(null)
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, toolCalls: [...(l.toolCalls || []), { type: 'tool_complete', tool_name: event.tool_name, preview: event.preview, error: event.error, timestamp: Date.now() }] }; return n })
      },
      onEvent(event) {
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, trajectoryEvents: [...(l.trajectoryEvents || []), event] }; return n })
      },
      onUsage(usage) {
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, usage: { total_tokens: usage.total_tokens } }; return n })
      },
      onComplete() {
        setSending(false); setActiveTool(null)
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, running: false }; return n })
      },
      onError(error) {
        setSending(false); setActiveTool(null)
        setMessages(prev => { const n = [...prev]; const l = n[n.length - 1]; if (l?.role === 'assistant') n[n.length - 1] = { ...l, content: l.content || `错误: ${error}`, running: false }; return n })
      },
    })
  }, [sending, messages])

  // 对话完成且不在发送中 → 存到历史
  useEffect(() => {
    if (!sending && messages.length > 0 && !messages[messages.length - 1]?.running) {
      const convId = currentConvIdRef.current || Date.now().toString()
      currentConvIdRef.current = convId
      const firstUser = messages.find(m => m.role === 'user')
      const title = firstUser ? firstUser.content.slice(0, 40) : '新对话'
      setConversations(prev => {
        const filtered = prev.filter(c => c.id !== convId)
        saveConversations([{ id: convId, title, messages: [...messages], createdAt: Date.now() }, ...filtered])
        return [{ id: convId, title, messages: [...messages], createdAt: Date.now() }, ...filtered]
      })
    }
  }, [sending])

  return (
    <div className="h-full w-full max-w-md mx-auto flex flex-col bg-white">
      <Header activeTool={activeTool} inChat={!showHome} onBack={saveAndGoHome} />

      <main className="flex-1 overflow-y-auto">
        {showHome ? (
          <div className="flex flex-col gap-6 px-4 py-6">
            <Welcome />
            <PromptCards onSend={handleSend} />
            <CapabilityGrid />
            <ConversationHistory conversations={conversations} onOpen={openConversation} onDelete={deleteConversation} />
          </div>
        ) : (
          <ChatPanel messages={messages} />
        )}
      </main>

      <div className="shrink-0 border-t border-gray-200 bg-white">
        <ActionBar messages={messages} onAction={handleSend} disabled={sending} />
        <InputBar onSend={handleSend} disabled={sending} />
      </div>
    </div>
  )
}
