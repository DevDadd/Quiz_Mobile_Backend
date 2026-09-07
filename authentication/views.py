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

from authentication.models import Challenge

class ChallengeView(APIView):
    def post(self, request):
        # API Gửi thách đấu
        session_token = request.headers.get('Authorization')
        if not session_token:
            return Response({'error': 'Thiếu Token'}, status=401)
            
        try:
            current_session = UserSession.objects.get(session_id=session_token)
        except UserSession.DoesNotExist:
            return Response({'error': 'Token không hợp lệ'}, status=401)
            
        opponent_id = request.data.get('opponent_id')
        if not opponent_id:
            return Response({'error': 'Thiếu ID đối thủ'}, status=400)
            
        try:
            opponent = User.objects.get(user_id=opponent_id)
        except User.DoesNotExist:
            return Response({'error': 'Không tìm thấy đối thủ'}, status=404)
            
        # Tạo bản ghi thách đấu mới
        challenge = Challenge.objects.create(
            challenger=current_session.user,
            opponent=opponent,
            status='pending',
            created_at=timezone.now(),
            updated_at=timezone.now()
        )
        
        return Response({'message': 'Đã gửi lời thách đấu', 'challenge_id': challenge.challenge_id}, status=201)

    def get(self, request):
        # API Poll nhận thách đấu (Xem có ai thách đấu mình không)
        session_token = request.headers.get('Authorization')
        if not session_token:
            return Response({'error': 'Thiếu Token'}, status=401)
            
        try:
            current_session = UserSession.objects.get(session_id=session_token)
        except UserSession.DoesNotExist:
            return Response({'error': 'Token không hợp lệ'}, status=401)
            
        # Tìm các thách đấu gửi đến mình, trạng thái pending, trong 30 giây qua
        thirty_secs_ago = timezone.now() - timezone.timedelta(seconds=30)
        pending_challenges = Challenge.objects.filter(
            opponent=current_session.user,
            status='pending',
            created_at__gte=thirty_secs_ago
        ).select_related('challenger')
        
        data = []
        for c in pending_challenges:
            data.append({
                'challenge_id': c.challenge_id,
                'challenger_id': c.challenger.user_id,
                'challenger_name': c.challenger.username,
                'created_at': c.created_at
            })
            
        return Response({'message': 'Thành công', 'data': data}, status=200)

from django.db import connection
from django.contrib.auth.hashers import make_password
from authentication.services import get_auth_session

class RegisterView(APIView):
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        display_name = request.data.get("display_name", username)
        
        if not username or not password:
            return Response({"error": "Missing username or password"}, status=400)
            
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists"}, status=400)
            
        user = User.objects.create(
            username=username,
            password_hash=make_password(password),
            display_name=display_name,
            total_score=0,
            created_at=timezone.now()
        )
        return Response({"user_id": user.user_id}, status=201)

class LogoutView(APIView):
    def post(self, request):
        user_id, session_id = get_auth_session(request)
        if not session_id: return Response({"error": "Unauthorized"}, status=401)
        
        UserSession.objects.filter(session_id=session_id).update(
            status='offline',
            current_match_id=None,
            updated_at=timezone.now()
        )
        return Response({"ok": True}, status=200)

class MeView(APIView):
    def get(self, request):
        user_id, session_id = get_auth_session(request)
        if not user_id: return Response({"error": "Unauthorized"}, status=401)
        
        user = User.objects.get(user_id=user_id)
        return Response({
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "total_score": float(user.total_score),
            "created_at": user.created_at
        }, status=200)

class HeartbeatView(APIView):
    def post(self, request):
        user_id, session_id = get_auth_session(request)
        if not session_id: return Response({"error": "Unauthorized"}, status=401)
        
        since = request.query_params.get('since', 0)
        try:
            since = float(since)
        except ValueError:
            since = 0
            
        with connection.cursor() as cursor:
            # Update heartbeat
            cursor.execute("UPDATE sessions SET last_heartbeat_at = now(), updated_at = now() WHERE session_id = %s", [session_id])
            
            # Fetch statuses as per PDF #4
            query = """
            SELECT s.current_match_id,
              (SELECT row_to_json(c) FROM challenges c 
               WHERE c.opponent_id = s.user_id AND c.status = 'pending' 
               AND c.created_at > now() - interval '30 seconds' 
               ORDER BY c.created_at DESC LIMIT 1) AS incoming_challenge,
              (SELECT row_to_json(c) FROM challenges c 
               WHERE c.challenger_id = s.user_id AND c.updated_at > to_timestamp(%s/1000.0) 
               ORDER BY c.updated_at DESC LIMIT 1) AS outgoing_challenge_update
            FROM sessions s WHERE s.session_id = %s
            """
            cursor.execute(query, [since, session_id])
            row = cursor.fetchone()
            
            # Postgres row_to_json returns dict directly when fetched via psycopg2 sometimes, or string
            # We'll just return it safely
            import json
            def safe_json(val):
                if isinstance(val, str): return json.loads(val)
                return val
                
            return Response({
                "server_time": timezone.now().timestamp() * 1000,
                "current_match_id": row[0] if row else None,
                "incoming_challenge": safe_json(row[1]) if row and row[1] else None,
                "outgoing_challenge_update": safe_json(row[2]) if row and row[2] else None
            }, status=200)


