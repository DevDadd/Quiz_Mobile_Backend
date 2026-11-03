from rest_framework.response import Response
from rest_framework.views import APIView

from practice import services


def _get_own_session(request, id):
    """Trả về (me, session, error_response). Tự nộp bài nếu phiên đã hết giờ (timeout lazy)."""
    session = services.resolve_if_expired(id)
    if not session:
        return None, None, Response({"error": "Không tìm thấy"}, status=404)
    return session['user_id'], session, None


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
        if not services.get_practice_set(id):
            return Response({"error": "Không tìm thấy bộ đề"}, status=404)
        return Response(services.get_questions(id))


class QuestionOptionsView(APIView):
    def get(self, request, question_id):
        if not services.question_exists(question_id):
            return Response({"error": "Không tìm thấy câu hỏi"}, status=404)
        return Response(services.get_options(question_id))


class PracticeSessionCreateView(APIView):
    def post(self, request):
        mode = request.data.get('mode', services.MODE_SET)
        me = request.data.get('user_id')
        try:
            me = int(me) if me is not None else None
        except (TypeError, ValueError):
            return Response({"error": "user_id không hợp lệ"}, status=400)
        if me is None:
            return Response({"error": "user_id is required"}, status=400)
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

        return Response(
            status=201,
            headers={
                "Location": f"/practice/sessions/{practice_id}/",
                "X-Practice-Id": str(practice_id),
            },
        )


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


class PracticeSubmitView(APIView):
    def post(self, request, id):
        me, session, error = _get_own_session(request, id)
        if error:
            return error

        answers = request.data if isinstance(request.data, list) else request.data.get('answers', [])
        return Response(services.submit(id, me, answers))


class PracticeGradeView(APIView):
    def post(self, request, id):
        me, session, error = _get_own_session(request, id)
        if error:
            return error
        if session['status'] == services.STATUS_ONGOING:
            return Response({"error": "Nộp bài trước khi chấm điểm"}, status=409)
        result = services.grade_session(id, me)
        if result is None:
            return Response({"error": "Không thể chấm session này"}, status=404)
        return Response(result)


class WrongQuestionRecordView(APIView):
    def post(self, request, id):
        me, session, error = _get_own_session(request, id)
        if error:
            return error
        if session['status'] == services.STATUS_ONGOING:
            return Response({"error": "Nộp bài trước khi ghi câu sai"}, status=409)
        if services.has_ungraded_answers(id):
            return Response({"error": "Chấm điểm trước khi ghi câu sai"}, status=409)
        result = services.record_session_wrong(id, me)
        if result is None:
            return Response({"error": "Không thể ghi câu sai của session này"}, status=404)
        return Response(result)


class PracticeResultView(APIView):
    def get(self, request, id):
        _, session, error = _get_own_session(request, id)
        if error:
            return error
        if session['status'] == services.STATUS_ONGOING:
            return Response({"error": "Phiên luyện tập chưa kết thúc", "status": session['status']}, status=409)
        if services.has_ungraded_answers(id):
            return Response({"error": "Chấm điểm trước khi xem kết quả"}, status=409)

        result = services.calculate_result(id)
        result["status"] = session['status']
        result["mode"] = session['mode']
        result["answers"] = services.get_result_review(id)
        return Response(result)


class WrongQuestionsView(APIView):
    def get(self, request):
        me = request.query_params.get('user_id')
        try:
            me = int(me) if me is not None else None
        except (TypeError, ValueError):
            return Response({"error": "user_id không hợp lệ"}, status=400)
        if me is None:
            return Response({"error": "user_id is required"}, status=400)
        include_mastered = request.query_params.get('include_mastered') in ('1', 'true', 'True')
        return Response(services.get_wrong_questions(me, include_mastered))
