from django.contrib.auth.hashers import check_password
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User, UserSession


class LoginView(APIView):
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not check_password(password, user.password_hash):
            return Response(
                {"error": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        now = timezone.now()
        session, _ = UserSession.objects.update_or_create(
            user=user,
            defaults={
                "status": "idle",
                "current_match_id": None,
                "last_heartbeat_at": now,
                "updated_at": now,
            },
        )

        return Response(
            {
                "message": "Đăng nhập thành công",
                "data": {
                    "session_id": str(session.session_id),
                    "user": {
                        "user_id": user.user_id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "total_score": float(user.total_score),
                    },
                },
            },
            status=status.HTTP_200_OK,
        )
