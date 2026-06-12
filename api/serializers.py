"""
DRF serializers for API validation and request/response shaping.
"""
import logging

from django.contrib.auth import (
    get_user_model,
    password_validation,
    update_session_auth_hash,
)
from rest_framework import serializers
from dj_rest_auth.serializers import PasswordChangeSerializer
from bson import ObjectId
from api.db import db as mongo_db
from django.contrib.auth.hashers import make_password

from api.models import Prompt

User = get_user_model()
logger = logging.getLogger(__name__)


class SignupSerializer(serializers.Serializer):
    """Validate and normalize signup request data. Uses Django/DRF validation."""

    name = serializers.CharField(
        max_length=200,
        required=True,
        trim_whitespace=True,
        help_text="Display name.",
    )
    phone = serializers.CharField(
        max_length=15,
        required=True,
        allow_blank=False,
    )
    email = serializers.EmailField(
        required=True,
        max_length=254,
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )
    role = serializers.ChoiceField(
        choices=User.Role.choices,
        default=User.Role.ADMIN.value,
        required=False,
    )

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        existing_user = User.objects.filter(email__iexact=email).first()
        if existing_user:
            if not getattr(existing_user, "is_verified", False):
                raise serializers.ValidationError(
                    "Account exists but is not verified. Please complete OTP verification."
                )
            raise serializers.ValidationError("User already exists.")
        return email

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name

    def validate_phone(self, value):
        phone = (value or "").strip()
        if not phone:
            raise serializers.ValidationError("Phone is required.")
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("Phone number already exists.")
        return phone

    def validate_password(self, value):
        if not (value and len(value) >= 8):
            raise serializers.ValidationError("Password must be at least 8 characters.")
        return value

    def validate_role(self, value):
        if value not in (User.Role.ADMIN.value, User.Role.OTHER.value):
            raise serializers.ValidationError(
                f"Invalid role. Must be one of: {User.Role.ADMIN.value}, {User.Role.OTHER.value}"
            )
        return value

    def to_internal_value(self, data):
        """Normalize role from request (e.g. missing -> default)."""
        if not data.get("role"):
            data = {**data, "role": User.Role.ADMIN.value}
        return super().to_internal_value(data)


class LoginSerializer(serializers.Serializer):
    """Validate login request: email and password."""

    email = serializers.EmailField(required=True, max_length=254)
    password = serializers.CharField(required=True, write_only=True, style={"input_type": "password"})

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        return email


class OtpLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, max_length=254, allow_null=True)
    phone = serializers.CharField(required=False, max_length=15, allow_blank=True, allow_null=True)
    otp = serializers.CharField(required=True, min_length=4, max_length=10, trim_whitespace=True)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        phone = (attrs.get("phone") or "").strip()
        otp = (attrs.get("otp") or "").strip()

        if not email and not phone:
            raise serializers.ValidationError("Either email or phone is required.")
        if email and phone:
            raise serializers.ValidationError("Provide either email or phone, not both.")
        if not otp:
            raise serializers.ValidationError("OTP is required.")

        attrs["email"] = email or None
        attrs["phone"] = phone or None
        attrs["otp"] = otp
        return attrs


class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, max_length=254)
    otp = serializers.CharField(required=True, min_length=4, max_length=10, trim_whitespace=True)

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        return email

    def validate_otp(self, value):
        otp = (value or "").strip()
        if not otp:
            raise serializers.ValidationError("OTP is required.")
        return otp


class OtpRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, max_length=254)

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        return email


class ResendOtpSerializer(OtpRequestSerializer):
    """Backward-compatible alias for existing resend endpoint."""


class CustomPasswordChangeSerializer(PasswordChangeSerializer):

    def save(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not getattr(user, "pk", None):
            raise serializers.ValidationError("Authenticated user is required for password change.")

        new_password = self.validated_data["new_password1"]
        password_validation.validate_password(new_password, user)
        
        hashed_password = make_password(new_password)

        try:
            result = mongo_db["api_customuser"].update_one(
                {"_id": ObjectId(str(user.pk))},
                {"$set": {"password": hashed_password}},
            )
        except Exception as e:
            print("Mongo password update error:", repr(e))

        return user


class PromptModelSerializer(serializers.ModelSerializer):
    """CRUD serializer for Prompt model."""

    class Meta:
        model = Prompt
        fields = ("_id", "service_id", "prompt_type", "title", "icon", "prompt_text")
        read_only_fields = ("_id",)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = str(instance.pk)
        data.pop("_id", None)
        sid = getattr(instance, "service_id", None)
        data["service_id"] = str(sid) if sid is not None else None
        return data