from rest_framework.permissions import BasePermission


class IsCommunityAdmin(BasePermission):
    """
    Erlaubt Änderungen an einer Community nur für Mitglieder mit Rolle 'admin'.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        return obj.memberships.filter(user=user, role="admin").exists()
