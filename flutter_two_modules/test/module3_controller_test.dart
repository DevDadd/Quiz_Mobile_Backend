import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:quiz_mobile_two_modules/module3/bot_game_controller.dart';
import 'package:quiz_mobile_two_modules/module3/match_dao.dart';
import 'package:quiz_mobile_two_modules/module3/models.dart';
import 'package:quiz_mobile_two_modules/module3/question_dao.dart';

class StubQuestionDAO extends QuestionDAO {
  const StubQuestionDAO();

  @override
  Future<List<Question>> pickQuestions(int count) async => List.generate(count, (i) => Question(
    questionId: i + 1,
    content: 'Câu ${i + 1}',
    category: 'Test',
    difficulty: 'easy',
    options: [
      QuestionOption(optionId: i * 2 + 1, questionId: i + 1,
        content: 'Sai', isCorrect: false, orderIndex: 0),
      QuestionOption(optionId: i * 2 + 2, questionId: i + 1,
        content: 'Đúng', isCorrect: true, orderIndex: 1),
    ],
  ));
}

class StubMatchDAO extends MatchDAO {
  const StubMatchDAO();

  @override
  Future<int> createMatch(Match match) async => 101;

  @override
  Future<bool> saveResult(Match match) async => match.status == 'finished';
}

void main() {
  test('M03 chọn 10 câu, tạo trận, trả lời, lưu và trả kết quả 1 lần', () async {
    final controller = BotGameController(
      questionDAO: const StubQuestionDAO(),
      matchDAO: const StubMatchDAO(),
      random: Random(2),
    );
    final match = await controller.startMatch('easy');
    expect(match.localMatchId, 101);
    expect(match.questions.length, 10);
    expect(match.botAnswers.length, 10);
    for (var i = 0; i < 10; i++) {
      controller.selectAnswer(i, i * 2 + 2); // correct option
    }
    final first = await controller.finishMatch('submit');
    final second = await controller.finishMatch('timeout');
    expect((first['match'] as Match).status, 'finished');
    expect((first['match'] as Match).player.correctCount, 10);
    expect((first['match'] as Match).player.result, 'win');
    expect(first['saved'], true);
    expect(identical(first, second), true); // idempotent
  });
}
