from rest_framework import serializers
from .models import Community, CommunityMembership
from integrations.providers.twitch import resolve_user_by_login, TwitchNotFoundError, TwitchConfigError
from django.db import IntegrityError
import re


class CommunityListSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Community
        fields = ["id", "name", "slug", "description", "member_count", "created_at"]


class CommunityDetailSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)
    is_member = serializers.BooleanField(read_only=True)
    my_role = serializers.CharField(read_only=True)

    class Meta:
        model = Community
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "created_by",
            "member_count",
            "is_member",
            "my_role",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]


def extract_twitch_login(value: str) -> str:
    v = value.strip()
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", v, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return v.lower()


class CommunityCreateSerializer(serializers.Serializer):
    twitch = serializers.CharField(help_text="Twitch username or channel URL")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)

    def validate_twitch(self, value):
        login = extract_twitch_login(value)
        if not login or len(login) < 3:
            raise serializers.ValidationError("Invalid Twitch channel/login.")
        return login

    def create(self, validated_data):
        request = self.context["request"]
        login = validated_data["twitch"]

        try:
            twitch_user = resolve_user_by_login(login)
        except TwitchConfigError:
            raise serializers.ValidationError({"twitch": "Twitch is not configured on server (missing client id/secret)."})
        except TwitchNotFoundError:
            raise serializers.ValidationError({"twitch": "Twitch user not found."})

        # Name default: Twitch display_name
        name = (validated_data.get("name") or twitch_user.display_name).strip()
        description = (validated_data.get("description") or "").strip()

        try:
            community = Community.objects.create(
                name=name,
                platform="twitch",
                external_id=twitch_user.id,
                external_login=twitch_user.login,
                external_display_name=twitch_user.display_name,
                external_profile_image_url=twitch_user.profile_image_url,
                status="unclaimed",
                created_by=request.user,
                description=description,
            )
        except IntegrityError:
            # unique(platform, external_id) -> community exists already
            raise serializers.ValidationError({"twitch": "Community for this streamer already exists."})

        CommunityMembership.objects.create(community=community, user=request.user, role="admin")
        return community


class CommunityPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Community
        fields = ["name", "description"]


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityMembership
        fields = ["community", "role", "joined_at"]
