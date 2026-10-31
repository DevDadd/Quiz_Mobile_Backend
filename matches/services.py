import random
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from authentication.models import User, UserSession
from authentication.services import is_available, update_score, set_busy, set_idle, pick_for_match
from matches.models import Challenge

# --- Hằng số ---
# Giá trị enum khớp đúng schema thật trong Postgres (xem information_schema/pg_enum),
# khác với chữ thường trong bản đặc tả PDF gốc.

SIDE_P1 = 'P1'
SIDE_P2 = 'P2'

MATCH_STATUS_ONGOING = 'ongoing'
MATCH_STATUS_FINISHED = 'finished'

DEFAULT_QUESTION_COUNT = 10
DEFAULT_TIME_LIMIT_SECONDS = 60
CHALLENGE_EXPIRY_SECONDS = 30
REMATCH_TIMEOUT_SECONDS = 30

# challenge_status_enum thật không có 'cancelled' -> dùng 'expired' cho "tự rút lại / tự hủy".
CHALLENGE_STATUS_SELF_CANCELLED = 'expired'

# Client dùng easy/medium/hard (đúng chữ đặc tả); DB lưu bot_difficulty_enum viết hoa.
BOT_DIFFICULTY_DB = {'easy': 'EASY', 'medium': 'NORMAL', 'hard': 'HARD'}

BOT_PROFILES = {
    'easy': {'accuracy': 0.55, 'duration_range': (0.60, 0.95)},
    'medium': {'accuracy': 0.75, 'duration_range': (0.40, 0.80)},
    'hard': {'accuracy': 0.92, 'duration_range': (0.25, 0.60)},
}

MATCH_COLUMNS = [
    'match_id', 'status', 'opponent_type', 'bot_difficulty', 'question_count',
    'time_limit_seconds', 'started_at', 'ended_at', 'updated_at',
]


def get_match(match_id, for_update=False):
    """Đọc 1 dòng matches. Không dùng ORM vì bảng matches chưa có model."""
    query = f"SELECT {', '.join(MATCH_COLUMNS)} FROM matches WHERE match_id = %s"
    if for_update:
        query += " FOR UPDATE"
    with connection.cursor() as cursor:
        cursor.execute(query, [match_id])
        row = cursor.fetchone()
    if not row:
        return None
    return dict(zip(MATCH_COLUMNS, row))


def get_participants(match_id):
    """Trả về {side: {user_id, result, points_earned, correct_count, duration_seconds, submitted_at}}."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT side, user_id, result, points_earned, correct_count, duration_seconds, submitted_at
            FROM match_participants WHERE match_id = %s
            """,
            [match_id],
        )
        rows = cursor.fetchall()
    return {
        r[0]: {
            'user_id': r[1],
            'result': r[2],
            'points_earned': r[3],
            'correct_count': r[4],
            'duration_seconds': r[5],
            'submitted_at': r[6],
        }
        for r in rows
    }


def my_side_in_match(match_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT side FROM match_participants WHERE match_id = %s AND user_id = %s",
            [match_id, user_id],
        )
        row = cursor.fetchone()
    return row[0] if row else None


def create_match(challenger_id, opponent_id, question_count=DEFAULT_QUESTION_COUNT,
                  time_limit_seconds=DEFAULT_TIME_LIMIT_SECONDS, opponent_type='HUMAN',
                  bot_difficulty_db=None):
    """Tạo match (status='ongoing' ngay vì đã biết đủ 2 người chơi) + 2 match_participants.
    opponent_id có thể None nếu là bot (matches.player2_id cho phép NULL)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO matches (
                status, opponent_type, bot_difficulty, player1_id, player2_id,
                question_count, time_limit_seconds, started_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
            RETURNING match_id
            """,
            [MATCH_STATUS_ONGOING, opponent_type, bot_difficulty_db, challenger_id, opponent_id,
             question_count, time_limit_seconds],
        )
        match_id = cursor.fetchone()[0]
        # result/points_earned là NOT NULL không default trong DB thật -> đặt placeholder
        # 'draw'/0, sẽ bị calculate_result() ghi đè giá trị thật. submitted_at NULL = chưa nộp bài.
        cursor.execute(
            """
            INSERT INTO match_participants (match_id, side, user_id, result, points_earned, correct_count)
            VALUES
                (%s, %s, %s, 'draw', 0, 0),
                (%s, %s, %s, 'draw', 0, 0)
            """,
            [match_id, SIDE_P1, challenger_id, match_id, SIDE_P2, opponent_id],
        )
    pick_for_match(match_id, question_count)
    return match_id


def generate_bot_answers(match_id, side, bot_difficulty, question_count, time_limit_seconds):
    """Sinh sẵn toàn bộ đáp án + correct_count/duration_seconds/submitted_at cho bot ngay lúc tạo match."""
    profile = BOT_PROFILES.get(bot_difficulty, BOT_PROFILES['medium'])
    accuracy = profile['accuracy']
    lo, hi = profile['duration_range']

    correct_count = 0
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT order_index, question_id FROM match_questions WHERE match_id = %s ORDER BY order_index",
            [match_id],
        )
        questions_list = cursor.fetchall()

        for order_index, question_id in questions_list:
            cursor.execute(
                "SELECT option_id, is_correct FROM question_options WHERE question_id = %s ORDER BY order_index",
                [question_id],
            )
            options = cursor.fetchall()
            if not options:
                continue
            correct_options = [o for o in options if o[1]]
            wrong_options = [o for o in options if not o[1]]

            answer_correctly = random.random() < accuracy
            if answer_correctly and correct_options:
                chosen = random.choice(correct_options)
            elif wrong_options:
                chosen = random.choice(wrong_options)
            else:
                chosen = random.choice(options)

            is_correct = bool(chosen[1])
            if is_correct:
                correct_count += 1

            response_time_ms = random.randint(500, 4000)
            cursor.execute(
                """
                INSERT INTO match_answers (match_id, order_index, side, selected_option_id, is_correct, response_time_ms, answered_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (match_id, order_index, side) DO UPDATE
                SET selected_option_id = EXCLUDED.selected_option_id,
                    is_correct = EXCLUDED.is_correct,
                    response_time_ms = EXCLUDED.response_time_ms,
                    answered_at = EXCLUDED.answered_at
                """,
                [match_id, order_index, side, chosen[0], is_correct, response_time_ms],
            )

        duration_seconds = int(time_limit_seconds * random.uniform(lo, hi))
        cursor.execute(
            """
            UPDATE match_participants
            SET correct_count = %s, duration_seconds = %s, submitted_at = now()
            WHERE match_id = %s AND side = %s
            """,
            [correct_count, duration_seconds, match_id, side],
        )


def calculate_result(match_id):
    """Chấm thắng/thua/hòa + cộng điểm + đóng trận. Gọi khi cả 2 bên đã có submitted_at."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT question_count FROM matches WHERE match_id = %s", [match_id])
        row = cursor.fetchone()
        if not row:
            return
        question_count = row[0]

    participants = get_participants(match_id)
    sides = list(participants.keys())
    if len(sides) != 2:
        return
    side_a, side_b = sides
    a, b = participants[side_a], participants[side_b]

    a_perfect = a['correct_count'] == question_count
    b_perfect = b['correct_count'] == question_count

    if a_perfect and b_perfect:
        if a['duration_seconds'] == b['duration_seconds']:
            winner_side = None
        elif a['duration_seconds'] < b['duration_seconds']:
            winner_side = side_a
        else:
            winner_side = side_b
    elif a_perfect:
        winner_side = side_a
    elif b_perfect:
        winner_side = side_b
    else:
        winner_side = None

    with connection.cursor() as cursor:
        for side, p in participants.items():
            if winner_side is None:
                result, points = 'draw', 0.5
            elif side == winner_side:
                result, points = 'win', 1.0
            else:
                result, points = 'lose', 0.0
            cursor.execute(
                "UPDATE match_participants SET result = %s, points_earned = %s WHERE match_id = %s AND side = %s",
                [result, points, match_id, side],
            )
            update_score(p['user_id'], points)

        cursor.execute(
            "UPDATE matches SET status = %s, ended_at = now(), updated_at = now() WHERE match_id = %s",
            [MATCH_STATUS_FINISHED, match_id],
        )

    set_idle(match_id)


def _auto_submit_side(cursor, match_id, side, time_limit_seconds):
    cursor.execute(
        """
        UPDATE match_answers a SET is_correct = COALESCE(o.is_correct, false)
        FROM question_options o
        WHERE o.option_id = a.selected_option_id
        AND a.match_id = %s AND a.side = %s
        """,
        [match_id, side],
    )
    cursor.execute(
        """
        UPDATE match_participants SET
            correct_count = (SELECT count(*) FROM match_answers WHERE match_id = %s AND side = %s AND is_correct),
            duration_seconds = %s,
            submitted_at = now()
        WHERE match_id = %s AND side = %s AND submitted_at IS NULL
        """,
        [match_id, side, time_limit_seconds, match_id, side],
    )


def resolve_if_expired(match_id):
    """Kiểm tra deadline quá hạn và tự giải quyết (auto-submit + calculate_result) nếu cần.
    Phải gọi ở đầu mọi request đọc/ghi match theo nguyên tắc timeout lazy."""
    with transaction.atomic():
        match = get_match(match_id, for_update=True)
        if not match or match['status'] != MATCH_STATUS_ONGOING:
            return match

        deadline = match['started_at'] + timedelta(seconds=match['time_limit_seconds'])
        if timezone.now() < deadline:
            return match

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT side FROM match_participants WHERE match_id = %s AND submitted_at IS NULL",
                [match_id],
            )
            unfinished_sides = [r[0] for r in cursor.fetchall()]
            for side in unfinished_sides:
                _auto_submit_side(cursor, match_id, side, match['time_limit_seconds'])

        calculate_result(match_id)

    return get_match(match_id)


# ---------------------------------------------------------------------------
# Challenges: sendChallenge, getPendingChallenge, acceptChallenge, rejectChallenge
# Các hàm trả về (kết quả, lỗi). lỗi là None hoặc (thông báo, http_status[, dữ liệu thêm]).
# ---------------------------------------------------------------------------

def send_challenge(challenger_id, opponent_id):
    """Challenges.sendChallenge(): tạo lời mời thách đấu (pending)."""
    if opponent_id == challenger_id:
        return None, ("Không thể tự thách đấu chính mình", 400)
    if not User.objects.filter(user_id=opponent_id).exists():
        return None, ("Không tìm thấy đối thủ", 404)
    if not is_available(opponent_id):
        return None, ("Đối thủ hiện không sẵn sàng", 400)

    active_since = timezone.now() - timedelta(seconds=CHALLENGE_EXPIRY_SECONDS)
    already_pending = Challenge.objects.filter(
        status='pending',
        created_at__gte=active_since,
    ).filter(
        Q(challenger_id=challenger_id, opponent_id=opponent_id)
        | Q(challenger_id=opponent_id, opponent_id=challenger_id)
    ).exists()
    if already_pending:
        return None, ("Đã có lời thách đấu đang chờ giữa hai người", 400)

    now = timezone.now()
    challenge = Challenge.objects.create(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        status='pending',
        created_at=now,
        updated_at=now,
    )
    return {"challenge_id": challenge.challenge_id, "status": "pending"}, None


def get_pending_challenge(user_id):
    """Challenges.getPendingChallenge(): lời mời đang chờ gửi tới user (còn hạn), hoặc None."""
    since = timezone.now() - timedelta(seconds=CHALLENGE_EXPIRY_SECONDS)
    c = Challenge.objects.filter(
        opponent_id=user_id, status='pending', created_at__gte=since,
    ).order_by('-created_at').first()
    if not c:
        return None
    challenger = User.objects.get(user_id=c.challenger_id)
    return {
        "challenge_id": c.challenge_id,
        "challenger_id": c.challenger_id,
        "challenger_name": challenger.display_name or challenger.username,
        "challenger_total_score": float(challenger.total_score),
        "created_at": c.created_at,
    }


def get_challenge(challenge_id, user_id):
    try:
        c = Challenge.objects.get(challenge_id=challenge_id)
    except Challenge.DoesNotExist:
        return None, ("Không tìm thấy", 404)
    if user_id not in (c.challenger_id, c.opponent_id):
        return None, ("Forbidden", 403)
    return {"challenge_id": c.challenge_id, "status": c.status, "match_id": c.match_id}, None


def accept_challenge(challenge_id, user_id):
    """Challenges.acceptChallenge(): đối thủ đồng ý -> tạo trận (createMatch) + đặt cả hai sang busy."""
    with transaction.atomic():
        try:
            c = Challenge.objects.select_for_update().get(challenge_id=challenge_id)
        except Challenge.DoesNotExist:
            return None, ("Không tìm thấy", 404)

        if c.opponent_id != user_id:
            return None, ("Forbidden", 403)

        if c.status == 'accepted':
            return c.match_id, None
        if c.status != 'pending':
            return None, ("Lời thách đấu không còn hiệu lực", 400)
        if timezone.now() - c.created_at > timedelta(seconds=CHALLENGE_EXPIRY_SECONDS):
            return None, ("Lời thách đấu đã hết hạn", 400)

        sessions = list(UserSession.objects.select_for_update().filter(
            user_id__in=[c.challenger_id, c.opponent_id]
        ))
        if any(s.current_match_id is not None for s in sessions):
            return None, ("Một trong hai người đã ở trong trận khác", 409)

        match_id = create_match(c.challenger_id, c.opponent_id)
        set_busy([c.challenger_id, c.opponent_id], match_id)

        c.status = 'accepted'
        c.match_id = match_id
        c.responded_at = timezone.now()
        c.updated_at = timezone.now()
        c.save()
    return match_id, None


def reject_challenge(challenge_id, user_id):
    """Challenges.rejectChallenge(): người được mời từ chối."""
    with transaction.atomic():
        try:
            c = Challenge.objects.select_for_update().get(challenge_id=challenge_id)
        except Challenge.DoesNotExist:
            return ("Không tìm thấy", 404)
        if c.opponent_id != user_id:
            return ("Forbidden", 403)
        if c.status == 'pending':
            c.status = 'rejected'
            c.responded_at = timezone.now()
            c.updated_at = timezone.now()
            c.save()
    return None


def cancel_challenge(challenge_id, user_id):
    """Người gửi tự rút lại lời mời."""
    with transaction.atomic():
        try:
            c = Challenge.objects.select_for_update().get(challenge_id=challenge_id)
        except Challenge.DoesNotExist:
            return ("Không tìm thấy", 404)
        if c.challenger_id != user_id:
            return ("Forbidden", 403)
        if c.status == 'pending':
            c.status = CHALLENGE_STATUS_SELF_CANCELLED
            c.responded_at = timezone.now()
            c.updated_at = timezone.now()
            c.save()
    return None


# ---------------------------------------------------------------------------
# Matches / Questions / Match_answers / Match_participants:
# getQuestions, getOptions, grade, isAllSubmitted, submit, getResult
# ---------------------------------------------------------------------------

def response_time_ms(match, now=None):
    now = now or timezone.now()
    return max(0, int((now - match['started_at']).total_seconds() * 1000))


def get_options(question_id, cursor):
    """Questions.getOptions(): phương án của một câu hỏi (không có is_correct)."""
    cursor.execute(
        "SELECT option_id, content, order_index FROM question_options WHERE question_id = %s ORDER BY order_index",
        [question_id],
    )
    return [{"option_id": o[0], "content": o[1], "order_index": o[2]} for o in cursor.fetchall()]


def get_questions(match_id):
    """Matches.getQuestions(): câu hỏi của trận kèm các phương án (gọi get_options cho từng câu)."""
    result = []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT mq.order_index, q.question_id, q.content
            FROM match_questions mq JOIN questions q ON q.question_id = mq.question_id
            WHERE mq.match_id = %s ORDER BY mq.order_index
            """,
            [match_id],
        )
        for order_index, question_id, content in cursor.fetchall():
            result.append({
                "order_index": order_index,
                "question_id": question_id,
                "content": content,
                "options": None,
            })
        for item in result:
            item["options"] = get_options(item["question_id"], cursor)
    return result


def _upsert_answers(cursor, match_id, side, answers, response_ms):
    saved = 0
    for a in answers:
        order_index = a.get('order_index')
        if order_index is None:
            continue
        cursor.execute(
            """
            INSERT INTO match_answers (match_id, order_index, side, selected_option_id, response_time_ms, answered_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (match_id, order_index, side) DO UPDATE
            SET selected_option_id = EXCLUDED.selected_option_id,
                response_time_ms = EXCLUDED.response_time_ms,
                answered_at = EXCLUDED.answered_at
            """,
            [match_id, order_index, side, a.get('selected_option_id'), response_ms],
        )
        saved += 1
    return saved


def save_answers(match_id, user_id, answers):
    """Lưu tạm đáp án (chưa chấm). Trả về (số câu đã lưu, lỗi)."""
    my_side = my_side_in_match(match_id, user_id)
    if not my_side:
        return None, ("Forbidden", 403)

    match = resolve_if_expired(match_id)
    if not match:
        return None, ("Không tìm thấy", 404)
    if match['status'] != MATCH_STATUS_ONGOING:
        return None, ("Trận đã kết thúc", 400, {"saved": 0})

    with connection.cursor() as cursor:
        return _upsert_answers(cursor, match_id, my_side, answers, response_time_ms(match)), None


def grade(match_id, side):
    """Match_answers.grade(): chấm đúng/sai các câu đã chọn của một phía."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE match_answers a SET is_correct = COALESCE(o.is_correct, false)
            FROM question_options o
            WHERE o.option_id = a.selected_option_id
            AND a.match_id = %s AND a.side = %s
            """,
            [match_id, side],
        )


def is_all_submitted(match_id):
    """Matches.isAllSubmitted(): cả hai bên đã nộp bài chưa."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM match_participants WHERE match_id = %s AND submitted_at IS NULL",
            [match_id],
        )
        return cursor.fetchone()[0] == 0


def submit(match_id, user_id, answers):
    """Match_participants.submit(): lưu đáp án, chấm (grade), ghi kết quả bên mình;
    cả hai đã nộp thì tính kết quả chung cuộc (calculate_result). Trả về (kết quả, lỗi)."""
    my_side = my_side_in_match(match_id, user_id)
    if not my_side:
        return None, ("Forbidden", 403)

    with transaction.atomic():
        match = get_match(match_id, for_update=True)
        if not match:
            return None, ("Không tìm thấy", 404)

        if match['status'] == MATCH_STATUS_ONGOING and timezone.now() >= match['started_at'] + timedelta(seconds=match['time_limit_seconds']):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT side FROM match_participants WHERE match_id = %s AND submitted_at IS NULL",
                    [match_id],
                )
                for side in [r[0] for r in cursor.fetchall()]:
                    _auto_submit_side(cursor, match_id, side, match['time_limit_seconds'])
            calculate_result(match_id)
            match = get_match(match_id)

        me_p = get_participants(match_id)[my_side]

        if match['status'] != MATCH_STATUS_ONGOING or me_p['submitted_at'] is not None:
            return {
                "submitted_at": me_p['submitted_at'] or match['updated_at'],
                "correct_count": me_p['correct_count'],
                "duration_seconds": me_p['duration_seconds'],
                "waiting_opponent": match['status'] == MATCH_STATUS_ONGOING,
            }, None

        with connection.cursor() as cursor:
            _upsert_answers(cursor, match_id, my_side, answers, response_time_ms(match))

        grade(match_id, my_side)

        with connection.cursor() as cursor:
            duration_seconds = int((timezone.now() - match['started_at']).total_seconds())
            cursor.execute(
                """
                UPDATE match_participants SET
                    correct_count = (SELECT count(*) FROM match_answers WHERE match_id = %s AND side = %s AND is_correct),
                    duration_seconds = %s,
                    submitted_at = now()
                WHERE match_id = %s AND side = %s
                """,
                [match_id, my_side, duration_seconds, match_id, my_side],
            )
            cursor.execute("UPDATE matches SET updated_at = now() WHERE match_id = %s", [match_id])

        waiting_opponent = not is_all_submitted(match_id)
        if not waiting_opponent:
            calculate_result(match_id)

        me_p = get_participants(match_id)[my_side]
        return {
            "submitted_at": me_p['submitted_at'],
            "correct_count": me_p['correct_count'],
            "duration_seconds": me_p['duration_seconds'],
            "waiting_opponent": waiting_opponent,
        }, None


def get_result(match_id, user_id):
    """Match_participants.getResult(): kết quả chung cuộc của trận, kèm đáp án từng câu."""
    my_side = my_side_in_match(match_id, user_id)
    if not my_side:
        return None, ("Forbidden", 403)

    match = resolve_if_expired(match_id)
    if not match:
        return None, ("Không tìm thấy", 404)
    if match['status'] != MATCH_STATUS_FINISHED:
        return None, ("Trận chưa kết thúc", 409, {"status": match['status']})

    participants = get_participants(match_id)
    opp_side = next(s for s in participants if s != my_side)
    winner_side = next((s for s, p in participants.items() if p['result'] == 'win'), None)

    def brief(p):
        return {
            "correct_count": p['correct_count'],
            "duration_seconds": p['duration_seconds'],
            "result": p['result'],
            "points_earned": float(p['points_earned']) if p['points_earned'] is not None else None,
        }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT mq.order_index,
                   me_a.selected_option_id AS my_option,
                   correct_opt.option_id AS correct_option
            FROM match_questions mq
            LEFT JOIN match_answers me_a
                ON me_a.match_id = mq.match_id AND me_a.order_index = mq.order_index AND me_a.side = %s
            LEFT JOIN question_options correct_opt
                ON correct_opt.question_id = mq.question_id AND correct_opt.is_correct = true
            WHERE mq.match_id = %s
            ORDER BY mq.order_index
            """,
            [my_side, match_id],
        )
        answers = [
            {"order_index": r[0], "my_option": r[1], "correct_option": r[2]}
            for r in cursor.fetchall()
        ]

    return {
        "status": match['status'],
        "winner_side": winner_side,
        "me": brief(participants[my_side]),
        "opponent": brief(participants[opp_side]),
        "answers": answers,
    }, None
