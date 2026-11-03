import 'local_database.dart';
import 'models.dart';

/// Follows the QuestionDAO role shown in the user's M03 class diagram.
class QuestionDAO {
  const QuestionDAO();

  Future<List<Question>> pickQuestions(int count) async {
    if (count <= 0) throw ArgumentError.value(count, 'count');
    final db = await LocalDatabase.instance.database;
    final rows = await db.rawQuery(
      'SELECT question_id, content, category, difficulty '
      'FROM questions ORDER BY RANDOM() LIMIT ?',
      [count],
    );
    final questions = <Question>[];
    for (final row in rows) {
      final questionId = row['question_id'] as int;
      final optionRows = await db.query(
        'question_options',
        where: 'question_id = ?',
        whereArgs: [questionId],
        orderBy: 'order_index ASC',
      );
      questions.add(Question(
        questionId: questionId,
        content: row['content'] as String,
        category: row['category'] as String,
        difficulty: row['difficulty'] as String,
        options: optionRows.map((option) => QuestionOption(
          optionId: option['option_id'] as int,
          questionId: questionId,
          content: option['content'] as String,
          isCorrect: option['is_correct'] == 1,
          orderIndex: option['order_index'] as int,
        )).toList(growable: false),
      ));
    }
    // Fail closed for an invalid question bank; 10 questions are required by demo.
    if (questions.length < count ||
        questions.any((q) => q.options.length < 2 ||
            q.options.where((o) => o.isCorrect).length != 1)) {
      throw StateError('Không đủ câu hỏi hợp lệ để tạo trận ($count câu).');
    }
    return questions;
  }
}
