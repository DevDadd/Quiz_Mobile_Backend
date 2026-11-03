import 'dart:math';

import 'match_dao.dart';
import 'models.dart';
import 'question_dao.dart';

/// Handles the complete M03 match on-device, with no HTTP/Django calls.
class BotGameController {
  final QuestionDAO questionDAO;
  final MatchDAO matchDAO;
  final Random random;

  BotGameController({QuestionDAO? questionDAO, MatchDAO? matchDAO, Random? random})
      : questionDAO = questionDAO ?? const QuestionDAO(),
        matchDAO = matchDAO ?? const MatchDAO(),
        random = random ?? Random();

  Match? currentMatch;
  Future<Map<String, dynamic>>? _finishFuture;

  static const Map<String, double> botAccuracy = {
    'easy': 0.55,
    'medium': 0.75,
    'hard': 0.92,
  };
  static const Map<String, List<double>> botDurationRange = {
    'easy': [0.60, 0.95],
    'medium': [0.40, 0.80],
    'hard': [0.25, 0.60],
  };

  Future<Match> startMatch(String difficulty, {
    int questionCount = 10,
    int timeLimitSeconds = 60,
  }) async {
    if (!botAccuracy.containsKey(difficulty)) {
      throw ArgumentError.value(difficulty, 'difficulty', 'easy/medium/hard');
    }
    if (questionCount < 1 || timeLimitSeconds < 1) {
      throw ArgumentError('questionCount / timeLimitSeconds must be positive.');
    }
    final questions = await questionDAO.pickQuestions(questionCount);
    final match = Match(
      botDifficulty: difficulty,
      questionCount: questionCount,
      timeLimitSeconds: timeLimitSeconds,
      startedAt: DateTime.now(),
      questions: [
        for (var i = 0; i < questions.length; i++)
          MatchQuestion(orderIndex: i, question: questions[i]),
      ],
    );
    generateBot(match);
    match.localMatchId = await matchDAO.createMatch(match);
    currentMatch = match;
    _finishFuture = null;
    return match;
  }

  /// Generate P2's answers once (like generate_bot_answers in Django backend).
  void generateBot(Match match) {
    final accuracy = botAccuracy[match.botDifficulty]!;
    final range = botDurationRange[match.botDifficulty]!;
    for (final mq in match.questions) {
      final correct = mq.question.options.where((o) => o.isCorrect).toList();
      final wrong = mq.question.options.where((o) => !o.isCorrect).toList();
      final chooseCorrect = random.nextDouble() < accuracy;
      final pool = chooseCorrect || wrong.isEmpty ? correct : wrong;
      final picked = pool[random.nextInt(pool.length)];
      match.botAnswers[mq.orderIndex] = MatchAnswer(
        orderIndex: mq.orderIndex,
        side: 'P2',
        selectedOption: picked,
        isCorrect: picked.isCorrect,
        responseTimeMs: 500 + random.nextInt(3501),
      );
    }
    match.bot.correctCount = match.botAnswers.values.where((a) => a.isCorrect).length;
    final fraction = range[0] + random.nextDouble() * (range[1] - range[0]);
    match.bot.durationSeconds = max(1, (match.timeLimitSeconds * fraction).round());
  }

  /// Equivalent to BotQuizPage -> BotGameController.selectAnswer().
  void selectAnswer(int orderIndex, int optionId) {
    final match = currentMatch;
    if (match == null || match.status != 'ongoing' || timeLeft(DateTime.now()) <= 0) {
      throw StateError('Trận đã kết thúc hoặc hết thời gian.');
    }
    final qMatches = match.questions.where((q) => q.orderIndex == orderIndex).toList();
    if (qMatches.isEmpty) throw ArgumentError('Sai thứ tự câu hỏi.');
    final mq = qMatches.first;
    final optionMatches = mq.question.options.where((o) => o.optionId == optionId).toList();
    if (optionMatches.isEmpty) throw ArgumentError('Đáp án không thuộc câu hỏi này.');
    final chosen = optionMatches.first;
    final elapsed = DateTime.now().difference(match.startedAt).inMilliseconds;
    match.playerAnswers[orderIndex] = MatchAnswer(
      orderIndex: orderIndex,
      side: 'P1',
      selectedOption: chosen,
      isCorrect: chosen.isCorrect,
      responseTimeMs: max(0, elapsed),
    );
  }

  int timeLeft(DateTime now) {
    final match = currentMatch;
    if (match == null || match.status != 'ongoing') return 0;
    final end = match.startedAt.add(Duration(seconds: match.timeLimitSeconds));
    return max(0, (end.difference(now).inMilliseconds / 1000).ceil());
  }

  /// Idempotent: simultaneous Submit and timer expiry cannot score twice.
  Future<Map<String, dynamic>> finishMatch(String reason) {
    if (reason != 'submit' && reason != 'timeout') {
      throw ArgumentError.value(reason, 'reason');
    }
    return _finishFuture ??= _finishMatch(reason);
  }

  Future<Map<String, dynamic>> _finishMatch(String reason) async {
    final match = currentMatch;
    if (match == null) throw StateError('Chưa có trận đấu.');
    final elapsed = DateTime.now().difference(match.startedAt).inMilliseconds;
    match.player.durationSeconds = reason == 'timeout'
        ? match.timeLimitSeconds
        : min(match.timeLimitSeconds, max(1, (elapsed / 1000).ceil()));
    match.player.correctCount = match.playerAnswers.values.where((a) => a.isCorrect).length;
    evaluateOutcome(match);
    match.endedAt = DateTime.now();
    match.status = 'finished';
    final saved = await matchDAO.saveResult(match);
    return {'match': match, 'saved': saved};
  }

  void evaluateOutcome(Match match) {
    final playerResult = resolveMatchOutcome(
      questionCount: match.questionCount,
      playerCorrect: match.player.correctCount,
      botCorrect: match.bot.correctCount,
      playerSeconds: match.player.durationSeconds,
      botSeconds: match.bot.durationSeconds,
    );
    match.player.result = playerResult;
    match.bot.result = playerResult == 'win'
        ? 'lose'
        : (playerResult == 'lose' ? 'win' : 'draw');
    match.player.pointsEarned = playerResult == 'win' ? 1.0 : (playerResult == 'draw' ? 0.5 : 0.0);
    match.bot.pointsEarned = match.bot.result == 'win' ? 1.0 : (match.bot.result == 'draw' ? 0.5 : 0.0);
  }
}
