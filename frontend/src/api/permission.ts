import { get, post } from '@/utils/request'

export interface PermissionInfo {
  user_id: string
  resource_type: string
  resource_id: string
  action: string
  granted_by?: string
  created_at?: string
}

export interface RoleInfo {
  id: string
  name: string
  description: string
  permissions?: string[]
  created_at?: string
}

export interface ResourceTypeInfo {
  value: string
  name: string
}

export interface ActionInfo {
  value: string
  name: string
}

export const permissionApi = {
  // ===== 权限管理 =====
  /** 授予权限 */
  grant: (data: {
    user_id: string
    resource_type: string
    resource_id: string
    action: string
  }) => post<{ status: string; message: string }>('/api/permissions/grant', data),

  /** 撤销权限 */
  revoke: (data: {
    user_id: string
    resource_type: string
    resource_id: string
    action: string
  }) => post<{ status: string; message: string }>('/api/permissions/revoke', data),

  /** 检查权限 */
  check: (data: {
    user_id: string
    resource_type: string
    resource_id: string
    action: string
  }) => post<{ has_permission: boolean; user_id: string; resource_type: string; resource_id: string; action: string }>(
    '/api/permissions/check',
    data,
  ),

  /** 获取用户所有权限 */
  userPermissions: (userId: string) =>
    get<{ user_id: string; permissions: PermissionInfo[] }>(`/api/permissions/user/${userId}`),

  /** 获取资源 ACL */
  resourceAcl: (resourceType: string, resourceId: string) =>
    get<{ resource_type: string; resource_id: string; acl: PermissionInfo[] }>(
      `/api/permissions/resource/${resourceType}/${resourceId}/acl`,
    ),

  // ===== 角色管理 =====
  /** 获取所有角色 */
  roles: () => get<{ roles: RoleInfo[] }>('/api/permissions/roles'),

  /** 创建角色 */
  createRole: (data: { name: string; description: string; permissions: string[] }) =>
    post<{ status: string; role_id: string; message: string }>('/api/permissions/roles/create', data),

  /** 获取角色详情 */
  roleDetail: (roleId: string) =>
    get<{ role_id: string; permissions: string[] }>(`/api/permissions/roles/${roleId}`),

  /** 删除角色 */
  deleteRole: (roleId: string) =>
    fetch(`/api/permissions/roles/${roleId}`, { method: 'DELETE' }).then(res => res.json()) as Promise<{
      status: string
      message: string
    }>,

  /** 分配角色给用户 */
  assignRole: (data: { user_id: string; role_id: string }) =>
    post<{ status: string; message: string }>('/api/permissions/roles/assign', data),

  /** 移除用户角色 */
  removeRole: (data: { user_id: string; role_id: string }) =>
    post<{ status: string; message: string }>('/api/permissions/roles/remove', data),

  // ===== 元数据 =====
  /** 获取资源类型 */
  resourceTypes: () =>
    get<{ resource_types: ResourceTypeInfo[] }>('/api/permissions/resource-types'),

  /** 获取操作类型 */
  actions: () =>
    get<{ actions: ActionInfo[] }>('/api/permissions/actions'),
}
