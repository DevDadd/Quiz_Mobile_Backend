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

class OnlinePlayersView(APIView):
    def get(self, request):
        user_id, session_id = get_auth_session(request)
        if not user_id: return Response({"error": "Unauthorized"}, status=401)
        
        with connection.cursor() as cursor:
            query = """
            SELECT u.user_id, u.display_name, u.total_score,
            CASE WHEN s.current_match_id IS NOT NULL THEN 'busy' ELSE 'idle' END AS status
            FROM sessions s JOIN users u USING (user_id)
            WHERE s.status = 'online'
            AND s.last_heartbeat_at > now() - interval '15 seconds'
            AND u.user_id <> %s
            ORDER BY u.total_score DESC
            """
            cursor.execute(query, [user_id])
            columns = [col[0] for col in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Convert decimal to float
            for d in data:
                d['total_score'] = float(d['total_score'])
                
        return Response(data, status=200)

# ==========================================
# CÁC API CÒN LẠI CỦA DEV 1 (#7 ĐẾN #13)
# ==========================================

class LeaderboardView(APIView):
    def get(self, request):
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        
        with connection.cursor() as cursor:
            # Query chuẩn xác 100% từ PDF trang 3
            query = """
            WITH pvp AS (
                SELECT mp.user_id, mp.result, mp.duration_seconds, opp.user_id AS opp_id
                FROM match_participants mp
                JOIN matches m ON m.match_id = mp.match_id AND m.status = 'finished' AND m.opponent_type = 'HUMAN'
                JOIN match_participants opp ON opp.match_id = mp.match_id AND opp.side <> mp.side
                WHERE mp.user_id IS NOT NULL
            )
            SELECT u.user_id, u.display_name, u.total_score,
                AVG(ou.total_score) AS avg_opp_score,
                AVG(p.duration_seconds) FILTER (WHERE p.result = 'win') AS avg_win_time
            FROM users u
            LEFT JOIN pvp p ON p.user_id = u.user_id
            LEFT JOIN users ou ON ou.user_id = p.opp_id
            GROUP BY u.user_id, u.display_name, u.total_score
            ORDER BY u.total_score DESC, avg_opp_score DESC NULLS LAST, avg_win_time ASC NULLS LAST
            LIMIT %s OFFSET %s
            """
            cursor.execute(query, [limit, offset])
            columns = [col[0] for col in cursor.description]
            data = []
            for i, row in enumerate(cursor.fetchall()):
                d = dict(zip(columns, row))
                d['rank'] = offset + i + 1
                d['total_score'] = float(d['total_score'])
                d['avg_opp_score'] = float(d['avg_opp_score']) if d['avg_opp_score'] else 0.0
                d['avg_win_time'] = float(d['avg_win_time']) if d['avg_win_time'] else 0.0
                data.append(d)
                
        return Response(data, status=200)

class UserStatsView(APIView):
    def get(self, request, id):
        with connection.cursor() as cursor:
            query = """
            SELECT 
              count(*) as played,
              count(*) FILTER (WHERE result = 'win') as win,
              count(*) FILTER (WHERE result = 'draw') as draw,
              count(*) FILTER (WHERE result = 'lose') as lose,
              AVG(duration_seconds) FILTER (WHERE result = 'win') as avg_win_time
            FROM match_participants
            WHERE user_id = %s
            """
            cursor.execute(query, [id])
            row = cursor.fetchone()
            
            return Response({
                "played": row[0] or 0,
                "win": row[1] or 0,
                "draw": row[2] or 0,
                "lose": row[3] or 0,
                "avg_win_time": float(row[4]) if row[4] else 0.0
            }, status=200)

class UserMatchesView(APIView):
    def get(self, request, id):
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        
        with connection.cursor() as cursor:
            query = """
            SELECT m.match_id, 
                   COALESCE(opp_user.display_name, 'BOT') as opponent_name, 
                   mp.result, mp.points_earned, mp.correct_count, mp.duration_seconds, m.ended_at
            FROM match_participants mp
            JOIN matches m ON m.match_id = mp.match_id
            LEFT JOIN match_participants opp ON opp.match_id = m.match_id AND opp.side <> mp.side
            LEFT JOIN users opp_user ON opp_user.user_id = opp.user_id
            WHERE mp.user_id = %s
            ORDER BY m.ended_at DESC NULLS LAST
            LIMIT %s OFFSET %s
            """
            cursor.execute(query, [id, limit, offset])
            columns = [col[0] for col in cursor.description]
            data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            for d in data:
                d['points_earned'] = float(d['points_earned'])
                
        return Response(data, status=200)

class QuestionsView(APIView):
    def get(self, request):
        # #10 Lấy danh sách câu hỏi
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT question_id, content, category, difficulty FROM questions ORDER BY question_id DESC LIMIT %s OFFSET %s", [limit, offset])
            columns = [col[0] for col in cursor.description]
            questions = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            for q in questions:
                cursor.execute("SELECT option_id, content, is_correct, order_index FROM question_options WHERE question_id = %s ORDER BY order_index", [q['question_id']])
                opt_cols = [col[0] for col in cursor.description]
                q['options'] = [dict(zip(opt_cols, row)) for row in cursor.fetchall()]
                
        return Response(questions, status=200)
        
    def post(self, request):
        # #11 Thêm câu hỏi
        data = request.data
        options = data.get('options', [])
        
        # Validate đúng 1 đáp án đúng
        if sum([1 for o in options if o.get('is_correct')]) != 1:
            return Response({"error": "Phải có đúng 1 đáp án đúng"}, status=400)
            
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO questions (content, category, difficulty, created_at) VALUES (%s, %s, %s, now()) RETURNING question_id",
                [data.get('content'), data.get('category'), data.get('difficulty')]
            )
            q_id = cursor.fetchone()[0]
            
            for opt in options:
                cursor.execute(
                    "INSERT INTO question_options (question_id, content, is_correct, order_index) VALUES (%s, %s, %s, %s)",
                    [q_id, opt.get('content'), opt.get('is_correct'), opt.get('order_index')]
                )
        return Response({"question_id": q_id}, status=201)

class QuestionDetailView(APIView):
    def put(self, request, id):
        # #12 Sửa câu hỏi
        data = request.data
        options = data.get('options', [])
        
        if sum([1 for o in options if o.get('is_correct')]) != 1:
            return Response({"error": "Phải có đúng 1 đáp án đúng"}, status=400)
            
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE questions SET content=%s, category=%s, difficulty=%s WHERE question_id=%s",
                [data.get('content'), data.get('category'), data.get('difficulty'), id]
            )
            cursor.execute("DELETE FROM question_options WHERE question_id=%s", [id])
            for opt in options:
                cursor.execute(
                    "INSERT INTO question_options (question_id, content, is_correct, order_index) VALUES (%s, %s, %s, %s)",
                    [id, opt.get('content'), opt.get('is_correct'), opt.get('order_index')]
                )
        return Response({"ok": True}, status=200)

    def delete(self, request, id):
        # #13 Xóa câu hỏi (Chặn nếu đã có trong trận)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM match_questions WHERE question_id = %s LIMIT 1", [id])
            if cursor.fetchone():
                return Response({"error": "Không thể xóa câu hỏi đã được sử dụng trong trận đấu"}, status=400)
            
            cursor.execute("DELETE FROM questions WHERE question_id = %s", [id])
            
        return Response({"ok": True}, status=200)
