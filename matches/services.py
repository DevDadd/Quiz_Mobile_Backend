import random
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from authentication.services import add_points, enter_match, leave_match, pick_for_match

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
        # 'draw'/0, sẽ bị finalize() ghi đè giá trị thật. submitted_at NULL = chưa nộp bài.
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


def finalize(match_id):
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
            add_points(p['user_id'], points)

        cursor.execute(
            "UPDATE matches SET status = %s, ended_at = now(), updated_at = now() WHERE match_id = %s",
            [MATCH_STATUS_FINISHED, match_id],
        )

    leave_match(match_id)


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
    """Kiểm tra deadline quá hạn và tự giải quyết (auto-submit + finalize) nếu cần.
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

        finalize(match_id)

    return get_match(match_id)
