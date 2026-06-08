"""权限管理 API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth.permission_manager import PermissionAction, PermissionResource, get_permission_manager
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/permissions", tags=["权限管理"])


class PermissionGrantRequest(BaseModel):
    """授予权限请求"""

    user_id: str
    resource_type: str
    resource_id: str
    action: str


class RoleCreateRequest(BaseModel):
    """创建角色请求"""

    name: str
    description: str
    permissions: list


class RoleAssignRequest(BaseModel):
    """分配角色请求"""

    user_id: str
    role_id: str


class PermissionCheckRequest(BaseModel):
    """权限检查请求"""

    user_id: str
    resource_type: str
    resource_id: str
    action: str


class PermissionCheckResponse(BaseModel):
    """权限检查响应"""

    has_permission: bool
    user_id: str
    resource_type: str
    resource_id: str
    action: str


def get_current_user_id(request: Request) -> str:
    """获取当前用户ID（示例）"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id


@router.post("/grant")
async def grant_permission(
    request: PermissionGrantRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """授予权限"""
    try:
        perm_manager = get_permission_manager()

        success = await perm_manager.grant_permission(
            user_id=request.user_id,
            resource_type=PermissionResource(request.resource_type),
            resource_id=request.resource_id,
            action=PermissionAction(request.action),
            granted_by=current_user_id,
        )

        if success:
            return {"status": "success", "message": "权限授予成功"}
        else:
            raise HTTPException(status_code=500, detail="权限授予失败")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"授予权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"授予权限失败: {str(e)}")


@router.post("/revoke")
async def revoke_permission(
    request: PermissionGrantRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """撤销权限"""
    try:
        perm_manager = get_permission_manager()

        success = await perm_manager.revoke_permission(
            user_id=request.user_id,
            resource_type=PermissionResource(request.resource_type),
            resource_id=request.resource_id,
            action=PermissionAction(request.action),
        )

        if success:
            return {"status": "success", "message": "权限撤销成功"}
        else:
            raise HTTPException(status_code=500, detail="权限撤销失败")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"撤销权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"撤销权限失败: {str(e)}")


@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    request: PermissionCheckRequest,
):
    """检查权限"""
    try:
        perm_manager = get_permission_manager()

        has_permission = await perm_manager.check_permission(
            user_id=request.user_id,
            resource_type=PermissionResource(request.resource_type),
            resource_id=request.resource_id,
            action=PermissionAction(request.action),
        )

        return PermissionCheckResponse(
            has_permission=has_permission,
            user_id=request.user_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            action=request.action,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"检查权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查权限失败: {str(e)}")


@router.get("/user/{user_id}")
async def get_user_permissions(user_id: str):
    """获取用户所有权限"""
    try:
        perm_manager = get_permission_manager()
        permissions = await perm_manager.get_user_permissions(user_id)

        return {"user_id": user_id, "permissions": permissions}

    except Exception as e:
        logger.error(f"获取用户权限失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取用户权限失败: {str(e)}")


@router.get("/resource/{resource_type}/{resource_id}/acl")
async def get_resource_acl(resource_type: str, resource_id: str):
    """获取资源 ACL"""
    try:
        perm_manager = get_permission_manager()
        acl = await perm_manager.get_resource_acl(
            resource_type=PermissionResource(resource_type),
            resource_id=resource_id,
        )

        return {"resource_type": resource_type, "resource_id": resource_id, "acl": acl}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取资源 ACL 失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取资源 ACL 失败: {str(e)}")


@router.post("/roles/create")
async def create_role(
    request: RoleCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """创建角色"""
    try:
        perm_manager = get_permission_manager()

        role_id = await perm_manager.create_role(
            role_name=request.name,
            description=request.description,
            permissions=request.permissions,
        )

        if role_id:
            return {"status": "success", "role_id": role_id, "message": "角色创建成功"}
        else:
            raise HTTPException(status_code=500, detail="角色创建失败")

    except Exception as e:
        logger.error(f"创建角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建角色失败: {str(e)}")


@router.get("/roles")
async def get_all_roles():
    """获取所有角色"""
    try:
        perm_manager = get_permission_manager()
        roles = await perm_manager.get_all_roles()

        return {"roles": roles}

    except Exception as e:
        logger.error(f"获取角色列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取角色列表失败: {str(e)}")


@router.get("/roles/{role_id}")
async def get_role_detail(role_id: str):
    """获取角色详情"""
    try:
        perm_manager = get_permission_manager()
        permissions = await perm_manager.get_role_permissions(role_id)

        return {"role_id": role_id, "permissions": permissions}

    except Exception as e:
        logger.error(f"获取角色详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取角色详情失败: {str(e)}")


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    """删除角色"""
    try:
        perm_manager = get_permission_manager()

        success = await perm_manager.delete_role(role_id)

        if success:
            return {"status": "success", "message": "角色删除成功"}
        else:
            raise HTTPException(status_code=500, detail="角色删除失败")

    except Exception as e:
        logger.error(f"删除角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除角色失败: {str(e)}")


@router.post("/roles/assign")
async def assign_role(
    request: RoleAssignRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    """分配角色"""
    try:
        perm_manager = get_permission_manager()

        success = await perm_manager.assign_role_to_user(
            user_id=request.user_id,
            role_id=request.role_id,
            assigned_by=current_user_id,
        )

        if success:
            return {"status": "success", "message": "角色分配成功"}
        else:
            raise HTTPException(status_code=500, detail="角色分配失败")

    except Exception as e:
        logger.error(f"分配角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"分配角色失败: {str(e)}")


@router.post("/roles/remove")
async def remove_role(
    request: RoleAssignRequest,
):
    """移除用户角色"""
    try:
        perm_manager = get_permission_manager()

        success = await perm_manager.remove_role_from_user(
            user_id=request.user_id,
            role_id=request.role_id,
        )

        if success:
            return {"status": "success", "message": "角色移除成功"}
        else:
            raise HTTPException(status_code=500, detail="角色移除失败")

    except Exception as e:
        logger.error(f"移除角色失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移除角色失败: {str(e)}")


@router.get("/resource-types")
async def get_resource_types():
    """获取资源类型列表"""
    return {"resource_types": [{"value": rt.value, "name": rt.name} for rt in PermissionResource]}


@router.get("/actions")
async def get_actions():
    """获取操作类型列表"""
    return {"actions": [{"value": pa.value, "name": pa.name} for pa in PermissionAction]}
