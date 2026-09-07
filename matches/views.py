import datetime as dt

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User, UserSession
from authentication.services import (
    add_points,
    enter_match,
    get_auth_session,
    is_available,
    leave_match,
)
from matches import services as match_services
from matches.models import Challenge

CHALLENGE_EXPIRY_SECONDS = match_services.CHALLENGE_EXPIRY_SECONDS
REMATCH_TIMEOUT_SECONDS = match_services.REMATCH_TIMEOUT_SECONDS
ONGOING = match_services.MATCH_STATUS_ONGOING
FINISHED = match_services.MATCH_STATUS_FINISHED

# challenge_status_enum thật không có 'cancelled', chỉ có pending/accepted/rejected/expired.
# Dùng 'expired' để biểu diễn "tự rút lại / tự hủy" theo yêu cầu #18 và nhánh rematch decline.
CHALLENGE_STATUS_SELF_CANCELLED = 'expired'


def _unauthorized():
    return Response({"error": "Unauthorized"}, status=401)


def _response_time_ms(match, now=None):
    now = now or timezone.now()
    return max(0, int((now - match['started_at']).total_seconds() * 1000))


# ---------------------------------------------------------------------------
# #14-#18 Challenge
# ---------------------------------------------------------------------------

class ChallengeCreateView(APIView):
    def post(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        opponent_id = request.data.get('opponent_id')
        if not opponent_id:
            return Response({"error": "Thiếu opponent_id"}, status=400)

        try:
            opponent_id = int(opponent_id)
        except (TypeError, ValueError):
            return Response({"error": "opponent_id không hợp lệ"}, status=400)

        if opponent_id == me:
            return Response({"error": "Không thể tự thách đấu chính mình"}, status=400)

        if not User.objects.filter(user_id=opponent_id).exists():
            return Response({"error": "Không tìm thấy đối thủ"}, status=404)

        if not is_available(opponent_id):
            return Response({"error": "Đối thủ hiện không sẵn sàng"}, status=400)

        active_since = timezone.now() - dt.timedelta(seconds=CHALLENGE_EXPIRY_SECONDS)
        already_pending = Challenge.objects.filter(
            status='pending',
            created_at__gte=active_since,
        ).filter(
            Q(challenger_id=me, opponent_id=opponent_id) | Q(challenger_id=opponent_id, opponent_id=me)
        ).exists()
        if already_pending:
            return Response({"error": "Đã có lời thách đấu đang chờ giữa hai người"}, status=400)

        now = timezone.now()
        challenge = Challenge.objects.create(
            challenger_id=me,
            opponent_id=opponent_id,
            status='pending',
            created_at=now,
            updated_at=now,
        )
        return Response({"challenge_id": challenge.challenge_id, "status": "pending"}, status=201)


class ChallengeDetailView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        try:
            c = Challenge.objects.get(challenge_id=id)
        except Challenge.DoesNotExist:
            return Response({"error": "Không tìm thấy"}, status=404)
        if me not in (c.challenger_id, c.opponent_id):
            return Response({"error": "Forbidden"}, status=403)
        return Response({"challenge_id": c.challenge_id, "status": c.status, "match_id": c.match_id})


class ChallengeAcceptView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        with transaction.atomic():
            try:
                c = Challenge.objects.select_for_update().get(challenge_id=id)
            except Challenge.DoesNotExist:
                return Response({"error": "Không tìm thấy"}, status=404)

            if c.opponent_id != me:
                return Response({"error": "Forbidden"}, status=403)

            if c.status == 'accepted':
                return Response({"match_id": c.match_id})
            if c.status != 'pending':
                return Response({"error": "Lời thách đấu không còn hiệu lực"}, status=400)
            if timezone.now() - c.created_at > dt.timedelta(seconds=CHALLENGE_EXPIRY_SECONDS):
                return Response({"error": "Lời thách đấu đã hết hạn"}, status=400)

            sessions = list(UserSession.objects.select_for_update().filter(
                user_id__in=[c.challenger_id, c.opponent_id]
            ))
            if any(s.current_match_id is not None for s in sessions):
                return Response({"error": "Một trong hai người đã ở trong trận khác"}, status=409)

            match_id = match_services.create_match(c.challenger_id, c.opponent_id)
            enter_match([c.challenger_id, c.opponent_id], match_id)

            c.status = 'accepted'
            c.match_id = match_id
            c.responded_at = timezone.now()
            c.updated_at = timezone.now()
            c.save()

        return Response({"match_id": match_id})


class ChallengeRejectView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        with transaction.atomic():
            try:
                c = Challenge.objects.select_for_update().get(challenge_id=id)
            except Challenge.DoesNotExist:
                return Response({"error": "Không tìm thấy"}, status=404)
            if c.opponent_id != me:
                return Response({"error": "Forbidden"}, status=403)
            if c.status == 'pending':
                c.status = 'rejected'
                c.responded_at = timezone.now()
                c.updated_at = timezone.now()
                c.save()
        return Response({"ok": True})


class ChallengeCancelView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        with transaction.atomic():
            try:
                c = Challenge.objects.select_for_update().get(challenge_id=id)
            except Challenge.DoesNotExist:
                return Response({"error": "Không tìm thấy"}, status=404)
            if c.challenger_id != me:
                return Response({"error": "Forbidden"}, status=403)
            if c.status == 'pending':
                c.status = CHALLENGE_STATUS_SELF_CANCELLED
                c.responded_at = timezone.now()
                c.updated_at = timezone.now()
                c.save()
        return Response({"ok": True})


# ---------------------------------------------------------------------------
# #19 Bot match
# ---------------------------------------------------------------------------

class MatchBotView(APIView):
    def post(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        bot_difficulty = request.data.get('bot_difficulty', 'medium')
        if bot_difficulty not in match_services.BOT_PROFILES:
            return Response({"error": "bot_difficulty không hợp lệ"}, status=400)

        try:
            question_count = int(request.data.get('question_count', match_services.DEFAULT_QUESTION_COUNT))
            time_limit_seconds = int(request.data.get('time_limit_seconds', match_services.DEFAULT_TIME_LIMIT_SECONDS))
        except (TypeError, ValueError):
            return Response({"error": "question_count/time_limit_seconds không hợp lệ"}, status=400)

        with transaction.atomic():
            session = UserSession.objects.select_for_update().get(user_id=me)
            if session.current_match_id is not None:
                return Response({"error": "Bạn đang ở trong một trận khác"}, status=409)

            match_id = match_services.create_match(
                me, None, question_count, time_limit_seconds,
                opponent_type='BOT',
                bot_difficulty_db=match_services.BOT_DIFFICULTY_DB[bot_difficulty],
            )
            enter_match([me], match_id)
            match_services.generate_bot_answers(
                match_id, match_services.SIDE_P2, bot_difficulty, question_count, time_limit_seconds
            )

        return Response({"match_id": match_id}, status=201)


# ---------------------------------------------------------------------------
# #20-#26 Match lifecycle
# ---------------------------------------------------------------------------

def _time_remaining_ms(match):
    if match['status'] != ONGOING:
        return 0
    deadline = match['started_at'] + dt.timedelta(seconds=match['time_limit_seconds'])
    return max(0.0, (deadline - timezone.now()).total_seconds() * 1000)


class MatchDetailView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        match = match_services.resolve_if_expired(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        participants = match_services.get_participants(id)
        opp_side = next(s for s in participants if s != my_side)
        opp = participants[opp_side]

        if opp['user_id'] is None:
            opponent_info = {"name": "BOT", "total_score": None}
        else:
            opp_user = User.objects.get(user_id=opp['user_id'])
            opponent_info = {"name": opp_user.display_name, "total_score": float(opp_user.total_score)}

        return Response({
            "match_id": match['match_id'],
            "opponent_type": match['opponent_type'],
            "my_side": my_side,
            "opponent": opponent_info,
            "question_count": match['question_count'],
            "time_limit_seconds": match['time_limit_seconds'],
            "status": match['status'],
            "time_remaining_ms": _time_remaining_ms(match),
        })


class MatchQuestionsView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        result = []
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mq.order_index, q.question_id, q.content
                FROM match_questions mq JOIN questions q ON q.question_id = mq.question_id
                WHERE mq.match_id = %s ORDER BY mq.order_index
                """,
                [id],
            )
            rows = cursor.fetchall()
            for order_index, question_id, content in rows:
                cursor.execute(
                    "SELECT option_id, content, order_index FROM question_options WHERE question_id = %s ORDER BY order_index",
                    [question_id],
                )
                options = [
                    {"option_id": o[0], "content": o[1], "order_index": o[2]}
                    for o in cursor.fetchall()
                ]
                result.append({
                    "order_index": order_index,
                    "question_id": question_id,
                    "content": content,
                    "options": options,
                })

        return Response(result)


class MatchStateView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        match = match_services.resolve_if_expired(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)

        since = request.query_params.get('since')
        if since:
            try:
                since_dt = dt.datetime.fromtimestamp(float(since) / 1000.0, tz=dt.timezone.utc)
                if match['updated_at'] <= since_dt:
                    return Response(status=304)
            except (ValueError, TypeError, OSError):
                pass

        participants = match_services.get_participants(id)
        opp_side = next(s for s in participants if s != my_side)
        me_p = participants[my_side]
        opp_p = participants[opp_side]

        hide_bot = (
            match['opponent_type'] == 'BOT'
            and me_p['submitted_at'] is None
            and match['status'] == ONGOING
        )
        if hide_bot:
            opponent_submitted = False
            opponent_answered = 0
        else:
            opponent_submitted = opp_p['submitted_at'] is not None
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM match_answers WHERE match_id = %s AND side = %s AND selected_option_id IS NOT NULL",
                    [id, opp_side],
                )
                opponent_answered = cursor.fetchone()[0]

        return Response({
            "status": match['status'],
            "updated_at": match['updated_at'],
            "time_remaining_ms": _time_remaining_ms(match),
            "opponent_submitted": opponent_submitted,
            "opponent_answered": opponent_answered,
            "me_submitted": me_p['submitted_at'] is not None,
        })


class MatchAnswersView(APIView):
    def put(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        match = match_services.resolve_if_expired(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)
        if match['status'] != ONGOING:
            return Response({"saved": 0, "error": "Trận đã kết thúc"}, status=400)

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        response_time_ms = _response_time_ms(match)
        n = 0
        with connection.cursor() as cursor:
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
                    [id, order_index, my_side, a.get('selected_option_id'), response_time_ms],
                )
                n += 1

        return Response({"saved": n})


class MatchSubmitView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        with transaction.atomic():
            match = match_services.get_match(id, for_update=True)
            if not match:
                return Response({"error": "Không tìm thấy"}, status=404)

            if match['status'] == ONGOING and timezone.now() >= match['started_at'] + dt.timedelta(seconds=match['time_limit_seconds']):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT side FROM match_participants WHERE match_id = %s AND submitted_at IS NULL",
                        [id],
                    )
                    for side in [r[0] for r in cursor.fetchall()]:
                        match_services._auto_submit_side(cursor, id, side, match['time_limit_seconds'])
                match_services.finalize(id)
                match = match_services.get_match(id)

            participants = match_services.get_participants(id)
            me_p = participants[my_side]

            if match['status'] != ONGOING or me_p['submitted_at'] is not None:
                return Response({
                    "submitted_at": me_p['submitted_at'] or match['updated_at'],
                    "correct_count": me_p['correct_count'],
                    "duration_seconds": me_p['duration_seconds'],
                    "waiting_opponent": match['status'] == ONGOING,
                })

            answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
            response_time_ms = _response_time_ms(match)
            with connection.cursor() as cursor:
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
                        [id, order_index, my_side, a.get('selected_option_id'), response_time_ms],
                    )

                cursor.execute(
                    """
                    UPDATE match_answers a SET is_correct = COALESCE(o.is_correct, false)
                    FROM question_options o
                    WHERE o.option_id = a.selected_option_id
                    AND a.match_id = %s AND a.side = %s
                    """,
                    [id, my_side],
                )

                duration_seconds = int((timezone.now() - match['started_at']).total_seconds())
                cursor.execute(
                    """
                    UPDATE match_participants SET
                        correct_count = (SELECT count(*) FROM match_answers WHERE match_id = %s AND side = %s AND is_correct),
                        duration_seconds = %s,
                        submitted_at = now()
                    WHERE match_id = %s AND side = %s
                    """,
                    [id, my_side, duration_seconds, id, my_side],
                )
                cursor.execute("UPDATE matches SET updated_at = now() WHERE match_id = %s", [id])

                cursor.execute(
                    "SELECT count(*) FROM match_participants WHERE match_id = %s AND submitted_at IS NULL",
                    [id],
                )
                remaining = cursor.fetchone()[0]

            if remaining == 0:
                match_services.finalize(id)

            participants = match_services.get_participants(id)
            me_p = participants[my_side]

            return Response({
                "submitted_at": me_p['submitted_at'],
                "correct_count": me_p['correct_count'],
                "duration_seconds": me_p['duration_seconds'],
                "waiting_opponent": remaining > 0,
            })


class MatchResultView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        my_side = match_services.my_side_in_match(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        match = match_services.resolve_if_expired(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)
        if match['status'] != FINISHED:
            return Response({"error": "Trận chưa kết thúc", "status": match['status']}, status=409)

        participants = match_services.get_participants(id)
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
                [my_side, id],
            )
            answers = [
                {"order_index": r[0], "my_option": r[1], "correct_option": r[2]}
                for r in cursor.fetchall()
            ]

        return Response({
            "status": match['status'],
            "winner_side": winner_side,
            "me": brief(participants[my_side]),
            "opponent": brief(participants[opp_side]),
            "answers": answers,
        })


class MatchQuitView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        with transaction.atomic():
            match = match_services.get_match(id, for_update=True)
            if not match:
                return Response({"error": "Không tìm thấy"}, status=404)

            my_side = match_services.my_side_in_match(id, me)
            if not my_side:
                return Response({"error": "Forbidden"}, status=403)

            if match['status'] != ONGOING:
                return Response({"ok": True})

            participants = match_services.get_participants(id)
            opp_side = next(s for s in participants if s != my_side)
            me_p = participants[my_side]

            duration_seconds = me_p['duration_seconds']
            if me_p['submitted_at'] is None:
                duration_seconds = int((timezone.now() - match['started_at']).total_seconds())

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE match_participants
                    SET result = 'lose', points_earned = 0.0, duration_seconds = %s, submitted_at = COALESCE(submitted_at, now())
                    WHERE match_id = %s AND side = %s
                    """,
                    [duration_seconds, id, my_side],
                )
                cursor.execute(
                    """
                    UPDATE match_participants
                    SET result = 'win', points_earned = 1.0, submitted_at = COALESCE(submitted_at, now())
                    WHERE match_id = %s AND side = %s
                    """,
                    [id, opp_side],
                )
                cursor.execute(
                    "UPDATE matches SET status = %s, ended_at = now(), updated_at = now() WHERE match_id = %s",
                    [FINISHED, id],
                )

            add_points(participants[opp_side]['user_id'], 1.0)
            leave_match(id)

        return Response({"ok": True})


# ---------------------------------------------------------------------------
# #27-#28 Rematch
# ---------------------------------------------------------------------------

class MatchRematchView(APIView):
    def _opponent(self, match_id, me):
        my_side = match_services.my_side_in_match(match_id, me)
        if not my_side:
            return None, None, None
        participants = match_services.get_participants(match_id)
        opp_side = next(s for s in participants if s != my_side)
        return my_side, opp_side, participants[opp_side]['user_id']

    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        match = match_services.get_match(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)
        if match['opponent_type'] != 'HUMAN':
            return Response({"error": "Không thể rematch với bot"}, status=400)
        if match['status'] != FINISHED:
            return Response({"error": "Trận chưa kết thúc"}, status=400)

        my_side, opp_side, other_id = self._opponent(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)

        accept = bool(request.data.get('accept'))
        end_ref = match['ended_at'] or match['updated_at']

        with transaction.atomic():
            pending = Challenge.objects.select_for_update().filter(
                status='pending',
                created_at__gte=end_ref,
            ).filter(
                Q(challenger_id=me, opponent_id=other_id) | Q(challenger_id=other_id, opponent_id=me)
            ).order_by('-created_at').first()

            now = timezone.now()

            if accept:
                if pending is None:
                    Challenge.objects.create(
                        challenger_id=me, opponent_id=other_id,
                        status='pending', created_at=now, updated_at=now,
                    )
                    return Response({"state": "waiting"})

                if pending.challenger_id == other_id:
                    new_match_id = match_services.create_match(pending.challenger_id, pending.opponent_id)
                    enter_match([pending.challenger_id, pending.opponent_id], new_match_id)
                    pending.match_id = new_match_id
                    pending.status = 'accepted'
                    pending.responded_at = now
                    pending.updated_at = now
                    pending.save()
                    return Response({"state": "started", "match_id": new_match_id})

                return Response({"state": "waiting"})

            if pending is not None:
                pending.status = 'rejected' if pending.challenger_id == other_id else CHALLENGE_STATUS_SELF_CANCELLED
                pending.responded_at = now
                pending.updated_at = now
                pending.save()
            else:
                Challenge.objects.create(
                    challenger_id=other_id, opponent_id=me,
                    status='rejected', created_at=now, responded_at=now, updated_at=now,
                )
            UserSession.objects.filter(user_id=me).update(
                current_match_id=None, status='idle', updated_at=now
            )
            return Response({"state": "declined"})

    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        match = match_services.get_match(id)
        if not match:
            return Response({"error": "Không tìm thấy"}, status=404)
        if match['status'] != FINISHED:
            return Response({"error": "Trận chưa kết thúc"}, status=400)

        my_side, opp_side, other_id = self._opponent(id, me)
        if not my_side:
            return Response({"error": "Forbidden"}, status=403)
        if other_id is None:
            return Response({"state": "timeout"})

        end_ref = match['ended_at'] or match['updated_at']
        pending = Challenge.objects.filter(
            created_at__gte=end_ref,
        ).filter(
            Q(challenger_id=me, opponent_id=other_id) | Q(challenger_id=other_id, opponent_id=me)
        ).order_by('-updated_at').first()

        if pending is None:
            elapsed = (timezone.now() - end_ref).total_seconds()
            state = 'timeout' if elapsed > REMATCH_TIMEOUT_SECONDS else 'waiting'
            return Response({"state": state})

        if pending.status == 'pending':
            state = 'waiting' if pending.challenger_id == me else 'asked'
            return Response({"state": state})
        if pending.status == 'accepted':
            return Response({"state": "started", "match_id": pending.match_id})
        if pending.status in ('rejected', CHALLENGE_STATUS_SELF_CANCELLED):
            return Response({"state": "declined"})
        return Response({"state": "timeout"})
