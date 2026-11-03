from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

# --- Hằng số ---
# Giá trị enum khớp đúng pg_enum trong Postgres: practice_mode_enum, practice_status_enum.

MODE_SET = 'SET'
MODE_WRONG_REVIEW = 'WRONG_REVIEW'
MODES = (MODE_SET, MODE_WRONG_REVIEW)

STATUS_ONGOING = 'ongoing'
STATUS_FINISHED = 'finished'
STATUS_ABANDONED = 'abandoned'

DEFAULT_TIME_LIMIT_SECONDS = 600
WRONG_REVIEW_QUESTION_COUNT = 10
MASTERED_STREAK = 3  # đúng liên tiếp bấy nhiêu lần khi ôn lại thì coi là đã thuộc

SESSION_COLUMNS = [
    'practice_id', 'user_id', 'mode', 'set_id', 'time_limit_seconds', 'status', 'started_at', 'ended_at',
]


def _rows(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Practice_sets
# ---------------------------------------------------------------------------

def get_practice_sets(difficulty=None):
    """Danh sách bộ đề đang dùng, lọc theo độ khó nếu có."""
    query = """
        SELECT s.set_id, s.title, s.category, s.difficulty, s.time_limit_seconds,
               (SELECT count(*) FROM practice_set_questions q WHERE q.set_id = s.set_id) AS question_count
        FROM practice_sets s
        WHERE s.is_active
    """
    params = []
    if difficulty is not None:
        query += " AND s.difficulty = %s"
        params.append(difficulty)
    query += " ORDER BY s.set_id"
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return _rows(cursor)


def get_practice_set(set_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_id, title, category, difficulty, time_limit_seconds "
            "FROM practice_sets WHERE set_id = %s AND is_active",
            [set_id],
        )
        rows = _rows(cursor)
    return rows[0] if rows else None


def get_questions(set_id):
    """Danh sách câu hỏi của một bộ đề, không kèm options."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT psq.order_index, q.question_id, q.content
            FROM practice_set_questions psq JOIN questions q ON q.question_id = psq.question_id
            WHERE psq.set_id = %s ORDER BY psq.order_index
            """,
            [set_id],
        )
        return _rows(cursor)


def question_exists(question_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM questions WHERE question_id = %s", [question_id])
        return cursor.fetchone() is not None


def get_options(question_id, cursor=None):
    """Các phương án của một câu hỏi. Không trả is_correct để client không biết đáp án."""
    def run(c):
        c.execute(
            "SELECT option_id, content, order_index FROM question_options "
            "WHERE question_id = %s ORDER BY order_index",
            [question_id],
        )
        return _rows(c)

    if cursor is not None:
        return run(cursor)
    with connection.cursor() as c:
        return run(c)


# ---------------------------------------------------------------------------
# Practice_sessions
# ---------------------------------------------------------------------------

def get_session(practice_id, for_update=False):
    query = f"SELECT {', '.join(SESSION_COLUMNS)} FROM practice_sessions WHERE practice_id = %s"
    if for_update:
        query += " FOR UPDATE"
    with connection.cursor() as cursor:
        cursor.execute(query, [practice_id])
        row = cursor.fetchone()
    return dict(zip(SESSION_COLUMNS, row)) if row else None


def time_remaining_ms(session):
    if session['status'] != STATUS_ONGOING:
        return 0
    if session['time_limit_seconds'] is None:
        return None
    deadline = session['started_at'] + timedelta(seconds=session['time_limit_seconds'])
    return max(0.0, (deadline - timezone.now()).total_seconds() * 1000)


def start_session(user_id, mode, set_id=None, time_limit_seconds=None):
    """Create a practice session and snapshot its question items."""
    if mode not in MODES:
        return None, ("mode không hợp lệ (SET hoặc WRONG_REVIEW)", 400)

    with transaction.atomic(), connection.cursor() as cursor:
        if mode == MODE_SET:
            practice_set = get_practice_set(set_id) if set_id is not None else None
            if not practice_set:
                return None, ("Không tìm thấy bộ đề", 404)
            cursor.execute(
                "SELECT order_index, question_id FROM practice_set_questions WHERE set_id = %s ORDER BY order_index",
                [set_id],
            )
            questions = cursor.fetchall()
            if not questions:
                return None, ("Bộ đề không có câu hỏi", 400)
            if time_limit_seconds is None:
                time_limit_seconds = practice_set['time_limit_seconds']
        else:
            set_id = None
            cursor.execute(
                """
                SELECT question_id FROM user_wrong_questions
                WHERE user_id = %s AND NOT is_mastered
                ORDER BY last_wrong_at DESC LIMIT %s
                """,
                [user_id, WRONG_REVIEW_QUESTION_COUNT],
            )
            questions = [(i, row[0]) for i, row in enumerate(cursor.fetchall())]
            if not questions:
                return None, ("Không có câu sai nào để ôn luyện", 400)

        if time_limit_seconds is None:
            time_limit_seconds = DEFAULT_TIME_LIMIT_SECONDS

        cursor.execute(
            "UPDATE practice_sessions SET status = %s, ended_at = now() WHERE user_id = %s AND status = %s",
            [STATUS_ABANDONED, user_id, STATUS_ONGOING],
        )
        cursor.execute(
            "INSERT INTO practice_sessions (user_id, mode, set_id, time_limit_seconds) "
            "VALUES (%s, %s, %s, %s) RETURNING practice_id",
            [user_id, mode, set_id, time_limit_seconds],
        )
        practice_id = cursor.fetchone()[0]
        cursor.executemany(
            "INSERT INTO practice_items (practice_id, order_index, question_id) VALUES (%s, %s, %s)",
            [(practice_id, order_index, question_id) for order_index, question_id in questions],
        )
    return practice_id, None


def get_session_questions(practice_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pi.order_index, q.question_id, q.content, pi.selected_option_id
            FROM practice_items pi JOIN questions q ON q.question_id = pi.question_id
            WHERE pi.practice_id = %s ORDER BY pi.order_index
            """,
            [practice_id],
        )
        questions = _rows(cursor)
        for q in questions:
            q['options'] = get_options(q['question_id'], cursor)
    return questions


def save_answers(practice_id, answers):
    """Lưu tạm đáp án đã chọn (chưa chấm). selected_option_id = None nghĩa là bỏ chọn / bỏ qua."""
    saved = 0
    with connection.cursor() as cursor:
        for a in answers:
            order_index = a.get('order_index')
            if order_index is None:
                continue
            option_id = a.get('selected_option_id')
            cursor.execute(
                """
                UPDATE practice_items pi SET
                    selected_option_id = %s,
                    response_time_ms = %s,
                    answered_at = CASE WHEN %s IS NULL THEN NULL ELSE now() END
                WHERE pi.practice_id = %s AND pi.order_index = %s
                AND (%s IS NULL OR EXISTS (
                    SELECT 1 FROM question_options o
                    WHERE o.option_id = %s AND o.question_id = pi.question_id))
                """,
                [option_id, a.get('response_time_ms'), option_id, practice_id, order_index, option_id, option_id],
            )
            saved += cursor.rowcount
    return saved


def submit(practice_id, user_id, answers=None):
    """Save final answers and close the session; grading and wrong recording are separate steps."""
    with transaction.atomic():
        session = get_session(practice_id, for_update=True)
        if not session:
            return {"submitted": False}
        if session['status'] != STATUS_ONGOING:
            return {"submitted": False, "status": session['status']}
        if answers:
            save_answers(practice_id, answers)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE practice_sessions SET status = %s, ended_at = now() WHERE practice_id = %s",
                [STATUS_FINISHED, practice_id],
            )
    return {"submitted": True, "status": STATUS_FINISHED}


def grade_session(practice_id, user_id):
    """Grade answered items that have not been graded yet."""
    processed = 0
    with transaction.atomic():
        session = get_session(practice_id, for_update=True)
        if not session or session['status'] == STATUS_ONGOING:
            return None
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT order_index, question_id, selected_option_id, response_time_ms "
                "FROM practice_items WHERE practice_id = %s "
                "AND selected_option_id IS NOT NULL AND is_correct IS NULL ORDER BY order_index",
                [practice_id],
            )
            items = cursor.fetchall()
        for order_index, question_id, selected_option_id, response_time_ms in items:
            grade(practice_id, user_id, order_index, question_id, selected_option_id, response_time_ms)
            processed += 1
    return {"graded": processed}


def record_session_wrong(practice_id, user_id):
    """Record graded items once; the event table makes this endpoint safe to retry."""
    recorded = 0
    with transaction.atomic():
        session = get_session(practice_id, for_update=True)
        if not session or session['status'] == STATUS_ONGOING:
            return None
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT order_index, question_id, is_correct FROM practice_items "
                "WHERE practice_id = %s AND selected_option_id IS NOT NULL "
                "AND is_correct IS NOT NULL ORDER BY order_index",
                [practice_id],
            )
            items = cursor.fetchall()
            for order_index, question_id, is_correct in items:
                cursor.execute(
                    "INSERT INTO practice_item_record_events (practice_id, order_index) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING RETURNING practice_id",
                    [practice_id, order_index],
                )
                if cursor.fetchone():
                    record_wrong(user_id, question_id, is_correct)
                    recorded += 1
    return {"recorded": recorded}


def has_ungraded_answers(practice_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM practice_items WHERE practice_id = %s "
            "AND selected_option_id IS NOT NULL AND is_correct IS NULL)",
            [practice_id],
        )
        return cursor.fetchone()[0]


def calculate_result(practice_id):
    """Tổng hợp kết quả: total_questions, answered_count, correct_count, total_response_time_ms (+ sai/bỏ qua)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*), count(selected_option_id), count(*) FILTER (WHERE is_correct),
                   COALESCE(sum(response_time_ms), 0)
            FROM practice_items WHERE practice_id = %s
            """,
            [practice_id],
        )
        total, answered, correct, total_response_time_ms = cursor.fetchone()
    return {
        "total_questions": total,
        "answered_count": answered,
        "correct_count": correct,
        "wrong_count": answered - correct,
        "skipped_count": total - answered,
        "total_response_time_ms": int(total_response_time_ms),
    }


def get_result_review(practice_id):
    """Từng câu: đáp án đã chọn, đáp án đúng, đúng/sai (để màn kết quả hiển thị)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pi.order_index, q.question_id, q.content, pi.selected_option_id,
                   co.option_id AS correct_option_id, pi.is_correct
            FROM practice_items pi
            JOIN questions q ON q.question_id = pi.question_id
            LEFT JOIN question_options co ON co.question_id = pi.question_id AND co.is_correct
            WHERE pi.practice_id = %s ORDER BY pi.order_index
            """,
            [practice_id],
        )
        return _rows(cursor)


def resolve_if_expired(practice_id):
    """Hết giờ mà chưa nộp thì tự nộp phần đã lưu (timeout lazy, giống matches)."""
    session = get_session(practice_id)
    if not session or session['status'] != STATUS_ONGOING or session['time_limit_seconds'] is None:
        return session
    deadline = session['started_at'] + timedelta(seconds=session['time_limit_seconds'])
    if timezone.now() >= deadline:
        submit(practice_id, session['user_id'])
        return get_session(practice_id)
    return session


# ---------------------------------------------------------------------------
# Practice_items / User_wrong_questions
# ---------------------------------------------------------------------------

def grade(practice_id, user_id, order_index, question_id, selected_option_id, response_time_ms):
    """Chấm một câu: ghi đáp án + is_correct vào practice_items, trả True nếu đúng."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE practice_items pi SET
                selected_option_id = %s,
                response_time_ms = %s,
                answered_at = COALESCE(pi.answered_at, now()),
                is_correct = COALESCE(
                    (SELECT o.is_correct FROM question_options o
                     WHERE o.option_id = %s AND o.question_id = pi.question_id), false)
            WHERE pi.practice_id = %s AND pi.order_index = %s AND pi.question_id = %s
            AND EXISTS (SELECT 1 FROM practice_sessions ps WHERE ps.practice_id = pi.practice_id AND ps.user_id = %s)
            RETURNING pi.is_correct
            """,
            [selected_option_id, response_time_ms, selected_option_id, practice_id, order_index, question_id, user_id],
        )
        row = cursor.fetchone()
    return bool(row[0]) if row else False


def record_wrong(user_id, question_id, is_correct):
    """Cập nhật sổ câu sai: sai thì +1 wrong_count và reset streak; đúng thì chỉ tăng streak
    cho câu đã có trong sổ, đủ MASTERED_STREAK lần liên tiếp thì đánh dấu đã thuộc."""
    with connection.cursor() as cursor:
        if not is_correct:
            cursor.execute(
                """
                INSERT INTO user_wrong_questions (user_id, question_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, question_id) DO UPDATE SET
                    wrong_count = user_wrong_questions.wrong_count + 1,
                    correct_streak = 0,
                    is_mastered = false,
                    last_wrong_at = now()
                """,
                [user_id, question_id],
            )
        else:
            cursor.execute(
                """
                UPDATE user_wrong_questions SET
                    correct_streak = correct_streak + 1,
                    is_mastered = (correct_streak + 1 >= %s)
                WHERE user_id = %s AND question_id = %s
                """,
                [MASTERED_STREAK, user_id, question_id],
            )


def get_wrong_questions(user_id, include_mastered=False):
    query = """
        SELECT w.question_id, q.content, w.wrong_count, w.correct_streak, w.is_mastered, w.last_wrong_at
        FROM user_wrong_questions w JOIN questions q ON q.question_id = w.question_id
        WHERE w.user_id = %s
    """
    if not include_mastered:
        query += " AND NOT w.is_mastered"
    query += " ORDER BY w.last_wrong_at DESC"
    with connection.cursor() as cursor:
        cursor.execute(query, [user_id])
        return _rows(cursor)
