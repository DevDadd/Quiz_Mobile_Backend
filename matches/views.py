import datetime as dt

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import User, UserSession
from authentication.services import (
    update_score,
    set_busy,
    get_auth_session,
    set_idle,
)
from matches import services as match_services
from matches.models import Challenge

REMATCH_TIMEOUT_SECONDS = match_services.REMATCH_TIMEOUT_SECONDS
ONGOING = match_services.MATCH_STATUS_ONGOING
FINISHED = match_services.MATCH_STATUS_FINISHED

# challenge_status_enum thật không có 'cancelled', chỉ có pending/accepted/rejected/expired.
# Dùng 'expired' để biểu diễn "tự rút lại / tự hủy" theo yêu cầu #18 và nhánh rematch decline.
CHALLENGE_STATUS_SELF_CANCELLED = 'expired'


def _unauthorized():
    return Response({"error": "Unauthorized"}, status=401)


def _error_response(error):
    """error = (thông báo, http_status[, dữ liệu thêm]) trả về từ matches.services."""
    body = {"error": error[0]}
    if len(error) > 2:
        body.update(error[2])
    return Response(body, status=error[1])


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

        result, error = match_services.send_challenge(me, opponent_id)
        if error:
            return _error_response(error)
        return Response(result, status=201)


class ChallengePendingView(APIView):
    def get(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        return Response(match_services.get_pending_challenge(me))


class ChallengeDetailView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        result, error = match_services.get_challenge(id, me)
        if error:
            return _error_response(error)
        return Response(result)


class ChallengeAcceptView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        match_id, error = match_services.accept_challenge(id, me)
        if error:
            return _error_response(error)
        return Response({"match_id": match_id})


class ChallengeRejectView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        error = match_services.reject_challenge(id, me)
        if error:
            return _error_response(error)
        return Response({"ok": True})


class ChallengeCancelView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        error = match_services.cancel_challenge(id, me)
        if error:
            return _error_response(error)
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
            set_busy([me], match_id)
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

        if not match_services.my_side_in_match(id, me):
            return Response({"error": "Forbidden"}, status=403)
        return Response(match_services.get_questions(id))


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

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        saved, error = match_services.save_answers(id, me, answers)
        if error:
            return _error_response(error)
        return Response({"saved": saved})


class MatchSubmitView(APIView):
    def post(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        result, error = match_services.submit(id, me, answers)
        if error:
            return _error_response(error)
        return Response(result)


class MatchResultView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        result, error = match_services.get_result(id, me)
        if error:
            return _error_response(error)
        return Response(result)


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

            update_score(participants[opp_side]['user_id'], 1.0)
            set_idle(id)

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
                    set_busy([pending.challenger_id, pending.opponent_id], new_match_id)
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
