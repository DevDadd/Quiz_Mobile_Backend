from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from authentication.models import User


def create_access_token(user):
    now = timezone.now()
    payload = {
        "sub": str(user.user_id),
        "username": user.username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


class JWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        authorization = get_authorization_header(request).split()
        if not authorization:
            return None

        if len(authorization) != 2 or authorization[0].decode().lower() != "bearer":
            raise AuthenticationFailed("Authorization header must be: Bearer <token>.")

        try:
            token = authorization[1].decode()
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=["HS256"],
                options={"require": ["sub", "iat", "exp", "type"]},
            )
        except (UnicodeError, jwt.InvalidTokenError):
            raise AuthenticationFailed("Invalid or expired access token.")

        if payload.get("type") != "access":
            raise AuthenticationFailed("Invalid access token.")

        try:
            user = User.objects.get(user_id=payload["sub"])
        except (User.DoesNotExist, ValueError, TypeError):
            raise AuthenticationFailed("User does not exist.")

        return user, payload

    def authenticate_header(self, request):
        return self.keyword
