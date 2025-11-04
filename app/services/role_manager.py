from __future__ import annotations

from typing import Dict, List


class RoleManager:
    """Utility to manage role-to-department mappings for RBAC enforcement."""

    def __init__(self) -> None:
        self._role_to_departments: Dict[str, List[str]] = {
            "finance": ["finance", "general"],
            "marketing": ["marketing", "general"],
            "hr": ["hr", "general"],
            "engineering": ["engineering", "general"],
            "employee": ["general"],
            "c_level": ["finance", "marketing", "hr", "engineering", "general"],
        }

    def normalize_role(self, role: str) -> str:
        """Normalize incoming role names for consistent lookups."""
        return role.strip().lower()

    def departments_for_role(self, role: str) -> List[str]:
        """Return the list of departments the role is authorized to access."""
        normalized = self.normalize_role(role)
        return self._role_to_departments.get(normalized, [])

    def register_role(self, role: str, departments: List[str]) -> None:
        """Extend RBAC mapping with a custom role at runtime if required."""
        normalized = self.normalize_role(role)
        self._role_to_departments[normalized] = departments
