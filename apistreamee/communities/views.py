from django.db.models import Count
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Community, CommunityMembership
from .permissions import IsCommunityAdmin
from .serializers import (
    CommunityListSerializer,
    CommunityDetailSerializer,
    CommunityCreateSerializer,
    CommunityPatchSerializer,
)
from .selectors.communities import communities_with_counts, community_detail_with_user_flags


@api_view(["GET", "POST"])
def community_list_create(request):
    if request.method == "GET":
        qs = communities_with_counts().order_by("-created_at")
        return Response(CommunityListSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    # POST
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = CommunityCreateSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    community = serializer.save()

    # Detail response inkl. Count + Flags
    obj = community_detail_with_user_flags(community.slug, request.user).get(pk=community.pk)
    return Response(CommunityDetailSerializer(obj).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def community_detail_by_slug(request, slug: str):
    qs = community_detail_with_user_flags(slug, request.user)
    community = get_object_or_404(qs, slug=slug)
    return Response(CommunityDetailSerializer(community).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def community_patch_by_id(request, pk: int):
    community = get_object_or_404(Community, pk=pk)

    # Permission: nur admin darf patchen
    perm = IsCommunityAdmin()
    if not perm.has_object_permission(request, None, community):
        return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

    serializer = CommunityPatchSerializer(community, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    obj = community_detail_with_user_flags(community.slug, request.user).get(pk=community.pk)
    return Response(CommunityDetailSerializer(obj).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def community_join(request, pk: int):
    community = get_object_or_404(Community, pk=pk)

    membership, created = CommunityMembership.objects.get_or_create(
        community=community,
        user=request.user,
        defaults={"role": "member"},
    )
    if not created:
        return Response({"detail": "Already a member."}, status=status.HTTP_200_OK)

    return Response({"detail": "Joined."}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def community_leave(request, pk: int):
    community = get_object_or_404(Community, pk=pk)

    # Optional: wenn admin, darf leave nur wenn noch ein anderer admin existiert (MVP-Guard)
    my_membership = CommunityMembership.objects.filter(community=community, user=request.user).first()
    if not my_membership:
        return Response({"detail": "Not a member."}, status=status.HTTP_200_OK)

    if my_membership.role == "admin":
        other_admin_exists = CommunityMembership.objects.filter(
            community=community, role="admin"
        ).exclude(user=request.user).exists()
        if not other_admin_exists:
            return Response(
                {"detail": "Cannot leave as the last admin. Promote another admin first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    my_membership.delete()
    return Response({"detail": "Left."}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_communities(request):
    qs = (
        Community.objects.filter(memberships__user=request.user)
        .annotate(member_count=Count("memberships"))
        .order_by("-created_at")
    )
    return Response(CommunityListSerializer(qs, many=True).data, status=status.HTTP_200_OK)
