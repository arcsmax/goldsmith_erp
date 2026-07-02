"""VIEWER must have zero consultation permissions (design IP)."""
from goldsmith_erp.core.permissions import ROLE_PERMISSIONS, Permission
from goldsmith_erp.db.models import UserRole


def test_goldsmith_has_consultation_permissions():
    perms = ROLE_PERMISSIONS[UserRole.GOLDSMITH]
    assert Permission.CONSULTATION_VIEW in perms
    assert Permission.CONSULTATION_CREATE in perms
    assert Permission.CONSULTATION_EDIT in perms


def test_viewer_has_no_consultation_permissions():
    perms = ROLE_PERMISSIONS[UserRole.VIEWER]
    assert not any(p.value.startswith("consultation:") for p in perms)
