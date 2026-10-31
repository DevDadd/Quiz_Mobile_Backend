from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.services import get_auth_session
from practice import services


def _unauthorized():
    return Response({"error": "Unauthorized"}, status=401)


def _get_own_session(request, id):
    """Trả về (me, session, error_response). Tự nộp bài nếu phiên đã hết giờ (timeout lazy)."""
    me, _ = get_auth_session(request)
    if not me:
        return None, None, _unauthorized()
    session = services.resolve_if_expired(id)
    if not session:
        return None, None, Response({"error": "Không tìm thấy"}, status=404)
    if session['user_id'] != me:
        return None, None, Response({"error": "Forbidden"}, status=403)
    return me, session, None


def _session_payload(session):
    return {
        "practice_id": session['practice_id'],
        "mode": session['mode'],
        "set_id": session['set_id'],
        "status": session['status'],
        "time_limit_seconds": session['time_limit_seconds'],
        "time_remaining_ms": services.time_remaining_ms(session),
        "started_at": session['started_at'],
        "ended_at": session['ended_at'],
    }


class PracticeSetsView(APIView):
    def get(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        difficulty = request.query_params.get('difficulty')
        if difficulty in (None, ''):
            difficulty = None
        else:
            try:
                difficulty = int(difficulty)
            except ValueError:
                return Response({"error": "difficulty không hợp lệ"}, status=400)
        return Response(services.get_practice_sets(difficulty))


class PracticeSetQuestionsView(APIView):
    def get(self, request, id):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        if not services.get_practice_set(id):
            return Response({"error": "Không tìm thấy bộ đề"}, status=404)
        return Response(services.get_questions(id))


class PracticeSessionCreateView(APIView):
    def post(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()

        mode = request.data.get('mode', services.MODE_SET)
        set_id = request.data.get('set_id')
        time_limit_seconds = request.data.get('time_limit_seconds')
        try:
            set_id = int(set_id) if set_id is not None else None
            time_limit_seconds = int(time_limit_seconds) if time_limit_seconds is not None else None
        except (TypeError, ValueError):
            return Response({"error": "set_id/time_limit_seconds không hợp lệ"}, status=400)
        if time_limit_seconds is not None and time_limit_seconds <= 0:
            return Response({"error": "time_limit_seconds phải lớn hơn 0"}, status=400)

        practice_id, error = services.start_session(me, mode, set_id, time_limit_seconds)
        if error:
            return Response({"error": error[0]}, status=error[1])

        session = services.get_session(practice_id)
        payload = _session_payload(session)
        payload["questions"] = services.get_session_questions(practice_id)
        return Response(payload, status=201)


class PracticeSessionDetailView(APIView):
    def get(self, request, id):
        _, session, error = _get_own_session(request, id)
        if error:
            return error
        return Response(_session_payload(session))


class PracticeQuestionsView(APIView):
    def get(self, request, id):
        _, session, error = _get_own_session(request, id)
        if error:
            return error
        return Response(services.get_session_questions(id))


class PracticeAnswersView(APIView):
    def put(self, request, id):
        _, session, error = _get_own_session(request, id)
        if error:
            return error
        if session['status'] != services.STATUS_ONGOING:
            return Response({"saved": 0, "error": "Phiên luyện tập đã kết thúc"}, status=400)

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        return Response({"saved": services.save_answers(id, answers)})


class PracticeSubmitView(APIView):
    def post(self, request, id):
        me, session, error = _get_own_session(request, id)
        if error:
            return error

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        result = services.submit(id, me, answers)
        result["answers"] = services.get_result_review(id)
        return Response(result)


class PracticeResultView(APIView):
    def get(self, request, id):
        _, session, error = _get_own_session(request, id)
        if error:
            return error
        if session['status'] == services.STATUS_ONGOING:
            return Response({"error": "Phiên luyện tập chưa kết thúc", "status": session['status']}, status=409)

        result = services.calculate_result(id)
        result["status"] = session['status']
        result["mode"] = session['mode']
        result["answers"] = services.get_result_review(id)
        return Response(result)


class WrongQuestionsView(APIView):
    def get(self, request):
        me, _ = get_auth_session(request)
        if not me:
            return _unauthorized()
        include_mastered = request.query_params.get('include_mastered') in ('1', 'true', 'True')
        return Response(services.get_wrong_questions(me, include_mastered))
