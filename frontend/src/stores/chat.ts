import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UnifiedChatEvent, ToolCallSummary } from '@/types/unified-chat'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  references?: Array<{
    content: string
    distance: number
    metadata?: Record<string, any>
  }>
  status?: 'pending' | 'processing' | 'completed' | 'failed'
  taskId?: string
  /** 第三步新增字段 */
  attachments?: Array<{ fileId: string; fileName: string; fileType: string }>
  route?: 'chat' | 'rag' | 'agent' | 'multimodal'
  toolCalls?: ToolCallSummary[]
  loadingPhase?: string
}

export interface ChatSession {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<ChatSession[]>([])
  const currentSessionId = ref<string | null>(null)
  const isStreaming = ref(false)
  const settings = ref({
    useRag: true,
    topK: 3,
    temperature: 0.7
  })

  // AbortController 用于取消进行中的请求
  const abortController = ref<AbortController | null>(null)

  const currentSession = computed(() => {
    return sessions.value.find(s => s.id === currentSessionId.value) || null
  })

  const sortedSessions = computed(() => {
    return [...sessions.value].sort((a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
  })

  function createSession(): ChatSession {
    const session: ChatSession = {
      id: Date.now().toString(),
      title: '新对话',
      messages: [],
      createdAt: new Date()
    }
    console.log('[ChatStore] Creating session:', session)
    sessions.value.push(session)
    console.log('[ChatStore] Sessions after push:', sessions.value.length, 'sessions')
    console.log('[ChatStore] Sorted sessions:', sortedSessions.value.length, 'sorted sessions')
    currentSessionId.value = session.id
    console.log('[ChatStore] Current session ID:', currentSessionId.value)
    return session
  }

  function selectSession(sessionId: string) {
    currentSessionId.value = sessionId
  }

  function deleteSession(sessionId: string) {
    const index = sessions.value.findIndex(s => s.id === sessionId)
    if (index !== -1) {
      sessions.value.splice(index, 1)
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = sessions.value[0]?.id || null
      }
    }
  }

  async function sendMessage(content: string): Promise<void> {
    console.log('[ChatStore] sendMessage called with:', content)
    if (!currentSession.value) {
      console.log('[ChatStore] No current session, creating new one')
      createSession()
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date()
    }
    currentSession.value!.messages.push(userMessage)

    if (currentSession.value!.title === '新对话') {
      currentSession.value!.title = content.substring(0, 20) + (content.length > 20 ? '...' : '')
    }

    isStreaming.value = true

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: content,
          session_id: currentSession.value!.id,
          use_rag: settings.value.useRag,
          top_k: settings.value.topK
        })
      })

      const data = await response.json()

      const assistantMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: data.answer,
        timestamp: new Date(),
        references: data.references || []
      }
      currentSession.value!.messages.push(assistantMessage)
    } catch (error) {
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: 'assistant',
        content: '抱歉，我暂时无法回答您的问题。',
        timestamp: new Date()
      }
      currentSession.value!.messages.push(errorMessage)
    } finally {
      isStreaming.value = false
    }
  }

  async function sendMessageStream(content: string): Promise<void> {
    if (!currentSession.value) {
      createSession()
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date()
    }
    currentSession.value!.messages.push(userMessage)

    if (currentSession.value!.title === '新对话') {
      currentSession.value!.title = content.substring(0, 20) + (content.length > 20 ? '...' : '')
    }

    isStreaming.value = true

    const assistantMessage: Message = {
      id: Date.now().toString(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      references: []
    }
    currentSession.value!.messages.push(assistantMessage)

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: content,
          session_id: currentSession.value!.id,
          use_rag: settings.value.useRag,
          top_k: settings.value.topK
        })
      })

      if (!response.body) {
        assistantMessage.content = '抱歉，流式响应不可用。'
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)

            if (data === '[DONE]') {
              break
            }

            try {
              const parsed = JSON.parse(data)

              if (parsed.type === 'references') {
                assistantMessage.references = parsed.data
              } else {
                assistantMessage.content += parsed
                currentSession.value!.messages = [...currentSession.value!.messages]
              }
            } catch {
              assistantMessage.content += data
              currentSession.value!.messages = [...currentSession.value!.messages]
            }
          }
        }
      }
    } catch (error) {
      assistantMessage.content = '抱歉，流式响应出错。'
    } finally {
      isStreaming.value = false
    }
  }

  function updateSettings(newSettings: Partial<typeof settings.value>) {
    settings.value = { ...settings.value, ...newSettings }
  }

  /** 取消进行中的请求 */
  function cancelRequest(): void {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    isStreaming.value = false
  }

  /** 从后端加载已登录用户的会话列表 */
  async function fetchSessions(): Promise<void> {
    const token = localStorage.getItem('access_token')
    if (!token) return
    try {
      const response = await fetch('/api/chat/sessions', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return
      const data = await response.json()
      for (const s of data.sessions || []) {
        if (!sessions.value.find(x => x.id === s.id)) {
          sessions.value.push({
            id: s.id,
            title: s.title || '新对话',
            messages: [],
            createdAt: new Date(s.created_at || Date.now()),
          })
        }
      }
    } catch (e) {
      console.error('[ChatStore] 加载会话列表失败:', e)
    }
  }

  /** 加载指定会话的历史消息（从后端 Redis） */
  async function loadSessionMessages(sessionId: string): Promise<void> {
    const token = localStorage.getItem('access_token')
    try {
      const response = await fetch(`/api/chat/sessions/${sessionId}/messages`)
      if (!response.ok) return
      const data = await response.json()
      const session = sessions.value.find(s => s.id === sessionId)
      if (session && data.messages) {
        session.messages = data.messages.map((m: { role: string; content: string; timestamp: string }) => ({
          id: `${sessionId}_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: new Date(m.timestamp || Date.now()),
        }))
      }
    } catch (e) {
      console.error('[ChatStore] 加载消息历史失败:', e)
    }
  }

  async function sendMessageAsync(
    content: string,
    fileIds: string[] = [],
    attachmentInfos: Array<{ fileId: string; fileName: string; fileType: string }> = [],
  ): Promise<void> {
    if (!currentSession.value) {
      createSession()
    }

    // 取消上一个请求
    if (abortController.value) {
      abortController.value.abort()
    }
    abortController.value = new AbortController()

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
      attachments: attachmentInfos,
    }
    currentSession.value!.messages.push(userMessage)

    if (currentSession.value!.title === '新对话') {
      currentSession.value!.title = content.substring(0, 20) + (content.length > 20 ? '...' : '')
    }

    isStreaming.value = true

    const assistantMessage: Message = {
      id: Date.now().toString() + '_a',
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      references: [],
      status: 'processing',
    }
    currentSession.value!.messages.push(assistantMessage)

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/chat/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: content,
          session_id: currentSession.value!.id,
          use_rag: settings.value.useRag,
          top_k: settings.value.topK,
          file_ids: fileIds,
        }),
        signal: abortController.value.signal,
      })

      if (!response.ok) {
        const errText = await response.text()
        console.error(`[ChatStore] API error ${response.status}:`, errText)
        throw new Error(`服务器错误 (${response.status})`)
      }

      if (!response.body) {
        throw new Error('流式响应不可用')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let streamChunkCount = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          console.log(`[ChatStore] SSE stream done, chunks=${streamChunkCount}, contentLen=${assistantMessage.content.length}, finalBuffer="${buffer.slice(0, 50)}"`)
          break
        }

        streamChunkCount++
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        console.log(`[ChatStore] chunk[${streamChunkCount}]: len=${chunk.length}, content="${chunk.replace(/\n/g, '\\n').slice(0, 100)}"`)

        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''
        console.log(`[ChatStore] split into ${lines.length} lines, leftover buffer="${buffer.slice(0, 30)}"`)

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i]
          console.log(`[ChatStore] line[${i}]: "${line.slice(0, 80)}"`)

          // 跳过 SSE 注释行（以 : 开头，如心跳 ": ping"）
          let dataStr = line.trim()
          if (!dataStr || dataStr.startsWith(':')) {
            console.log(`[ChatStore]   -> skipped (comment)`)
            continue
          }
          // 兼容两种 SSE 格式：带 "data: " 前缀 或 直接 JSON
          if (dataStr.startsWith('data: ')) {
            dataStr = dataStr.slice(6).trim()
          }
          if (!dataStr) {
            console.log(`[ChatStore]   -> skipped (empty)`)
            continue
          }

          try {
            const event: UnifiedChatEvent = JSON.parse(dataStr)
            console.log(`[ChatStore]   -> parsed event type=${event.type}`)
            handleUnifiedEvent(event, assistantMessage)
          } catch (parseErr) {
            // 兜底：当作纯文本
            console.warn('[ChatStore]   -> parse failed:', (parseErr as Error).message)
            assistantMessage.content += dataStr
          }

          // 触发 Vue 响应式更新
          currentSession.value!.messages = [...currentSession.value!.messages]
        }
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        console.log('[ChatStore] 请求已取消')
        assistantMessage.content = ''
        assistantMessage.status = 'failed'
      } else {
        console.error('[ChatStore] sendMessage error:', error)
        assistantMessage.content = `抱歉，请求失败。${error instanceof Error ? error.message : ''}`
        assistantMessage.status = 'failed'
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
    }
  }

  /** 统一事件处理器 */
  function handleUnifiedEvent(event: UnifiedChatEvent, msg: Message): void {
    // 调试日志：追踪关键事件
    if (event.type === 'content' || event.type === 'metadata') {
      console.log(`[ChatStore] event: type=${event.type}`,
        event.type === 'content' ? `data="${(event as {data:string}).data.slice(0,40)}"` :
        `completion="${(event as {completion:string}).completion}"`)
    }

    switch (event.type) {
      case 'status':
        // 更新 loading 状态（供 ChatArea 动画文字使用）
        msg.loadingPhase = event.phase
        break

      case 'content':
        msg.content += (event as {data: string}).data
        break

      case 'tool_start':
        // 工具调用开始 — incremental 添加到 toolCalls 列表
        if (!msg.toolCalls) {
          msg.toolCalls = []
        }
        msg.toolCalls = [
          ...msg.toolCalls,
          {
            step: event.step,
            tool: event.tool,
            input: typeof event.input === 'string' ? { _raw: event.input } : event.input,
            success: false,
            summary: '执行中...',
          },
        ]
        break

      case 'tool_end':
        // 工具调用结束 — 更新对应步骤的状态
        if (msg.toolCalls) {
          msg.toolCalls = msg.toolCalls.map(c =>
            c.step === event.step
              ? { ...c, success: event.success, summary: event.summary }
              : c,
          )
        }
        break

      case 'metadata':
        // 后端返回 "complete" → 映射为前端 Message 的 "completed"
        const completionMap: Record<string, Message['status']> = {
          complete: 'completed',
          partial: 'completed',
          degraded: 'completed',
        }
        msg.status = completionMap[event.completion] || 'failed'
        // 清空 loadingPhase，停止 typing indicator
        msg.loadingPhase = undefined
        msg.references = (event.sources || []).map(s => ({
          content: s.source,
          distance: s.score != null ? 1 - s.score : 0,
          metadata: s.metadata,
        }))
        msg.route = event.route
        if (event.tool_calls?.length) {
          // metadata 中的 tool_calls 为最终完整版本，覆盖 incremental 构建的
          msg.toolCalls = event.tool_calls
        }
        break
    }
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    sortedSessions,
    isStreaming,
    settings,
    createSession,
    selectSession,
    deleteSession,
    sendMessage,
    sendMessageStream,
    sendMessageAsync,
    updateSettings,
    cancelRequest,
    handleUnifiedEvent,
    fetchSessions,
    loadSessionMessages,
  }
})
