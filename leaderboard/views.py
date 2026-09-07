from django.db import connection
from rest_framework.response import Response
from rest_framework.views import APIView
from authentication.services import get_auth_session

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

