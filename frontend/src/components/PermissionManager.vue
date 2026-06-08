<template>
  <div class="perm-page">
    <header class="page-header">
      <button class="back-btn" @click="goBack">
        <span>←</span> 返回
      </button>
      <h1 class="page-title">权限管理</h1>
    </header>

    <el-tabs v-model="activeTab" class="perm-tabs">
      <!-- 角色管理 -->
      <el-tab-pane label="角色管理" name="roles">
        <div class="panel">
          <div class="panel-header">
            <h3>角色列表</h3>
            <el-button type="primary" size="small" @click="showRoleDialog = true">
              创建角色
            </el-button>
          </div>
          <el-table :data="roles" v-loading="rolesLoading" stripe>
            <el-table-column prop="name" label="角色名" width="150" />
            <el-table-column prop="description" label="描述" min-width="200" />
            <el-table-column prop="id" label="角色ID" width="180">
              <template #default="{ row }">
                <span class="mono-text">{{ row.id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewRoleDetail(row)">
                  查看权限
                </el-button>
                <el-button type="danger" link size="small" @click="handleDeleteRole(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="!rolesLoading && roles.length === 0" class="empty-state">
            <p>暂无角色，点击上方按钮创建</p>
          </div>
        </div>
      </el-tab-pane>

      <!-- 用户角色分配 -->
      <el-tab-pane label="用户角色分配" name="assign">
        <div class="panel">
          <div class="assign-section">
            <h3>分配角色</h3>
            <el-form :inline="true" class="assign-form">
              <el-form-item label="用户ID">
                <el-input v-model="assignForm.user_id" placeholder="输入用户ID" />
              </el-form-item>
              <el-form-item label="角色">
                <el-select v-model="assignForm.role_id" placeholder="选择角色">
                  <el-option
                    v-for="role in roles"
                    :key="role.id"
                    :label="role.name"
                    :value="role.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleAssignRole">分配</el-button>
                <el-button type="danger" @click="handleRemoveRole">移除</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>

        <div class="panel" style="margin-top: 16px;">
          <div class="panel-header">
            <h3>查询用户权限</h3>
          </div>
          <el-form :inline="true">
            <el-form-item label="用户ID">
              <el-input v-model="lookupUserId" placeholder="输入用户ID" />
            </el-form-item>
            <el-form-item>
              <el-button @click="handleLookupUser">查询</el-button>
            </el-form-item>
          </el-form>

          <div v-if="userPermissions.length > 0" class="user-perm-list">
            <el-table :data="userPermissions" stripe>
              <el-table-column prop="resource_type" label="资源类型" width="120" />
              <el-table-column prop="resource_id" label="资源ID" width="180" />
              <el-table-column prop="action" label="操作" width="120" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button
                    type="danger"
                    link
                    size="small"
                    @click="handleRevokePermission(row)"
                  >
                    撤销
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-if="lookupUserId && !userPermLoading && userPermissions.length === 0" class="empty-state">
            <p>该用户暂无单独授予的权限</p>
          </div>
        </div>
      </el-tab-pane>

      <!-- 资源 ACL -->
      <el-tab-pane label="资源 ACL" name="acl">
        <div class="panel">
          <el-form :inline="true">
            <el-form-item label="资源类型">
              <el-select v-model="aclForm.resource_type" placeholder="选择资源类型">
                <el-option
                  v-for="rt in resourceTypes"
                  :key="rt.value"
                  :label="rt.name"
                  :value="rt.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="资源ID">
              <el-input v-model="aclForm.resource_id" placeholder="输入资源ID" />
            </el-form-item>
            <el-form-item>
              <el-button @click="handleLookupAcl">查询</el-button>
            </el-form-item>
          </el-form>

          <div v-if="aclList.length > 0" class="user-perm-list">
            <el-table :data="aclList" stripe>
              <el-table-column prop="user_id" label="用户" width="120" />
              <el-table-column prop="action" label="操作" width="120" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button
                    type="danger"
                    link
                    size="small"
                    @click="handleRevokeAcl(row)"
                  >
                    撤销
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-if="aclForm.resource_id && !aclLoading && aclList.length === 0" class="empty-state">
            <p>该资源暂无 ACL 配置</p>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 创建角色弹窗 -->
    <el-dialog v-model="showRoleDialog" title="创建角色" width="480px">
      <el-form :model="roleForm" label-width="80px">
        <el-form-item label="角色名">
          <el-input v-model="roleForm.name" placeholder="如: editor" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="roleForm.description" placeholder="角色描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRoleDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateRole" :loading="creatingRole">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 角色权限详情弹窗 -->
    <el-dialog v-model="showRoleDetailDialog" :title="`角色权限 - ${selectedRole?.name || ''}`" width="480px">
      <div v-if="selectedRole">
        <p class="role-desc">{{ selectedRole.description }}</p>
        <div v-if="rolePermissions.length > 0">
          <el-tag
            v-for="perm in rolePermissions"
            :key="perm"
            class="perm-tag"
            size="small"
          >
            {{ perm }}
          </el-tag>
        </div>
        <p v-else class="text-muted">该角色暂无权限配置</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { permissionApi, type RoleInfo, type PermissionInfo, type ResourceTypeInfo } from '@/api/permission'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const notifStore = useNotificationStore()
const activeTab = ref('roles')

// ===== 角色管理 =====
const roles = ref<RoleInfo[]>([])
const rolesLoading = ref(false)
const showRoleDialog = ref(false)
const creatingRole = ref(false)
const roleForm = ref({ name: '', description: '' })

// ===== 用户权限查询 =====
const lookupUserId = ref('')
const userPermissions = ref<PermissionInfo[]>([])
const userPermLoading = ref(false)

// ===== 角色分配 =====
const assignForm = ref({ user_id: '', role_id: '' })

// ===== 角色详情 =====
const showRoleDetailDialog = ref(false)
const selectedRole = ref<RoleInfo | null>(null)
const rolePermissions = ref<string[]>([])

// ===== 资源 ACL =====
const resourceTypes = ref<ResourceTypeInfo[]>([])
const aclForm = ref({ resource_type: 'document', resource_id: '' })
const aclList = ref<PermissionInfo[]>([])
const aclLoading = ref(false)

function goBack() {
  router.push('/')
}

onMounted(() => {
  loadRoles()
  loadResourceTypes()
})

async function loadRoles() {
  rolesLoading.value = true
  try {
    const res = await permissionApi.roles()
    roles.value = res.roles
  } catch {
    notifStore.toastError('加载失败', '无法获取角色列表')
  } finally {
    rolesLoading.value = false
  }
}

async function loadResourceTypes() {
  try {
    const res = await permissionApi.resourceTypes()
    resourceTypes.value = res.resource_types
  } catch { /* ignore */ }
}

async function handleCreateRole() {
  if (!roleForm.value.name.trim()) {
    notifStore.toastWarning('请输入角色名')
    return
  }

  creatingRole.value = true
  try {
    await permissionApi.createRole({
      name: roleForm.value.name.trim(),
      description: roleForm.value.description.trim(),
      permissions: [],
    })
    notifStore.toastSuccess('角色创建成功')
    showRoleDialog.value = false
    roleForm.value = { name: '', description: '' }
    loadRoles()
  } catch {
    notifStore.toastError('创建失败')
  } finally {
    creatingRole.value = false
  }
}

async function handleDeleteRole(role: RoleInfo) {
  try {
    await ElMessageBox.confirm(`确定删除角色「${role.name}」吗？`, '确认删除', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await permissionApi.deleteRole(role.id)
    notifStore.toastSuccess('角色已删除')
    loadRoles()
  } catch { /* cancel */ }
}

async function viewRoleDetail(role: RoleInfo) {
  selectedRole.value = role
  showRoleDetailDialog.value = true
  try {
    const res = await permissionApi.roleDetail(role.id)
    rolePermissions.value = res.permissions
  } catch {
    rolePermissions.value = []
  }
}

async function handleAssignRole() {
  if (!assignForm.value.user_id || !assignForm.value.role_id) {
    notifStore.toastWarning('请填写用户ID和选择角色')
    return
  }
  try {
    await permissionApi.assignRole({
      user_id: assignForm.value.user_id,
      role_id: assignForm.value.role_id,
    })
    notifStore.toastSuccess('角色分配成功')
    assignForm.value = { user_id: '', role_id: '' }
  } catch {
    notifStore.toastError('分配失败')
  }
}

async function handleRemoveRole() {
  if (!assignForm.value.user_id || !assignForm.value.role_id) {
    notifStore.toastWarning('请填写用户ID和选择角色')
    return
  }
  try {
    await permissionApi.removeRole({
      user_id: assignForm.value.user_id,
      role_id: assignForm.value.role_id,
    })
    notifStore.toastSuccess('角色移除成功')
    assignForm.value = { user_id: '', role_id: '' }
  } catch {
    notifStore.toastError('移除失败')
  }
}

async function handleLookupUser() {
  if (!lookupUserId.value.trim()) return
  userPermLoading.value = true
  try {
    const res = await permissionApi.userPermissions(lookupUserId.value.trim())
    userPermissions.value = res.permissions
  } catch {
    notifStore.toastError('查询失败')
  } finally {
    userPermLoading.value = false
  }
}

async function handleRevokePermission(perm: PermissionInfo) {
  try {
    await permissionApi.revoke({
      user_id: perm.user_id || lookupUserId.value,
      resource_type: perm.resource_type,
      resource_id: perm.resource_id,
      action: perm.action,
    })
    notifStore.toastSuccess('权限已撤销')
    handleLookupUser()
  } catch {
    notifStore.toastError('撤销失败')
  }
}

async function handleLookupAcl() {
  if (!aclForm.value.resource_type || !aclForm.value.resource_id.trim()) return
  aclLoading.value = true
  try {
    const res = await permissionApi.resourceAcl(aclForm.value.resource_type, aclForm.value.resource_id.trim())
    aclList.value = res.acl || []
  } catch {
    notifStore.toastError('查询失败')
  } finally {
    aclLoading.value = false
  }
}

async function handleRevokeAcl(perm: PermissionInfo) {
  try {
    await permissionApi.revoke({
      user_id: perm.user_id,
      resource_type: aclForm.value.resource_type,
      resource_id: aclForm.value.resource_id,
      action: perm.action,
    })
    notifStore.toastSuccess('权限已撤销')
    handleLookupAcl()
  } catch {
    notifStore.toastError('撤销失败')
  }
}
</script>

<style scoped>
.perm-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-paper-warm);
}

.page-header {
  display: flex;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(139, 115, 85, 0.15);
  gap: 16px;
}

.back-btn {
  padding: 8px 14px;
  border: 1px solid rgba(139, 115, 85, 0.2);
  background: transparent;
  border-radius: var(--radius-md);
  color: var(--color-ink-light);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
}

.back-btn:hover {
  background: rgba(139, 115, 85, 0.08);
  color: var(--color-ink-black);
}

.page-title {
  flex: 1;
  font-size: 20px;
  color: var(--color-ink-black);
  margin: 0;
}

.perm-tabs {
  flex: 1;
  padding: 0 24px;
}

.perm-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
}

.panel {
  background: white;
  border-radius: var(--radius-md);
  padding: 20px;
  border: 1px solid rgba(139, 115, 85, 0.1);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-header h3 {
  font-size: 16px;
  color: var(--color-ink-black);
  margin: 0;
}

.assign-section h3 {
  font-size: 16px;
  color: var(--color-ink-black);
  margin: 0 0 12px 0;
}

.assign-form {
  margin-bottom: 0;
}

.user-perm-list {
  margin-top: 12px;
}

.mono-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--color-ink-light);
}

.role-desc {
  color: var(--color-ink-light);
  font-size: 14px;
  margin-bottom: 16px;
}

.perm-tag {
  margin-right: 8px;
  margin-bottom: 8px;
}

.text-muted {
  color: var(--color-ink-faint);
  font-size: 13px;
}

.empty-state {
  text-align: center;
  padding: 40px;
}

.empty-state p {
  color: var(--color-ink-faint);
  font-size: 14px;
}
</style>
