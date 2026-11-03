/// M03 domain model (local to the phone). No Django API call in this module.
class QuestionOption {
  final int optionId;
  final int questionId;
  final String content;
  final bool isCorrect;
  final int orderIndex;

  const QuestionOption({
    required this.optionId,
    required this.questionId,
    required this.content,
    required this.isCorrect,
    required this.orderIndex,
  });
}

class Question {
  final int questionId;
  final String content;
  final String category;
  final String difficulty;
  final List<QuestionOption> options;

  const Question({
    required this.questionId,
    required this.content,
    required this.category,
    required this.difficulty,
    required this.options,
  });
}

class MatchQuestion {
  final int orderIndex;
  final Question question;
  const MatchQuestion({required this.orderIndex, required this.question});
}

class MatchAnswer {
  final int orderIndex;
  final String side;
  final QuestionOption? selectedOption;
  int? get selectedOptionId => selectedOption?.optionId;
  final bool isCorrect;
  final int responseTimeMs;
  final DateTime answeredAt;

  MatchAnswer({
    required this.orderIndex,
    required this.side,
    required this.selectedOption,
    required this.isCorrect,
    required this.responseTimeMs,
    DateTime? answeredAt,
  }) : answeredAt = answeredAt ?? DateTime.now();
}

class MatchParticipant {
  final String side;
  String result = 'draw';
  double pointsEarned = 0;
  int correctCount = 0;
  int durationSeconds = 0;
  /// users.user_id of the logged-in player for P1; null for the BOT side.
  int? userId;
  DateTime? submittedAt;

  MatchParticipant(this.side, {this.userId});
}

class Match {
  int? localMatchId;
  final String opponentType = 'BOT';
  int currentQuestionIndex = 0;
  final String botDifficulty;
  final int questionCount;
  final int timeLimitSeconds;
  final DateTime startedAt;
  final List<MatchQuestion> questions;
  final int? playerUserId;
  late final MatchParticipant player = MatchParticipant('P1', userId: playerUserId);
  final MatchParticipant bot = MatchParticipant('P2');
  List<MatchParticipant> get participants => [player, bot];
  final Map<int, MatchAnswer> playerAnswers = {};
  final Map<int, MatchAnswer> botAnswers = {};
  DateTime? endedAt;
  String status = 'ongoing';

  Match({
    required this.botDifficulty,
    required this.questionCount,
    required this.timeLimitSeconds,
    required this.startedAt,
    required this.questions,
    this.playerUserId,
  });
}

/// Pure match rule copied in meaning from matches/services.py:calculate_result.
/// More correct answers alone DO NOT win unless all questions are correct.
String resolveMatchOutcome({
  required int questionCount,
  required int playerCorrect,
  required int botCorrect,
  required int playerSeconds,
  required int botSeconds,
}) {
  final perfectPlayer = playerCorrect == questionCount;
  final perfectBot = botCorrect == questionCount;
  if (perfectPlayer && perfectBot) {
    if (playerSeconds < botSeconds) return 'win';
    if (playerSeconds > botSeconds) return 'lose';
    return 'draw';
  }
  if (perfectPlayer) return 'win';
  if (perfectBot) return 'lose';
  return 'draw';
}
