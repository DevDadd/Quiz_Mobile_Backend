from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User, UserSession


class LoginView(APIView):
    def post(self, request):
        session, user, error = login(request.data.get("username"), request.data.get("password"))
        if error:
            return Response({"error": error[0]}, status=error[1])

        return Response(
            {
                "message": "ÄÄƒng nháº­p thÃ nh cÃ´ng",
                "data": {
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

from django.db import connection
from authentication.services import get_auth_session, login, register_new_account

class RegisterView(APIView):
    def post(self, request):
        username = request.data.get("username")
        user, error = register_new_account(
            username,
            request.data.get("password"),
            request.data.get("display_name", username),
        )
        if error:
            return Response({"error": error[0]}, status=error[1])
        return Response({"user_id": user.user_id}, status=201)

class LogoutView(APIView):
    def post(self, request):
        user_id, session_id = get_auth_session(request)
        if not session_id: return Response({"error": "Unauthorized"}, status=401)
        
        # session_status_enum chá»‰ cÃ³ idle|busy (khÃ´ng cÃ³ offline) â€” "Ä‘Äƒng xuáº¥t" Ä‘Æ°á»£c biá»ƒu diá»…n
        # báº±ng cÃ¡ch Ä‘áº©y last_heartbeat_at vá» quÃ¡ khá»© Ä‘á»ƒ má»i check "online" (dá»±a trÃªn heartbeat
        # gáº§n Ä‘Ã¢y) coi user nÃ y lÃ  offline ngay láº­p tá»©c, thay vÃ¬ chá» 15s háº¿t háº¡n tá»± nhiÃªn.
        UserSession.objects.filter(session_id=session_id).update(
            status='idle',
            current_match_id=None,
            last_heartbeat_at=timezone.now() - timezone.timedelta(hours=1),
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


