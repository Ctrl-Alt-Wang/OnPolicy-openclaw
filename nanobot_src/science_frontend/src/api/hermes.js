const BASE = '/api/model'
let _sessionId = 'sci-' + Date.now().toString(36)

/**
 * 重置会话（开始新对话时调用）
 */
export function resetSession() {
  _sessionId = 'sci-' + Date.now().toString(36)
}

/**
 * 发送消息并订阅 ModelChat SSE 事件流
 *
 * SSE 格式:
 *   message: ""  + reasoningMessage: "thinking:"         → 初始信号
 *   message: ""  + reasoningMessage: "[工具] 调用: xxx"  → 工具开始
 *   message: ""  + reasoningMessage: "[工具] 完成: xxx"  → 工具完成
 *   message: "text" + reasoningMessage: ""               → 正文 delta
 *   message: {"totalToken": N}                           → Token 统计
 *   message: "[stop]"                                    → 结束
 *
 * @param {object} callbacks
 * @param {Array<{role:string,content:string}>} callbacks.messages - 对话历史（最后一条 user 消息作为提问）
 * @param {(delta: string) => void} callbacks.onDelta
 * @param {(text: string) => void} callbacks.onReasoning
 * @param {(event: object) => void} callbacks.onToolStart
 * @param {(event: object) => void} callbacks.onToolComplete
 * @param {(output: string, usage: object) => void} callbacks.onComplete
 * @param {(error: string) => void} callbacks.onError
 * @param {(event: object) => void} callbacks.onEvent
 * @returns {() => void} 取消函数
 */
export function streamChat(callbacks) {
  const controller = new AbortController()
  let cancelled = false

  ;(async () => {
    try {
      const linkId = 'q-' + Date.now().toString(36)
      const body = {
        linkId,
        sessionId: _sessionId,
        userId: callbacks.userId || 1,
        messages: callbacks.messages || [],
        type: 0,
      }

      const res = await fetch(`${BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        callbacks.onError?.(err.detail || `HTTP ${res.status}`)
        return
      }

      callbacks.onEvent?.({ type: 'metadata', sessionId: _sessionId, linkId })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            callbacks.onEvent?.(event)
            dispatch(event, callbacks)
          } catch {
            // 非 JSON 行跳过
          }
        }
      }
    } catch (err) {
      if (cancelled) return
      callbacks.onError?.(err.message || '网络错误')
    }
  })()

  return () => {
    cancelled = true
    controller.abort()
  }
}

/** 中止当前对话 */
export async function abortChat() {
  try {
    await fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        linkId: 'abort-' + Date.now().toString(36),
        sessionId: _sessionId,
        type: -1,
      }),
    })
  } catch {}
}

function dispatch(event, cbs) {
  const msg = event.message
  const rsn = event.reasoningMessage || ''

  // Token 统计
  if (typeof msg === 'object' && msg !== null && msg.totalToken) {
    cbs.onUsage?.({ total_tokens: msg.totalToken })
    return
  }

  // 结束信号
  if (msg === '[stop]') {
    cbs.onComplete?.()
    return
  }

  // 工具调用
  if (!msg && rsn) {
    if (rsn === 'thinking:') return

    const toolCall = rsn.match(/^\[工具\] 调用: (.+)$/)
    if (toolCall) {
      cbs.onToolStart?.({
        tool_name: toolCall[1],
        preview: toolCall[1],
      })
      return
    }

    const toolDone = rsn.match(/^\[工具\] 完成: (.+)$/)
    if (toolDone) {
      cbs.onToolComplete?.({
        tool_name: toolDone[1],
        preview: toolDone[1],
        error: toolDone[1].includes('失败'),
      })
      return
    }

    // 其他 reasoning 文本
    cbs.onReasoning?.(rsn)
    return
  }

  // 正文 delta
  if (msg) {
    cbs.onDelta?.(msg)
  }
}

/**
 * 下载轨迹 JSONL
 */
export function downloadTrajectory(events, prompt) {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const prefix = (prompt || 'trajectory').slice(0, 20).replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_')
  const filename = `trajectory_${prefix}_${ts}.jsonl`

  const header = JSON.stringify({
    type: 'metadata',
    prompt,
    sessionId: _sessionId,
    collected_at: new Date().toISOString(),
    event_count: events.length,
  })

  const body = events.map(e => JSON.stringify(e)).join('\n')
  const content = header + '\n' + body

  const blob = new Blob([content], { type: 'application/x-ndjson' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
