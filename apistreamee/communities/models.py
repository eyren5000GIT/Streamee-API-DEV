from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class CommunityPlatform(models.TextChoices):
    TWITCH = "twitch", "Twitch"


class CommunityStatus(models.TextChoices):
    UNCLAIMED = "unclaimed", "Unclaimed"
    CLAIMED = "claimed", "Claimed"


class Community(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)

    platform = models.CharField(max_length=32, choices=CommunityPlatform.choices, default=CommunityPlatform.TWITCH)

    # Eindeutige Streamer-Identität (Twitch User ID)
    external_id = models.CharField(max_length=64)  # REQUIRED
    external_login = models.CharField(max_length=120, blank=True, default="")
    external_display_name = models.CharField(max_length=120, blank=True, default="")
    external_profile_image_url = models.URLField(blank=True, default="")

    status = models.CharField(max_length=32, choices=CommunityStatus.choices, default=CommunityStatus.UNCLAIMED)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="communities_created")
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="communities_owned")

    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "external_id"], name="uniq_community_platform_external_id"),
        ]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["platform", "external_id"]),
            models.Index(fields=["status"]),
        ]

class MembershipRole(models.TextChoices):
    MEMBER = "member", "Member"
    ADMIN = "admin", "Admin"


class CommunityMembership(models.Model):
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="community_memberships")

    role = models.CharField(max_length=32, choices=MembershipRole.choices, default=MembershipRole.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["community", "user"], name="uniq_membership_community_user")
        ]
        indexes = [
            models.Index(fields=["community", "user"]),
            models.Index(fields=["user"]),
        ]
