from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID
    user_id: str
    role: str


def get_tenant_context(
    x_organization_id: str = Header(...),
    x_user_id: str = Header(...),
    x_user_role: str = Header(...),
) -> TenantContext:
    allowed_roles = {"admin", "operations_manager", "fleet_manager", "analyst", "viewer"}
    if x_user_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Unsupported organization role")
    try:
        organization_id = UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid organization ID") from exc

    return TenantContext(
        organization_id=organization_id,
        user_id=x_user_id,
        role=x_user_role,
    )
