from django.db import connection
from rest_framework.response import Response
from rest_framework.views import APIView

class QuestionsView(APIView):

    def get(self, request):
        # #10 Lấy danh sách câu hỏi
        limit = int(request.query_params.get('limit', 20))
        offset = int(request.query_params.get('offset', 0))
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT question_id, content, category, difficulty FROM questions ORDER BY question_id DESC LIMIT %s OFFSET %s", [limit, offset])
            columns = [col[0] for col in cursor.description]
            questions = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            for q in questions:
                cursor.execute("SELECT option_id, content, is_correct, order_index FROM question_options WHERE question_id = %s ORDER BY order_index", [q['question_id']])
                opt_cols = [col[0] for col in cursor.description]
                q['options'] = [dict(zip(opt_cols, row)) for row in cursor.fetchall()]
                
        return Response(questions, status=200)
        
    def post(self, request):
        # #11 Thêm câu hỏi
        data = request.data
        options = data.get('options', [])
        
        # Validate đúng 1 đáp án đúng
        if sum([1 for o in options if o.get('is_correct')]) != 1:
            return Response({"error": "Phải có đúng 1 đáp án đúng"}, status=400)
            
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO questions (content, category, difficulty, created_at) VALUES (%s, %s, %s, now()) RETURNING question_id",
                [data.get('content'), data.get('category'), data.get('difficulty')]
            )
            q_id = cursor.fetchone()[0]
            
            for opt in options:
                cursor.execute(
                    "INSERT INTO question_options (question_id, content, is_correct, order_index) VALUES (%s, %s, %s, %s)",
                    [q_id, opt.get('content'), opt.get('is_correct'), opt.get('order_index')]
                )
        return Response({"question_id": q_id}, status=201)


class QuestionDetailView(APIView):

    def put(self, request, id):
        # #12 Sửa câu hỏi
        data = request.data
        options = data.get('options', [])
        
        if sum([1 for o in options if o.get('is_correct')]) != 1:
            return Response({"error": "Phải có đúng 1 đáp án đúng"}, status=400)
            
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE questions SET content=%s, category=%s, difficulty=%s WHERE question_id=%s",
                [data.get('content'), data.get('category'), data.get('difficulty'), id]
            )
            cursor.execute("DELETE FROM question_options WHERE question_id=%s", [id])
            for opt in options:
                cursor.execute(
                    "INSERT INTO question_options (question_id, content, is_correct, order_index) VALUES (%s, %s, %s, %s)",
                    [id, opt.get('content'), opt.get('is_correct'), opt.get('order_index')]
                )
        return Response({"ok": True}, status=200)

    def delete(self, request, id):
        # #13 Xóa câu hỏi (Chặn nếu đã có trong trận)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM match_questions WHERE question_id = %s LIMIT 1", [id])
            if cursor.fetchone():
                return Response({"error": "Không thể xóa câu hỏi đã được sử dụng trong trận đấu"}, status=400)
            
            cursor.execute("DELETE FROM questions WHERE question_id = %s", [id])
            
        return Response({"ok": True}, status=200)

