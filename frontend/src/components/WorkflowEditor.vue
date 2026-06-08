<template>
  <div class="wf-page">
    <!-- 顶部工具栏 -->
    <header class="wf-header">
      <button class="back-btn" @click="goBack">← 返回</button>
      <h1 class="wf-title">工作流编辑器</h1>
      <div class="wf-actions">
        <span class="version-badge" v-if="currentWorkflow">v{{ currentWorkflow.version }}</span>
        <button class="btn btn-save" @click="handleSave" :disabled="!currentWorkflow">保存</button>
        <button class="btn btn-run" @click="handleExecute" :disabled="!currentWorkflow">▶ 执行</button>
        <button class="btn" @click="showVersionDialog = true" :disabled="!currentWorkflow">版本</button>
      </div>
    </header>

    <div class="wf-body">
      <!-- 左侧：工作流列表 + 节点面板 -->
      <aside class="wf-left">
        <div class="panel">
          <div class="panel-header">
            <h4>工作流列表</h4>
            <button class="icon-btn" @click="createWorkflow" title="新建">+</button>
          </div>
          <ul class="wf-list">
            <li v-for="wf in workflowList" :key="wf.id"
                :class="['wf-item', { active: currentWorkflow?.id === wf.id }]"
                @click="selectWorkflow(wf)">
              <span class="wf-name">{{ wf.name || wf.id }}</span>
            </li>
          </ul>
          <div v-if="workflowList.length === 0" class="empty-hint">暂无工作流</div>
        </div>

        <div class="panel" v-if="currentWorkflow">
          <div class="panel-header"><h4>节点面板</h4></div>
          <div class="palette">
            <div v-for="nt in nodeTypes" :key="nt.type"
                 class="palette-item"
                 draggable="true"
                 @dragstart="onDragStart($event, nt.type)"
                 @click="addNode(nt.type)">
              <span class="palette-icon">{{ nt.icon }}</span>
              <span>{{ nt.label }}</span>
            </div>
          </div>
        </div>
      </aside>

      <!-- 中间：画布 -->
      <main class="wf-canvas" v-if="currentWorkflow">
        <svg class="connectors" v-if="connections.length > 0">
          <line v-for="(c, i) in connections" :key="i"
                :x1="c.x1" :y1="c.y1" :x2="c.x2" :y2="c.y2"
                stroke="rgba(139,115,85,0.3)" stroke-width="2"
                marker-end="url(#arrowhead)" />
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="rgba(139,115,85,0.4)" />
            </marker>
          </defs>
        </svg>

        <div class="nodes-container">
          <div v-for="(node, idx) in nodeLayers" :key="node.id"
               :class="['wf-node-card', { selected: selectedNode?.id === node.id }]"
               :style="{ top: (idx * 130 + 20) + 'px' }"
               @click="selectNode(node)">
            <div class="node-header">
              <span class="node-icon">{{ typeMeta(node.type).icon }}</span>
              <span class="node-name">{{ node.name }}</span>
              <span class="node-type-tag">{{ typeMeta(node.type).label }}</span>
            </div>
            <div class="node-body" v-if="node.type === 'task'">
              <span class="node-detail">任务: {{ node.task_type }}</span>
            </div>
            <div class="node-body" v-else-if="node.type === 'condition'">
              <span class="node-detail">条件: {{ node.condition }}</span>
            </div>
            <button class="node-delete" @click.stop="deleteNode(node.id)">✕</button>
          </div>
        </div>
        <div class="canvas-empty" v-if="currentWorkflow.nodes.length === 0">
          从左侧面板拖拽或点击添加节点
        </div>
      </main>
      <main class="wf-canvas wf-canvas-empty" v-else>
        <div class="canvas-empty">选择或新建一个工作流开始编辑</div>
      </main>

      <!-- 右侧：属性面板 -->
      <aside class="wf-right" v-if="selectedNode">
        <div class="panel">
          <div class="panel-header"><h4>节点属性</h4></div>
          <div class="prop-form">
            <div class="prop-row">
              <label>名称</label>
              <input v-model="editingNode.name" class="prop-input" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'task'">
              <label>任务类型</label>
              <select v-model="editingNode.task_type" class="prop-input">
                <option value="log">日志</option>
                <option value="set_variable">设置变量</option>
                <option value="compute">计算</option>
                <option value="delay">延迟</option>
              </select>
            </div>
            <div class="prop-row" v-if="editingNode.type === 'task' && editingNode.task_type === 'log'">
              <label>日志消息</label>
              <input v-model="editingNode.task_config.message" class="prop-input" placeholder="消息内容" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'task' && editingNode.task_type === 'set_variable'">
              <label>变量名</label>
              <input v-model="editingNode.task_config.key" class="prop-input" />
              <label>值</label>
              <input v-model="editingNode.task_config.value" class="prop-input" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'task' && editingNode.task_type === 'compute'">
              <label>表达式</label>
              <input v-model="editingNode.task_config.expression" class="prop-input" placeholder="x + 1" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'task' && editingNode.task_type === 'delay'">
              <label>延迟(秒)</label>
              <input v-model.number="editingNode.task_config.seconds" class="prop-input" type="number" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'condition'">
              <label>条件表达式</label>
              <input v-model="editingNode.condition" class="prop-input" placeholder="count > 5" />
            </div>
            <div class="prop-row" v-if="editingNode.type === 'loop'">
              <label>循环条件</label>
              <input v-model="editingNode.loop_condition" class="prop-input" placeholder="count < 10" />
            </div>
            <div class="prop-row" v-if="editingNode.type !== 'end'">
              <label>下一节点</label>
              <select v-model="editingNode.next_nodes[0]" class="prop-input">
                <option value="">-- 不连接 --</option>
                <option v-for="n in currentWorkflow.nodes.filter(x => x.id !== editingNode.id)"
                        :key="n.id" :value="n.id">{{ n.name }}</option>
              </select>
            </div>
            <button class="btn btn-save prop-save" @click="applyNodeEdit">应用修改</button>
          </div>
        </div>
      </aside>
    </div>

    <!-- 版本管理弹窗 -->
    <el-dialog v-model="showVersionDialog" title="版本管理" width="500px">
      <el-table :data="versionList" stripe max-height="300">
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="description" label="描述" />
        <el-table-column prop="created_at" label="时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small">活跃</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 执行结果弹窗 -->
    <el-dialog v-model="showExecDialog" title="执行结果" width="560px">
      <div v-if="execResult">
        <div class="exec-status">
          <el-tag :type="statusTag(execResult.status)">{{ execResult.status }}</el-tag>
          <span class="exec-id">{{ execResult.execution_id }}</span>
        </div>
        <div class="exec-output" v-if="execResult.output">
          <pre>{{ JSON.stringify(execResult.output, null, 2) }}</pre>
        </div>
        <div class="exec-error" v-if="execResult.error">{{ execResult.error }}</div>
      </div>
      <div v-else class="exec-loading">执行中...</div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { workflowApi, type WorkflowNode, type WorkflowDefinition, type VersionInfo, type ExecutionResult, type NodeType } from '@/api/workflow'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const notifStore = useNotificationStore()

// ===== 工作流列表 =====
const workflowList = ref<{ id: string; name?: string }[]>([])
const currentWorkflow = ref<WorkflowDefinition | null>(null)
const selectedNode = ref<WorkflowNode | null>(null)
const editingNode = reactive<WorkflowNode>({} as WorkflowNode)

// ===== 版本 =====
const showVersionDialog = ref(false)
const versionList = ref<VersionInfo[]>([])

// ===== 执行 =====
const showExecDialog = ref(false)
const execResult = ref<ExecutionResult | null>(null)

// ===== 节点类型定义 =====
const nodeTypes = [
  { type: 'start' as NodeType, label: '开始', icon: '▶' },
  { type: 'end' as NodeType, label: '结束', icon: '⏹' },
  { type: 'task' as NodeType, label: '任务', icon: '⚙' },
  { type: 'condition' as NodeType, label: '条件', icon: '◇' },
  { type: 'loop' as NodeType, label: '循环', icon: '↻' },
]

function typeMeta(type: NodeType) {
  const found = nodeTypes.find(nt => nt.type === type)
  return found || { type, label: type, icon: '●' }
}

let nodeCounter = 0

// ===== 连线计算 =====
const nodeLayers = computed(() => currentWorkflow.value?.nodes || [])

const connections = computed(() => {
  if (!currentWorkflow.value) return []
  const lines: { x1: number; y1: number; x2: number; y2: number }[] = []
  const nodes = currentWorkflow.value.nodes

  nodes.forEach(node => {
    node.next_nodes.forEach(targetId => {
      const srcIdx = nodes.findIndex(n => n.id === node.id)
      const tgtIdx = nodes.findIndex(n => n.id === targetId)
      if (srcIdx >= 0 && tgtIdx >= 0) {
        lines.push({
          x1: 260, // card right edge
          y1: srcIdx * 130 + 60 + 20,
          x2: 260,
          y2: tgtIdx * 130 + 20 + 20,
        })
      }
    })
  })
  return lines
})

function goBack() { router.push('/') }

onMounted(() => {
  loadWorkflowList()
})

// ===== 工作流 CRUD =====
function loadWorkflowList() {
  // 从 localStorage 加载已创建工作流列表
  try {
    const stored = localStorage.getItem('sushi_workflows')
    if (stored) workflowList.value = JSON.parse(stored)
  } catch { /* ignore */ }
}

function saveWorkflowList() {
  localStorage.setItem('sushi_workflows', JSON.stringify(workflowList.value))
}

function createWorkflow() {
  const id = 'wf_' + Date.now()
  const wf: WorkflowDefinition = {
    id,
    name: '新工作流',
    description: '',
    version: '1.0.0',
    start_node_id: '',
    nodes: [],
  }
  const startNode: WorkflowNode = {
    id: 'node_' + (++nodeCounter),
    type: 'start' as NodeType,
    name: '开始',
    next_nodes: [],
  }
  wf.nodes.push(startNode)
  wf.start_node_id = startNode.id

  workflowList.value.unshift({ id, name: '新工作流' })
  saveWorkflowList()
  currentWorkflow.value = wf
  selectedNode.value = null
}

function selectWorkflow(wf: { id: string; name?: string }) {
  const stored = localStorage.getItem('sushi_wf_' + wf.id)
  if (stored) {
    try {
      currentWorkflow.value = JSON.parse(stored)
      nodeCounter = currentWorkflow.value!.nodes.length
      return
    } catch { /* ignore */ }
  }
  // 没有本地保存的，新建一个最小的
  createWorkflow()
  if (currentWorkflow.value) {
    currentWorkflow.value.id = wf.id
    currentWorkflow.value.name = wf.name || '未命名'
  }
}

function saveLocalWorkflow() {
  if (!currentWorkflow.value) return
  const wf = currentWorkflow.value
  localStorage.setItem('sushi_wf_' + wf.id, JSON.stringify(wf))
  const idx = workflowList.value.findIndex(x => x.id === wf.id)
  if (idx >= 0) workflowList.value[idx].name = wf.name
  saveWorkflowList()
}

// ===== 节点操作 =====
function addNode(type: NodeType) {
  if (!currentWorkflow.value) return
  const node: WorkflowNode = {
    id: 'node_' + (++nodeCounter),
    type,
    name: typeMeta(type).label + '_' + nodeCounter,
    next_nodes: [],
  }
  if (type === 'task') {
    node.task_type = 'log'
    node.task_config = { message: 'Hello' }
  }
  if (type === 'condition') {
    node.condition = 'true'
    node.true_branch = ''
    node.false_branch = ''
  }
  if (type === 'loop') {
    node.loop_condition = 'count < 5'
    node.loop_body = []
    node.exit_node = ''
  }
  currentWorkflow.value.nodes.push(node)
  saveLocalWorkflow()
}

function selectNode(node: WorkflowNode) {
  selectedNode.value = node
  Object.assign(editingNode, JSON.parse(JSON.stringify(node)))
}

function deleteNode(nodeId: string) {
  if (!currentWorkflow.value) return
  const wf = currentWorkflow.value
  if (wf.start_node_id === nodeId) return // 不删开始节点
  wf.nodes = wf.nodes.filter(n => n.id !== nodeId)
  wf.nodes.forEach(n => {
    n.next_nodes = n.next_nodes.filter(id => id !== nodeId)
  })
  if (selectedNode.value?.id === nodeId) selectedNode.value = null
  saveLocalWorkflow()
}

function applyNodeEdit() {
  if (!currentWorkflow.value || !selectedNode.value) return
  const wf = currentWorkflow.value
  const idx = wf.nodes.findIndex(n => n.id === selectedNode.value!.id)
  if (idx >= 0) {
    wf.nodes[idx] = JSON.parse(JSON.stringify(editingNode))
    selectedNode.value = wf.nodes[idx]
    saveLocalWorkflow()
  }
}

function onDragStart(e: DragEvent, type: NodeType) {
  e.dataTransfer!.effectAllowed = 'copy'
  e.dataTransfer!.setData('nodeType', type)
}

// ===== 保存/执行 =====
async function handleSave() {
  if (!currentWorkflow.value) return
  const wf = currentWorkflow.value

  // 自动补结束节点（后端验证要求至少一个）
  const hasEnd = wf.nodes.some(n => n.type === 'end')
  if (!hasEnd) {
    const endNode: WorkflowNode = {
      id: 'node_' + (++nodeCounter),
      type: 'end' as NodeType,
      name: '结束',
      next_nodes: [],
    }
    wf.nodes.push(endNode)
    // 把最后一个非 end 节点的 next_nodes 指向它
    const lastNode = wf.nodes.filter(n => n.type !== 'end').slice(-1)[0]
    if (lastNode) {
      lastNode.next_nodes = [...lastNode.next_nodes, endNode.id]
    }
    saveLocalWorkflow()
  }

  const def = {
    id: wf.id,
    name: wf.name,
    description: wf.description || '',
    version: wf.version,
    start_node_id: wf.start_node_id,
    nodes: wf.nodes,
  }
  try {
    const res = await workflowApi.define(def, '保存')
    notifStore.toastSuccess('保存成功', `版本: ${res.version}`)
    wf.version = res.version
    saveLocalWorkflow()
  } catch (e: unknown) {
    notifStore.toastError('保存失败', (e as Error)?.message || '')
  }
}

async function handleExecute() {
  if (!currentWorkflow.value) return
  showExecDialog.value = true
  execResult.value = null
  try {
    const res = await workflowApi.execute(currentWorkflow.value.id, { count: 0 })
    const statusRes = await workflowApi.status(res.execution_id)
    execResult.value = statusRes
  } catch (e: unknown) {
    execResult.value = {
      workflow_id: currentWorkflow.value.id,
      execution_id: '',
      status: 'failed',
      error: (e as Error)?.message || '执行失败',
      started_at: new Date().toISOString(),
    } as ExecutionResult
  }
}

async function loadVersions() {
  if (!currentWorkflow.value) return
  try {
    const res = await workflowApi.versions(currentWorkflow.value.id)
    versionList.value = res.versions
  } catch { versionList.value = [] }
}

watch(showVersionDialog, (v) => { if (v) loadVersions() })

function formatTime(t: string) {
  return t ? new Date(t).toLocaleString('zh-CN') : '-'
}

function statusTag(s: string) {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    completed: 'success', running: 'warning', failed: 'danger', stopped: 'info', pending: 'info',
  }
  return map[s] || 'info'
}
</script>

<style scoped>
.wf-page { height: 100vh; display: flex; flex-direction: column; background: var(--color-paper-warm); }
.wf-header { display: flex; align-items: center; padding: 12px 20px; border-bottom: 1px solid rgba(139,115,85,0.15); gap: 12px; }
.back-btn { padding: 6px 12px; border: 1px solid rgba(139,115,85,0.2); background: transparent; border-radius: var(--radius-md); color: var(--color-ink-light); cursor: pointer; font-size: 13px; }
.wf-title { flex: 1; font-size: 18px; color: var(--color-ink-black); margin: 0; }
.wf-actions { display: flex; align-items: center; gap: 8px; }
.version-badge { font-family: monospace; font-size: 12px; color: var(--color-ink-faint); border: 1px solid rgba(139,115,85,0.2); padding: 2px 8px; border-radius: 10px; }
.btn { padding: 7px 16px; border: 1px solid rgba(139,115,85,0.2); background: transparent; border-radius: var(--radius-md); cursor: pointer; font-size: 13px; color: var(--color-ink-light); transition: all 0.15s; }
.btn:hover { background: rgba(139,115,85,0.08); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-save { background: var(--color-accent); color: white; border-color: var(--color-accent); }
.btn-save:hover { background: var(--color-accent-dark, #6b5030); }
.btn-run { background: #409eff; color: white; border-color: #409eff; }
.btn-run:hover { background: #337ecc; }
.wf-body { flex: 1; display: flex; overflow: hidden; }
.wf-left { width: 220px; border-right: 1px solid rgba(139,115,85,0.1); overflow-y: auto; padding: 12px; flex-shrink: 0; }
.wf-canvas { flex: 1; position: relative; overflow-y: auto; padding: 20px; min-width: 400px; }
.wf-canvas-empty { display: flex; align-items: center; justify-content: center; }
.wf-right { width: 260px; border-left: 1px solid rgba(139,115,85,0.1); overflow-y: auto; padding: 12px; flex-shrink: 0; }
.panel { background: white; border-radius: var(--radius-md); padding: 12px; margin-bottom: 12px; border: 1px solid rgba(139,115,85,0.08); }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-header h4 { font-size: 14px; color: var(--color-ink-black); margin: 0; }
.wf-list { list-style: none; padding: 0; margin: 0; }
.wf-item { padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; color: var(--color-ink-light); transition: all 0.15s; }
.wf-item:hover, .wf-item.active { background: rgba(139,115,85,0.08); color: var(--color-ink-black); }
.empty-hint { text-align: center; font-size: 12px; color: var(--color-ink-faint); padding: 20px; }
.palette { display: flex; flex-direction: column; gap: 6px; }
.palette-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; border: 1px solid rgba(139,115,85,0.1); transition: all 0.15s; }
.palette-item:hover { background: rgba(139,115,85,0.08); border-color: var(--color-accent); }
.palette-icon { font-size: 16px; width: 24px; text-align: center; }
.icon-btn { width: 24px; height: 24px; border-radius: 50%; border: 1px solid rgba(139,115,85,0.15); background: transparent; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center; color: var(--color-ink-light); }
.icon-btn:hover { background: rgba(139,115,85,0.1); }
.connectors { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
.nodes-container { position: relative; min-height: 300px; }
.wf-node-card { position: absolute; left: 20px; width: 240px; background: white; border: 2px solid rgba(139,115,85,0.12); border-radius: var(--radius-md); padding: 12px; cursor: pointer; transition: all 0.15s; z-index: 2; }
.wf-node-card:hover { border-color: rgba(139,115,85,0.3); box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.wf-node-card.selected { border-color: var(--color-accent); box-shadow: 0 0 0 3px rgba(139,115,85,0.15); }
.node-header { display: flex; align-items: center; gap: 8px; }
.node-icon { font-size: 16px; }
.node-name { font-size: 14px; font-weight: 500; color: var(--color-ink-black); flex: 1; }
.node-type-tag { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: rgba(139,115,85,0.08); color: var(--color-ink-faint); }
.node-body { margin-top: 6px; }
.node-detail { font-size: 12px; color: var(--color-ink-faint); font-family: monospace; }
.node-delete { position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; border: none; background: rgba(181,71,71,0.8); color: white; font-size: 10px; cursor: pointer; display: none; align-items: center; justify-content: center; }
.wf-node-card:hover .node-delete { display: flex; }
.canvas-empty { color: var(--color-ink-faint); font-size: 14px; }
.prop-form { display: flex; flex-direction: column; gap: 10px; }
.prop-row { display: flex; flex-direction: column; gap: 4px; }
.prop-row label { font-size: 12px; color: var(--color-ink-faint); }
.prop-input { padding: 6px 8px; border: 1px solid rgba(139,115,85,0.2); border-radius: var(--radius-sm); font-size: 13px; background: var(--color-paper-warm); color: var(--color-ink-black); }
.prop-input:focus { outline: none; border-color: var(--color-accent); }
.prop-save { margin-top: 8px; }
.exec-status { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.exec-id { font-family: monospace; font-size: 12px; color: var(--color-ink-faint); }
.exec-output pre { background: rgba(139,115,85,0.05); padding: 12px; border-radius: var(--radius-sm); font-size: 12px; overflow-x: auto; max-height: 300px; }
.exec-error { color: var(--color-error); font-size: 13px; padding: 8px; background: rgba(181,71,71,0.08); border-radius: var(--radius-sm); }
.exec-loading { text-align: center; padding: 24px; color: var(--color-ink-faint); }
</style>
