from django.contrib.auth.hashers import check_password, make_password
from django.db import connection
from django.utils import timezone
from authentication.models import User, UserSession

# --- Users: hÃ m theo tÃ i liá»‡u phÃ¢n tÃ­ch (registerNewAccount, login, getAllPlayers) ---
# CÃ¡c hÃ m tráº£ vá» (káº¿t quáº£, lá»—i). lá»—i lÃ  None hoáº·c (thÃ´ng bÃ¡o, http_status).

def register_new_account(username, password, display_name=None):
    """Users.registerNewAccount()"""
    if not username or not password:
        return None, ("Missing username or password", 400)
    if User.objects.filter(username=username).exists():
        return None, ("Username already exists", 400)

    user = User.objects.create(
        username=username,
        password_hash=make_password(password),
        display_name=display_name,
        total_score=0,
        created_at=timezone.now(),
    )
    return user, None


def login(username, password):
    """Users.login(): xÃ¡c thá»±c rá»“i táº¡o/lÃ m má»›i phiÃªn Ä‘Äƒng nháº­p. Tráº£ vá» (session, user, lá»—i)."""
    if not username or not password:
        return None, None, ("Username and password are required.", 400)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return None, None, ("Invalid username or password.", 401)

    if not check_password(password, user.password_hash):
        return None, None, ("Invalid username or password.", 401)

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
    return session, user, None


def get_all_players(exclude_user_id):
    """Users.getAllPlayers(): toÃ n bá»™ ngÆ°á»i chÆ¡i trá»« chÃ­nh mÃ¬nh (khÃ´ng phÃ¢n biá»‡t online)."""
    players = User.objects.exclude(user_id=exclude_user_id).order_by('-total_score', 'user_id')
    return [
        {
            "user_id": u.user_id,
            "display_name": u.display_name or u.username,
            "total_score": float(u.total_score),
        }
        for u in players
    ]


# --- Sessions / Users: hÃ m ná»™i bá»™ cho cÃ¡c app khÃ¡c gá»i ---

def get_auth_session(request):
    """Resolve the active session from user_id without requiring a token.

    Send user_id in the query string for GET requests or JSON body for writes.
    This identifies a player but does not authenticate them.
    """
    data = getattr(request, "data", None)
    user_id = data.get("user_id") if hasattr(data, "get") else None
    user_id = user_id or request.query_params.get("user_id")
    if not user_id:
        return None, None
    try:
        session = UserSession.objects.get(user_id=int(user_id))
        return session.user.user_id, str(session.session_id)
    except (UserSession.DoesNotExist, TypeError, ValueError):
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

def set_busy(user_ids, match_id):
    """ presence.enterMatch(tx, [userId...], matchId) """
    UserSession.objects.filter(user_id__in=user_ids).update(
        current_match_id=match_id,
        status='busy',
        updated_at=timezone.now()
    )

def set_idle(match_id):
    """ presence.leaveMatch(tx, matchId) """
    UserSession.objects.filter(current_match_id=match_id).update(
        current_match_id=None,
        status='idle',
        updated_at=timezone.now()
    )

def update_score(user_id, points):
    """ score.addPoints(tx, userId, points) """
    if user_id is None:
        return # Skip náº¿u lÃ  bot
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
