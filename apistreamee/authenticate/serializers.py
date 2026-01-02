from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def validate_email(self, value: str) -> str:
        value = (value or "").strip().lower()
        if not value:
            raise serializers.ValidationError("Email ist erforderlich.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email wird bereits verwendet.")
        return value

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["email"] = validated_data["email"].strip().lower()

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    SimpleJWT-Login via email + password.
    Gibt access/refresh wie gewohnt zurück.
    """

    # Wir ersetzen das Standardfeld "username" durch "email"
    username_field = "email"

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        password = attrs.get("password")

        if not email or not password:
            raise serializers.ValidationError("Email und Passwort sind erforderlich.")

        # User anhand Email laden und dann authentifizieren
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Ungültige Zugangsdaten.")

        # username wird von Django intern für authenticate verwendet
        user = authenticate(username=user.username, password=password)
        if user is None:
            raise serializers.ValidationError("Ungültige Zugangsdaten.")

        if not user.is_active:
            raise serializers.ValidationError("User ist deaktiviert.")

        # Token generieren (Standard SimpleJWT)
        data = super().get_token(user)
        return {
            "refresh": str(data),
            "access": str(data.access_token),
        }