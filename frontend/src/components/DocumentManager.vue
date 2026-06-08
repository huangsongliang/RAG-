<template>
  <div class="document-page-container">
    <ChatSidebar />
    <div class="document-manager">
      <div class="manager-header">
        <h2 class="manager-title">📁 文档管理</h2>
        <button class="upload-btn" @click="showUploadModal = true">
          <span>+</span> 上传文档
        </button>
      </div>

      <div class="document-stats">
        <div class="stat-card">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总文档数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">活跃文档</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.chunks }}</div>
          <div class="stat-label">总分块数</div>
        </div>
      </div>

      <div class="document-filters">
        <div class="search-box">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索文档名称..."
            class="search-input"
          />
        </div>
        <select v-model="filterActive" class="filter-select">
          <option value="all">全部</option>
          <option value="active">仅活跃</option>
          <option value="inactive">已删除</option>
        </select>
      </div>

      <div class="document-list" v-if="documents.length > 0">
        <div
          v-for="doc in filteredDocuments"
          :key="doc.document_id"
          class="document-card"
          :class="{ inactive: !doc.is_active }"
        >
          <div class="doc-info">
            <div class="doc-icon">📄</div>
            <div class="doc-details">
              <h3 class="doc-name">{{ doc.name }}</h3>
              <p class="doc-meta">
                <span>版本 {{ doc.version }}</span>
                <span>·</span>
                <span>{{ doc.chunk_count }} 个分块</span>
                <span>·</span>
                <span>{{ formatDate(doc.created_at) }}</span>
              </p>
              <p v-if="doc.description" class="doc-description">
                {{ doc.description }}
              </p>
            </div>
          </div>
          <div class="doc-actions">
            <button
              class="action-btn view-btn"
              @click="viewDocument(doc)"
              title="查看详情"
            >
              👁️
            </button>
            <button
              class="action-btn history-btn"
              @click="showVersionHistory(doc)"
              title="版本历史"
            >
              📜
            </button>
            <button
              class="action-btn delete-btn"
              @click="confirmDelete(doc)"
              title="删除"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>

      <div class="empty-state" v-else>
        <div class="empty-icon">📭</div>
        <p>暂无文档</p>
        <button class="upload-btn secondary" @click="showUploadModal = true">
          上传第一个文档
        </button>
      </div>
    </div>

    <div class="modal-overlay" v-if="showUploadModal" @click.self="showUploadModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>上传文档</h3>
          <button class="close-btn" @click="showUploadModal = false">✕</button>
        </div>
        <form @submit.prevent="handleUpload" class="upload-form">
          <div class="form-group">
            <label>选择文件</label>
            <div class="file-upload" @click="triggerFileInput">
              <input
                ref="fileInput"
                type="file"
                class="file-input"
                accept=".txt,.md,.json,.csv"
                @change="handleFileSelect"
              />
              <div class="upload-area" :class="{ hasFile: selectedFile }">
                <span v-if="!selectedFile" class="upload-icon">📁</span>
                <span v-if="!selectedFile" class="upload-text">点击选择文件或拖拽到此处</span>
                <span v-else class="file-name">{{ selectedFile.name }}</span>
              </div>
            </div>
            <p class="file-hint">支持: .txt, .md, .json, .csv</p>
          </div>
          <div class="form-group">
            <label>文档描述（可选）</label>
            <textarea
              v-model="uploadDescription"
              placeholder="输入文档描述..."
              class="form-textarea"
              rows="3"
            ></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>分块大小</label>
              <input
                v-model.number="chunkSize"
                type="number"
                class="form-input small"
                min="100"
                max="2000"
              />
            </div>
            <div class="form-group">
              <label>分块重叠</label>
              <input
                v-model.number="chunkOverlap"
                type="number"
                class="form-input small"
                min="0"
                max="500"
              />
            </div>
          </div>
          <div class="form-actions">
            <button type="button" class="cancel-btn" @click="showUploadModal = false">
              取消
            </button>
            <button type="submit" class="submit-btn" :disabled="!selectedFile || isUploading">
              {{ isUploading ? '上传中...' : '上传' }}
            </button>
          </div>
        </form>
        <div v-if="uploadError" class="error-message">{{ uploadError }}</div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showVersionModal" @click.self="showVersionModal = false">
      <div class="modal-content version-modal">
        <div class="modal-header">
          <h3>版本历史 - {{ currentDocument?.name }}</h3>
          <button class="close-btn" @click="showVersionModal = false">✕</button>
        </div>
        <div class="version-list" v-if="versions.length > 0">
          <div
            v-for="ver in versions"
            :key="ver.version"
            class="version-item"
          >
            <div class="version-info">
              <span class="version-number">v{{ ver.version }}</span>
              <span class="version-date">{{ formatDate(ver.created_at) }}</span>
            </div>
            <div class="version-details">
              <span class="file-size">{{ formatFileSize(ver.file_size) }}</span>
              <span v-if="ver.change_log" class="change-log">{{ ver.change_log }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state small">
          <p>暂无版本历史</p>
        </div>
      </div>
    </div>

    <div class="modal-overlay" v-if="showDeleteModal" @click.self="showDeleteModal = false">
      <div class="modal-content delete-modal">
        <div class="delete-icon">⚠️</div>
        <h3>确认删除</h3>
        <p>确定要删除文档 "{{ documentToDelete?.name }}" 吗？</p>
        <p class="delete-hint">软删除可恢复，硬删除将永久删除</p>
        <div class="delete-options">
          <label class="checkbox-label">
            <input type="checkbox" v-model="hardDelete" />
            永久删除（不可恢复）
          </label>
        </div>
        <div class="form-actions">
          <button type="button" class="cancel-btn" @click="showDeleteModal = false">
            取消
          </button>
          <button type="button" class="delete-btn" @click="handleDelete">
            {{ hardDelete ? '永久删除' : '软删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="showDetailModal" class="modal-overlay" @click.self="showDetailModal = false">
      <div class="modal-content detail-modal">
        <div class="modal-header">
          <h3>📄 文档详情</h3>
          <button class="close-btn" @click="showDetailModal = false">✕</button>
        </div>
        <div class="modal-body" v-if="detailDocument">
          <div class="detail-item">
            <label>文档名称</label>
            <span>{{ detailDocument.name }}</span>
          </div>
          <div class="detail-item">
            <label>文档ID</label>
            <span class="doc-id">{{ detailDocument.document_id }}</span>
          </div>
          <div class="detail-item">
            <label>版本</label>
            <span>v{{ detailDocument.version }}</span>
          </div>
          <div class="detail-item">
            <label>分块数</label>
            <span>{{ detailDocument.chunk_count }} 个</span>
          </div>
          <div class="detail-item">
            <label>状态</label>
            <span :class="detailDocument.is_active ? 'status-active' : 'status-inactive'">
              {{ detailDocument.is_active ? '活跃' : '已删除' }}
            </span>
          </div>
          <div class="detail-item">
            <label>描述</label>
            <span>{{ detailDocument.description || '无' }}</span>
          </div>
          <div class="detail-item">
            <label>创建时间</label>
            <span>{{ formatDate(detailDocument.created_at) }}</span>
          </div>
          <div class="detail-item">
            <label>更新时间</label>
            <span>{{ formatDate(detailDocument.updated_at) }}</span>
          </div>

          <div class="preview-section">
            <button class="preview-toggle-btn" @click="togglePreview">
              {{ showPreview ? '收起内容' : '预览内容' }}
            </button>
            <div v-if="showPreview" class="preview-content">
              <div v-if="isLoadingPreview" class="preview-loading">加载中...</div>
              <pre v-else class="preview-text">{{ previewContent }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ChatSidebar from './ChatSidebar.vue'

interface Document {
  id: number
  document_id: string
  name: string
  description?: string
  chunk_count: number
  version: number
  is_active: boolean
  created_at: string
  updated_at: string
}

interface Version {
  version: number
  file_size: number
  change_log?: string
  created_at: string
}

const documents = ref<Document[]>([])
const searchQuery = ref('')
const filterActive = ref<'all' | 'active' | 'inactive'>('all')
const showUploadModal = ref(false)
const showVersionModal = ref(false)
const showDeleteModal = ref(false)
const selectedFile = ref<File | null>(null)
const uploadDescription = ref('')
const chunkSize = ref(512)
const chunkOverlap = ref(100)
const isUploading = ref(false)
const uploadError = ref('')
const currentDocument = ref<Document | null>(null)
const documentToDelete = ref<Document | null>(null)
const hardDelete = ref(false)
const versions = ref<Version[]>([])

const stats = computed(() => {
  const active = documents.value.filter(d => d.is_active).length
  const chunks = documents.value.reduce((sum, d) => sum + d.chunk_count, 0)
  return {
    total: documents.value.length,
    active,
    chunks
  }
})

const filteredDocuments = computed(() => {
  let result = documents.value

  if (filterActive.value === 'active') {
    result = result.filter(d => d.is_active)
  } else if (filterActive.value === 'inactive') {
    result = result.filter(d => !d.is_active)
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(d => d.name.toLowerCase().includes(query))
  }

  return result.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
})

const fileInput = ref<HTMLInputElement | null>(null)

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    selectedFile.value = target.files[0]
    uploadError.value = ''
  }
}

const handleUpload = async () => {
  if (!selectedFile.value) return

  isUploading.value = true
  uploadError.value = ''

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    if (uploadDescription.value) {
      formData.append('description', uploadDescription.value)
    }
    formData.append('chunk_size', chunkSize.value.toString())
    formData.append('chunk_overlap', chunkOverlap.value.toString())

    const response = await fetch('/api/documents/upload', {
      method: 'POST',
      body: formData
    })

    const result = await response.json()

    if (result.success) {
      showUploadModal.value = false
      selectedFile.value = null
      uploadDescription.value = ''

      if (result.skipped) {
        uploadError.value = ''
        alert(`⚠️ ${result.message || '该文档已存在，已跳过'}`)
      } else if (result.version) {
        uploadError.value = ''
        alert(`✅ ${result.message || '文档已更新至新版本'}`)
      }

      await fetchDocuments()
    } else {
      uploadError.value = result.error || '上传失败'
    }
  } catch (error) {
    uploadError.value = '上传失败，请重试'
  } finally {
    isUploading.value = false
  }
}

const fetchDocuments = async () => {
  try {
    const response = await fetch('/api/documents/list?include_inactive=true')
    const result = await response.json()
    documents.value = result.documents || []
  } catch (error) {
    console.error('获取文档列表失败:', error)
  }
}

const showDetailModal = ref(false)
const detailDocument = ref<Document | null>(null)
const showPreview = ref(false)
const previewContent = ref('')
const isLoadingPreview = ref(false)

const viewDocument = async (doc: Document) => {
  detailDocument.value = doc
  showDetailModal.value = true
  showPreview.value = false
  previewContent.value = ''
}

const togglePreview = async () => {
  if (showPreview.value) {
    showPreview.value = false
    return
  }

  if (!detailDocument.value) return

  isLoadingPreview.value = true
  try {
    const response = await fetch(`/api/documents/${detailDocument.value.document_id}/content`)
    const result = await response.json()
    if (result.success) {
      previewContent.value = result.content || ''
    } else {
      previewContent.value = '加载失败: ' + (result.error || '未知错误')
    }
    showPreview.value = true
  } catch (error) {
    previewContent.value = '加载失败，请重试'
  } finally {
    isLoadingPreview.value = false
  }
}

const showVersionHistory = async (doc: Document) => {
  currentDocument.value = doc
  try {
    const response = await fetch(`/api/documents/${doc.document_id}/versions`)
    const result = await response.json()
    versions.value = result.versions || []
    showVersionModal.value = true
  } catch (error) {
    console.error('获取版本历史失败:', error)
  }
}

const confirmDelete = (doc: Document) => {
  documentToDelete.value = doc
  hardDelete.value = false
  showDeleteModal.value = true
}

const handleDelete = async () => {
  if (!documentToDelete.value) return

  try {
    const response = await fetch(`/api/documents/${documentToDelete.value.document_id}?soft_delete=${!hardDelete.value}`, {
      method: 'DELETE'
    })

    const result = await response.json()

    if (result.success) {
      showDeleteModal.value = false
      documentToDelete.value = null
      await fetchDocuments()
    }
  } catch (error) {
    console.error('删除文档失败:', error)
  }
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

onMounted(() => {
  fetchDocuments()
})
</script>

<style scoped>
.document-page-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.document-manager {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.manager-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.upload-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.3s;
}

.upload-btn:hover {
  opacity: 0.9;
}

.upload-btn.secondary {
  background: #f0f0f0;
  color: #333;
}

.document-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  flex: 1;
  background: #f8f9fa;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #667eea;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-top: 4px;
}

.document-filters {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.search-box {
  flex: 1;
}

.search-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
}

.filter-select {
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.document-card {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: box-shadow 0.3s;
}

.document-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.document-card.inactive {
  opacity: 0.6;
  background: #fafafa;
}

.doc-info {
  display: flex;
  gap: 16px;
  flex: 1;
}

.doc-icon {
  font-size: 32px;
}

.doc-details {
  flex: 1;
}

.doc-name {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.doc-meta {
  font-size: 13px;
  color: #999;
  margin: 0 0 8px 0;
}

.doc-description {
  font-size: 14px;
  color: #666;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.doc-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: #f5f5f5;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.3s;
}

.action-btn:hover {
  background: #e0e0e0;
}

.action-btn.delete-btn:hover {
  background: #ffebee;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  background: #f8f9fa;
  border-radius: 16px;
}

.empty-state .empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-state p {
  color: #999;
  margin: 0 0 20px 0;
}

.empty-state.small {
  padding: 30px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 16px;
  padding: 24px;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.modal-header h3 {
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
}

.upload-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
}

.form-input {
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
}

.form-input.small {
  width: 100px;
}

.form-textarea {
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
  resize: none;
}

.form-row {
  display: flex;
  gap: 16px;
}

.file-upload {
  width: 100%;
}

.file-input {
  display: none;
}

.upload-area {
  border: 2px dashed #e0e0e0;
  border-radius: 12px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.3s;
}

.upload-area:hover {
  border-color: #667eea;
}

.upload-area.hasFile {
  border-style: solid;
  border-color: #667eea;
  background: #f0f0ff;
}

.upload-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 12px;
}

.upload-text {
  color: #999;
}

.file-name {
  color: #667eea;
  font-weight: 500;
}

.file-hint {
  font-size: 12px;
  color: #999;
  margin: 4px 0 0 0;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.cancel-btn {
  padding: 12px 24px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background: white;
  color: #666;
  cursor: pointer;
}

.submit-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.submit-btn:disabled {
  opacity: 0.5;
}

.error-message {
  padding: 12px;
  background: #ffebee;
  color: #c62828;
  border-radius: 8px;
  font-size: 14px;
  margin-top: 16px;
}

.version-modal {
  max-width: 600px;
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.version-item {
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.version-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.version-number {
  font-weight: 600;
  color: #667eea;
}

.version-date {
  font-size: 13px;
  color: #999;
}

.version-details {
  font-size: 13px;
  color: #666;
}

.change-log {
  display: block;
  margin-top: 4px;
  color: #999;
}

.delete-modal {
  text-align: center;
}

.delete-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.delete-modal h3 {
  margin: 0 0 8px 0;
}

.delete-modal p {
  margin: 0 0 20px 0;
  color: #666;
}

.delete-hint {
  font-size: 13px;
  color: #999;
}

.delete-options {
  margin-bottom: 20px;
  text-align: left;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #c62828;
}

.delete-options input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.form-actions .delete-btn {
  background: #c62828;
  color: white;
}

.detail-modal {
  max-width: 450px;
}

.detail-item {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.detail-item:last-child {
  border-bottom: none;
}

.detail-item label {
  width: 100px;
  font-weight: 500;
  color: #666;
  flex-shrink: 0;
}

.detail-item span {
  flex: 1;
  word-break: break-all;
}

.doc-id {
  font-family: monospace;
  font-size: 12px;
  color: #999;
}

.status-active {
  color: #4caf50;
}

.status-inactive {
  color: #999;
}

.preview-section {
  margin-top: 16px;
  border-top: 1px solid #e0e0e0;
  padding-top: 16px;
}

.preview-toggle-btn {
  width: 100%;
  padding: 12px;
  background: #f0f0f0;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  transition: background 0.3s;
}

.preview-toggle-btn:hover {
  background: #e0e0e0;
}

.preview-content {
  margin-top: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.preview-loading {
  text-align: center;
  color: #999;
  padding: 20px;
}

.preview-text {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 280px;
  overflow-y: auto;
}
</style>
