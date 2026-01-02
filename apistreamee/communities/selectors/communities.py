from django.db.models import Count, Exists, OuterRef, Value, CharField, Subquery
from ..models import Community, CommunityMembership


def communities_with_counts():
    return Community.objects.annotate(member_count=Count("memberships"))


def community_detail_with_user_flags(slug: str, user=None):
    qs = Community.objects.filter(slug=slug).annotate(member_count=Count("memberships"))

    if user and user.is_authenticated:
        membership_qs = CommunityMembership.objects.filter(community=OuterRef("pk"), user=user)
        qs = qs.annotate(
            is_member=Exists(membership_qs),
            my_role=Subquery(membership_qs.values("role")[:1]),
        )
    else:
        qs = qs.annotate(
            is_member=Value(False),
            my_role=Value("", output_field=CharField()),
        )

    return qs
