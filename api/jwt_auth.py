import hashlib
import logging
from bson import ObjectId
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def _get_md5_hash_password(password):
    """MD5 hash of password for revoke-claim comparison (replaces removed simplejwt.utils.get_md5_hash_password)."""
    if password is None:
        return None
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def _user_from_mongo_doc(User, doc):
    """Build a User instance from a MongoDB api_customuser document (id = _id, _state.adding = False)."""
    if not doc:
        return None
    user = User()
    user._id = doc["_id"]
    user._state.adding = False
    user._state.db = "default"
    for f in User._meta.fields:
        if f.attname != "_id" and f.attname in doc:
            setattr(user, f.attname, doc[f.attname])
    return user


class CustomUserJWTAuthentication(JWTAuthentication):
    """Resolve user from JWT by ObjectId; fallback to raw MongoDB when ORM get fails (Djongo)."""

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as e:
            raise InvalidToken(
                _("Token contained no recognizable user identification")
            ) from e

        User = get_user_model()
        try:
            oid = ObjectId(user_id) if isinstance(user_id, str) else user_id
        except Exception:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        user = None
        # 1) Try ORM (works with some Djongo setups). Use pk= so it works with _id as primary key.
        try:
            user = User.objects.get(pk=oid)
        except User.DoesNotExist:
            pass

        # 2) Fallback: load from MongoDB by _id (Djongo get(id=ObjectId) often fails)
        if user is None:
            try:
                from api.db import db as mongo_db
                doc = mongo_db["api_customuser"].find_one({"_id": oid})
                user = _user_from_mongo_doc(User, doc) if doc else None
            except Exception as e:
                logger.warning("JWT auth: MongoDB fallback for user_id=%s failed: %r", oid, e)

        if user is None:
            raise AuthenticationFailed(_("User not found"), code="user_not_found")

        # Optional checks (some SimpleJWT versions don't define these settings)
        check_active = getattr(api_settings, "CHECK_USER_IS_ACTIVE", True)
        if check_active and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")

        check_revoke = getattr(api_settings, "CHECK_REVOKE_TOKEN", False)
        if check_revoke:
            revoke_claim = getattr(api_settings, "REVOKE_TOKEN_CLAIM", "revoke_claim")
            if validated_token.get(revoke_claim) != _get_md5_hash_password(user.password):
                raise AuthenticationFailed(
                    _("The user's password has been changed."),
                    code="password_changed",
                )

        return user
