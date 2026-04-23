"""Registry invariants — protects against the A2 regression (duplicate enums).

See docs/fix-plan/2026-04-23/A2-permission-merge.md for context.

Before A2: two independent Permission enums coexisted in
api.deps and core.permissions. These tests fail loudly if anyone
re-introduces the split.
"""
import pytest

from goldsmith_erp.core.permissions import Permission, ROLE_PERMISSIONS
from goldsmith_erp.db.models import UserRole


def test_every_permission_appears_in_at_least_one_role():
    """No orphaned enum values: every Permission must be granted to some role."""
    all_granted = set().union(*ROLE_PERMISSIONS.values())
    missing = [p for p in Permission if p not in all_granted]
    assert not missing, (
        f"Permissions defined but never granted to any role: {missing}"
    )


def test_role_permissions_contain_only_defined_permissions():
    """No role may reference permissions that don't exist in the enum."""
    valid = set(Permission)
    for role, perms in ROLE_PERMISSIONS.items():
        extra = [p for p in perms if p not in valid]
        assert not extra, (
            f"Role {role} references undefined permissions: {extra}"
        )


def test_single_permission_enum_defined_in_repo():
    """Fail loud if someone re-introduces a duplicate in api.deps (A2 regression)."""
    try:
        from goldsmith_erp.api.deps import Permission as DepsPermission  # noqa: F401
        pytest.fail(
            "Duplicate Permission enum detected in api.deps — "
            "should be removed (A2 regression)."
        )
    except ImportError:
        pass  # expected


def test_admin_has_all_permissions():
    """ADMIN must be granted every Permission the enum defines."""
    assert set(ROLE_PERMISSIONS[UserRole.ADMIN]) == set(Permission)


@pytest.mark.parametrize(
    "role", [UserRole.VIEWER, UserRole.GOLDSMITH, UserRole.ADMIN]
)
def test_every_role_has_at_least_one_permission(role):
    """No role may be permission-empty; that would be a deployment foot-gun."""
    assert len(ROLE_PERMISSIONS[role]) > 0
