from django.db import connection
from django.utils import timezone
from authentication.models import User, UserSession

# --- INTERNAL FUNCTIONS CHO DEV 2 GỌI ---

def get_auth_session(request):
    """ Tương đương auth.middleware(req) """
    session_id = request.headers.get('Authorization')
    if not session_id:
        return None, None
    try:
        session = UserSession.objects.get(session_id=session_id)
        return session.user.user_id, session_id
    except UserSession.DoesNotExist:
        return None, None

def is_available(user_id):
    """ presence.isAvailable(userId) -> bool """
    try:
        # online (heartbeat < 15s) && current_match_id IS NULL
        session = UserSession.objects.get(user_id=user_id)
        time_diff = timezone.now() - session.last_heartbeat_at
        if time_diff.total_seconds() <= 15 and session.current_match_id is None and session.status == 'idle':
            return True
        return False
    except UserSession.DoesNotExist:
        return False

def enter_match(user_ids, match_id):
    """ presence.enterMatch(tx, [userId...], matchId) """
    UserSession.objects.filter(user_id__in=user_ids).update(
        current_match_id=match_id,
        status='busy',
        updated_at=timezone.now()
    )

def leave_match(match_id):
    """ presence.leaveMatch(tx, matchId) """
    UserSession.objects.filter(current_match_id=match_id).update(
        current_match_id=None,
        status='idle',
        updated_at=timezone.now()
    )

def add_points(user_id, points):
    """ score.addPoints(tx, userId, points) """
    if user_id is None:
        return # Skip nếu là bot
    with connection.cursor() as cursor:
        cursor.execute("UPDATE users SET total_score = total_score + %s WHERE user_id = %s", [points, user_id])

def pick_for_match(match_id, n):
    """ questions.pickForMatch(tx, matchId, n) """
    with connection.cursor() as cursor:
        cursor.execute('''
            INSERT INTO match_questions (match_id, question_id, order_index)
            SELECT %s, question_id, row_number() over() - 1
            FROM questions
            ORDER BY random()
            LIMIT %s
        ''', [match_id, n])
