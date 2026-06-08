<template>
  <div class="chat-area">
    <div v-if="!store.currentSession" class="welcome-screen">
      <div class="welcome-content">
        <div class="welcome-icon">
          <span class="poem-icon">知</span>
        </div>
        <h1 class="title-chinese">企业级智能文档问答平台</h1>
        <p class="welcome-desc">智能管理企业知识库，精准回答问题</p>
        <div class="feature-list">
          <div class="feature-item">📚 智能问答</div>
          <div class="feature-item">📖 文档管理</div>
          <div class="feature-item">🎨 智能检索</div>
        </div>
        <button class="classic-btn classic-btn-primary" @click="startChat">
          开始对话
        </button>
      </div>
    </div>

    <div v-else class="chat-content">
      <div class="chat-header">
        <h2 class="title-chinese">{{ store.currentSession.title }}</h2>
        <div class="header-actions">
          <button class="header-btn" @click="clearChat">
            <span>🗑️</span>
          </button>
        </div>
      </div>

      <div ref="messagesContainer" class="messages-container">
        <div
          v-for="(message, index) in store.currentSession.messages"
          :key="message.id"
          class="message-wrapper"
          :class="{ 'user-message': message.role === 'user' }"
          :style="{ animationDelay: `${index * 0.05}s` }"
        >
          <div class="message-bubble">
            <div class="message-avatar">
              <span v-if="message.role === 'user'">你</span>
              <span v-else>智</span>
            </div>
            <div class="message-content">
              <!-- Markdown 双轨渲染：流式纯文本 / 完成后富文本 -->
              <div
                v-if="message.role === 'assistant' && message.status === 'completed'"
                class="message-text markdown-body"
                v-html="renderMarkdown(message.content)"
              ></div>
              <p v-else class="message-text">{{ message.content }}</p>
              <!-- 用户消息附件展示 -->
              <div
                v-if="message.role === 'user' && message.attachments && message.attachments.length > 0"
                class="user-attachments"
              >
                <div
                  v-for="(att, idx) in message.attachments"
                  :key="idx"
                  class="user-attachment-item"
                >
                  <span class="att-icon">{{ att.fileType?.startsWith('image/') ? '🖼️' : '📄' }}</span>
                  <span class="att-name">{{ att.fileName }}</span>
                </div>
              </div>
              <!-- RAG traceability: show source citations -->
              <div
                v-if="message.role === 'assistant' && message.references && message.references.length > 0"
                class="source-citations"
              >
                <div class="citations-toggle" @click="toggleCitations(message.id)">
                  <span class="citations-icon">[ref]</span>
                  <span>参考来源 ({{ message.references.length }})</span>
                  <span class="citations-arrow">{{ expandedCitations[message.id] ? 'v' : '>' }}</span>
                </div>
                <div v-if="expandedCitations[message.id]" class="citations-list">
                  <div v-for="(ref, idx) in message.references" :key="idx" class="citation-item">
                    <div class="citation-header">
                      <span class="citation-index">[{{ idx + 1 }}]</span>
                      <span class="citation-score">
                        相似度 {{ ((1 - ref.distance) * 100).toFixed(0) }}%
                      </span>
                      <span v-if="ref.metadata && ref.metadata.source" class="citation-source">
                        来源: {{ ref.metadata.source }}
                      </span>
                    </div>
                    <p class="citation-snippet">{{ ref.content }}</p>
                  </div>
                </div>
              </div>
              <div v-if="message.status && message.status !== 'completed'" class="message-status">
                <span v-if="message.status === 'pending'" class="status-badge status-pending">排队中...</span>
                <span v-else-if="message.status === 'processing'" class="status-badge status-processing">处理中...</span>
                <span v-else-if="message.status === 'failed'" class="status-badge status-failed">失败</span>
              </div>
              <div class="message-meta">
                <span class="message-time">{{ formatTime(message.timestamp) }}</span>
                <span v-if="message.route" class="route-tag">{{ routeLabel(message.route) }}</span>
              </div>
              <!-- 工具调用折叠面板 — 取代旧的 tool-tag -->
              <ToolCallPanel
                v-if="message.toolCalls && message.toolCalls.length > 0"
                :calls="message.toolCalls"
              />
            </div>
          </div>
        </div>

        <div v-if="store.isStreaming" class="typing-indicator">
          <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span class="typing-text">{{ loadingText }}</span>
        </div>
      </div>

      <div class="input-area">
        <!-- 文件附件栏 -->
        <FileAttachmentBar ref="attachmentBarRef" @file-ids-change="onFileIdsChange" />
        <div class="input-wrapper">
          <textarea
            v-model="inputMessage"
            class="classic-input message-input"
            placeholder="请输入您的问题...（Shift+Enter 换行）"
            rows="2"
            @keydown.enter.exact.prevent="handleSend"
            @keydown.escape="handleCancelRequest"
          ></textarea>
          <button
            class="send-btn"
            :disabled="(!inputMessage.trim() && !store.isStreaming) || store.isStreaming"
            @click="store.isStreaming ? handleCancelRequest() : handleSend()"
          >
            <span>{{ store.isStreaming ? '停止' : '发送' }}</span>
          </button>
        </div>
        <div class="input-actions">
          <label class="checkbox-label">
            <input
              type="checkbox"
              :checked="store.settings.useRag"
              @change="store.updateSettings({ useRag: !store.settings.useRag })"
            />
            <span>使用知识库</span>
          </label>
          <span class="mode-indicator">
            <span class="mode-badge">异步模式</span>
            <span class="mode-hint">发送后可继续提问</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useMarkdown } from '@/composables/useMarkdown'
import ToolCallPanel from '@/components/ToolCallPanel.vue'
import FileAttachmentBar from '@/components/FileAttachmentBar.vue'

defineOptions({ name: 'ChatArea' })

const store = useChatStore()
const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const attachmentBarRef = ref<InstanceType<typeof FileAttachmentBar> | null>(null)
const { render: renderMarkdown } = useMarkdown()

// 当前已上传的文件 ID 列表
const fileIds = ref<string[]>([])

function onFileIdsChange(ids: string[]) {
  fileIds.value = ids
}

// Source citation expand state
const expandedCitations = ref<Record<string, boolean>>({})

function toggleCitations(messageId: string) {
  expandedCitations.value[messageId] = !expandedCitations.value[messageId]
}

// 动态 loading 文字：根据最新 assistant 消息的 loadingPhase 显示
const loadingText = computed(() => {
  const msgs = store.currentSession?.messages
  if (!msgs || msgs.length === 0) return '正在思考...'
  const last = msgs[msgs.length - 1]
  if (last.role !== 'assistant') return '正在思考...'
  const phase = last.loadingPhase
  const phaseMap: Record<string, string> = {
    thinking: '正在思考...',
    searching: '正在检索知识库...',
    analyzing: '正在分析...',
    generating: '正在生成回答...',
  }
  return phaseMap[phase || ''] || '正在思考...'
})

// 路由标签文字
function routeLabel(route: string | undefined): string {
  const map: Record<string, string> = {
    chat: '闲聊',
    rag: '知识库',
    agent: '智能代理',
    multimodal: '多模态',
  }
  return map[route || ''] || ''
}

console.log('[ChatArea] Current session:', store.currentSession)
console.log('[ChatArea] Current session ID:', store.currentSession?.id)
console.log('[ChatArea] Messages count:', store.currentSession?.messages.length)

function startChat() {
  console.log('[ChatArea] startChat called')
  store.createSession()
  console.log('[ChatArea] After createSession, current session:', store.currentSession)
}

function handleSend() {
  if (!inputMessage.value.trim() || store.isStreaming) return

  const message = inputMessage.value.trim()
  inputMessage.value = ''

  console.log('[ChatArea] Sending message:', message)
  console.log('[ChatArea] File IDs:', fileIds.value)

  // 收集附件信息用于用户消息展示
  const attachmentInfos = attachmentBarRef.value?.getFileInfos() || []

  // 携带文件 ID 和附件信息发送
  store.sendMessageAsync(message, fileIds.value, attachmentInfos)

  // 发送后清空附件
  attachmentBarRef.value?.clearAll()
  fileIds.value = []

  nextTick(() => {
    scrollToBottom()
  })
}

function handleCancelRequest() {
  store.cancelRequest()
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function formatTime(date: Date): string {
  return new Date(date).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

function clearChat() {
  if (store.currentSession) {
    store.currentSession.messages = []
    store.currentSession.title = '新对话'
  }
}

watch(() => {
  return store.currentSession ? store.currentSession.messages.length : 0
}, () => {
  nextTick(scrollToBottom)
})
</script>

<style scoped>
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-paper);
}

.welcome-screen {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-paper) 0%, var(--color-paper-warm) 100%);
}

.welcome-content {
  text-align: center;
  padding: 40px;
}

.welcome-icon {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-light) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px;
}

.poem-icon {
  color: white;
  font-family: var(--font-family-chinese);
  font-size: 48px;
  font-weight: 600;
}

.welcome-content h1 {
  font-size: 28px;
  margin-bottom: 12px;
  color: var(--color-ink-black);
}

.welcome-desc {
  font-size: 16px;
  color: var(--color-ink-light);
  margin-bottom: 32px;
}

.feature-list {
  display: flex;
  justify-content: center;
  gap: 32px;
  margin-bottom: 32px;
}

.feature-item {
  font-size: 14px;
  color: var(--color-ink-light);
  padding: 8px 16px;
  background: rgba(139, 115, 85, 0.08);
  border-radius: var(--radius-md);
}

.welcome-content button {
  padding: 12px 32px;
  font-size: 16px;
}

.chat-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--color-paper-warm);
  border-bottom: 1px solid rgba(139, 115, 85, 0.15);
}

.chat-header h2 {
  font-size: 16px;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.header-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.header-btn:hover {
  background: rgba(181, 71, 71, 0.1);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-wrapper {
  display: flex;
  animation: fadeIn 0.3s ease forwards;
}

.message-wrapper.user-message {
  justify-content: flex-end;
}

.message-bubble {
  display: flex;
  gap: 12px;
  max-width: 70%;
}

.user-message .message-bubble {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-light) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
  font-family: var(--font-family-chinese);
  font-size: 14px;
  font-weight: 600;
}

.user-message .message-avatar {
  background: linear-gradient(135deg, var(--color-ink-gray) 0%, var(--color-ink-light) 100%);
}

.message-content {
  background: var(--color-paper-warm);
  border: 1px solid rgba(139, 115, 85, 0.15);
  border-radius: var(--radius-lg);
  padding: 12px 16px;
  box-shadow: var(--shadow-soft);
}

.user-message .message-content {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.message-text {
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 8px;
  color: var(--color-ink-black);
}

.user-message .message-text {
  color: white;
}

/* 用户消息附件展示 */
.user-attachments {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.user-attachment-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.85);
  max-width: 200px;
}

.att-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.att-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.message-meta {
  display: flex;
  justify-content: flex-end;
}

.message-time {
  font-size: 11px;
  color: var(--color-ink-faint);
}

.user-message .message-time {
  color: rgba(255, 255, 255, 0.7);
}

.typing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-paper-warm);
  border: 1px solid rgba(139, 115, 85, 0.15);
  border-radius: var(--radius-lg);
  max-width: 200px;
}

.typing-dots {
  display: flex;
  gap: 4px;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: typingDot 1.4s infinite ease-in-out;
}

.typing-dots span:nth-child(1) { animation-delay: 0s; }
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingDot {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.typing-text {
  font-size: 14px;
  color: var(--color-ink-light);
}

.input-area {
  padding: 16px 20px;
  background: var(--color-paper-warm);
  border-top: 1px solid rgba(139, 115, 85, 0.15);
}

.input-wrapper {
  display: flex;
  gap: 12px;
}

.message-input {
  flex: 1;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
}

.send-btn {
  padding: 12px 24px;
  background: var(--color-accent);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: var(--font-family-chinese);
  transition: all 0.2s ease;
  align-self: flex-end;
}

.send-btn:hover:not(:disabled) {
  background: var(--color-accent-light);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-ink-light);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-accent);
}

.message-status {
  margin-bottom: 8px;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
}

.status-pending {
  background: rgba(255, 193, 7, 0.15);
  color: #856404;
}

.status-processing {
  background: rgba(33, 150, 243, 0.15);
  color: #1565c0;
}

.status-failed {
  background: rgba(244, 67, 54, 0.15);
  color: #c62828;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.mode-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-badge {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(33, 150, 243, 0.15);
  color: #1565c0;
  border-radius: var(--radius-sm);
}

.mode-hint {
  font-size: 11px;
  color: var(--color-ink-faint);
}

/* Source Citations */
.source-citations {
  margin-top: 8px;
  border-top: 1px solid rgba(139, 115, 85, 0.12);
  padding-top: 8px;
}

.citations-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-accent);
  cursor: pointer;
  user-select: none;
  padding: 4px 0;
}

.citations-toggle:hover {
  color: var(--color-accent-light);
}

.citations-icon {
  font-size: 13px;
}

.citations-arrow {
  font-size: 10px;
  margin-left: auto;
}

.citations-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.citation-item {
  background: rgba(139, 115, 85, 0.05);
  border: 1px solid rgba(139, 115, 85, 0.1);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
}

.citation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.citation-index {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-accent);
}

.citation-score {
  font-size: 11px;
  color: #2196f3;
  background: rgba(33, 150, 243, 0.08);
  padding: 1px 6px;
  border-radius: 8px;
}

.citation-source {
  font-size: 11px;
  color: var(--color-ink-faint);
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}

.citation-snippet {
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-ink-light);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Route & Tool Tags */
.route-tag {
  font-size: 10px;
  color: var(--color-accent);
  background: rgba(139, 115, 85, 0.1);
  padding: 1px 6px;
  border-radius: 8px;
  margin-left: 8px;
}

.tool-tag {
  font-size: 10px;
  color: #795548;
  background: rgba(121, 85, 72, 0.08);
  padding: 1px 6px;
  border-radius: 8px;
  margin-left: 6px;
}

/* ========== Markdown 富文本渲染样式 ========== */
.markdown-body {
  word-break: break-word;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin: 16px 0 8px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--color-ink-black);
}

.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 17px; border-bottom: 1px solid rgba(139, 115, 85, 0.15); padding-bottom: 4px; }
.markdown-body h3 { font-size: 15px; }

.markdown-body p {
  margin: 6px 0;
  line-height: 1.6;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 20px;
  margin: 6px 0;
}

.markdown-body li {
  margin: 2px 0;
  line-height: 1.5;
}

.markdown-body blockquote {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--color-accent);
  background: rgba(139, 115, 85, 0.05);
  color: var(--color-ink-light);
}

.markdown-body a {
  color: var(--color-accent);
  text-decoration: underline;
}

.markdown-body a:hover {
  color: var(--color-accent-light);
}

/* 表格样式 */
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 13px;
}

.markdown-body th,
.markdown-body td {
  border: 1px solid rgba(139, 115, 85, 0.2);
  padding: 6px 12px;
  text-align: left;
}

.markdown-body th {
  background: rgba(139, 115, 85, 0.08);
  font-weight: 600;
  color: var(--color-ink-black);
}

.markdown-body tr:nth-child(even) {
  background: rgba(139, 115, 85, 0.03);
}

/* 代码块样式 */
.markdown-body pre {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 8px 0;
  line-height: 1.5;
}

.markdown-body code {
  font-family: 'Fira Code', 'Source Code Pro', 'Consolas', monospace;
  font-size: 13px;
}

.markdown-body pre code {
  color: #d4d4d4;
  background: none;
  padding: 0;
}

.markdown-body p code,
.markdown-body li code {
  background: rgba(139, 115, 85, 0.1);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
  color: #c62828;
}

/* hr 分割线 */
.markdown-body hr {
  border: none;
  border-top: 1px solid rgba(139, 115, 85, 0.15);
  margin: 16px 0;
}

.markdown-body img {
  max-width: 100%;
  border-radius: 4px;
}

.markdown-body strong {
  font-weight: 600;
  color: var(--color-ink-black);
}
</style>
