import 'package:sqflite/sqflite.dart';

import 'local_database.dart';
import 'models.dart';

/// Local persistence layer for M03, never writes to Django / leaderboard.
class MatchDAO {
  const MatchDAO();

  Future<int> createMatch(Match match) async {
    final db = await LocalDatabase.instance.database;
    return db.transaction((txn) async {
      final id = await txn.insert('matches', {
        'bot_difficulty': match.botDifficulty,
        'question_count': match.questionCount,
        'time_limit_seconds': match.timeLimitSeconds,
        'status': match.status,
        'started_at': match.startedAt.toUtc().toIso8601String(),
        'ended_at': null,
      });
      for (final mq in match.questions) {
        await txn.insert('match_questions', {
          'match_id': id,
          'order_index': mq.orderIndex,
          'question_id': mq.question.questionId,
        });
      }
      for (final side in ['P1', 'P2']) {
        await txn.insert('match_participants', {
          'match_id': id,
          'side': side,
          'result': 'draw',
          'points_earned': 0.0,
          'correct_count': 0,
          'duration_seconds': 0,
        });
      }
      return id;
    });
  }

  /// Saves both sides and their per-question answers atomically.
  /// Returns false if device storage fails; result screen can still be shown.
  Future<bool> saveResult(Match match) async {
    final id = match.localMatchId;
    if (id == null || match.endedAt == null || match.status != 'finished') {
      return false;
    }
    try {
      final db = await LocalDatabase.instance.database;
      await db.transaction((txn) async {
        final count = await txn.update('matches', {
          'status': 'finished',
          'ended_at': match.endedAt!.toUtc().toIso8601String(),
        }, where: 'match_id = ?', whereArgs: [id]);
        if (count != 1) throw StateError('Trận đấu không tồn tại.');

        for (final participant in [match.player, match.bot]) {
          await txn.update('match_participants', {
            'result': participant.result,
            'points_earned': participant.pointsEarned,
            'correct_count': participant.correctCount,
            'duration_seconds': participant.durationSeconds,
          }, where: 'match_id = ? AND side = ?', whereArgs: [id, participant.side]);
        }
        for (final mq in match.questions) {
          for (final side in ['P1', 'P2']) {
            final answer = side == 'P1'
                ? match.playerAnswers[mq.orderIndex]
                : match.botAnswers[mq.orderIndex];
            await txn.insert('match_answers', {
              'match_id': id,
              'order_index': mq.orderIndex,
              'side': side,
              'selected_option_id': answer?.selectedOptionId,
              'is_correct': answer?.isCorrect == true ? 1 : 0,
              'response_time_ms': answer?.responseTimeMs ?? 0,
            }, conflictAlgorithm: ConflictAlgorithm.replace);
          }
        }
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Returns one locally saved match; useful for history/debugging.
  Future<Match?> getMatch(int id) async {
    final db = await LocalDatabase.instance.database;
    final rows = await db.query('matches', where: 'match_id = ?', whereArgs: [id], limit: 1);
    if (rows.isEmpty) return null;
    final row = rows.single;
    final mqRows = await db.query('match_questions', where: 'match_id = ?',
        whereArgs: [id], orderBy: 'order_index');
    final items = <MatchQuestion>[];
    for (final mqRow in mqRows) {
      final qid = mqRow['question_id'] as int;
      final qRow = (await db.query('questions', where: 'question_id = ?',
          whereArgs: [qid], limit: 1)).single;
      final options = await db.query('question_options',
          where: 'question_id = ?', whereArgs: [qid], orderBy: 'order_index');
      items.add(MatchQuestion(
        orderIndex: mqRow['order_index'] as int,
        question: Question(
          questionId: qid,
          content: qRow['content'] as String,
          category: qRow['category'] as String,
          difficulty: qRow['difficulty'] as String,
          options: options.map((o) => QuestionOption(
            optionId: o['option_id'] as int,
            questionId: qid,
            content: o['content'] as String,
            isCorrect: o['is_correct'] == 1,
            orderIndex: o['order_index'] as int,
          )).toList(),
        ),
      ));
    }
    final match = Match(
      botDifficulty: row['bot_difficulty'] as String,
      questionCount: row['question_count'] as int,
      timeLimitSeconds: row['time_limit_seconds'] as int,
      startedAt: DateTime.parse(row['started_at'] as String),
      questions: items,
    );
    match.localMatchId = id;
    match.status = row['status'] as String;
    if (row['ended_at'] != null) {
      match.endedAt = DateTime.parse(row['ended_at'] as String);
    }
    final participants = await db.query('match_participants',
        where: 'match_id = ?', whereArgs: [id]);
    for (final p in participants) {
      final part = p['side'] == 'P1' ? match.player : match.bot;
      part.result = p['result'] as String;
      part.pointsEarned = (p['points_earned'] as num).toDouble();
      part.correctCount = p['correct_count'] as int;
      part.durationSeconds = p['duration_seconds'] as int;
    }
    final answers = await db.query('match_answers',
        where: 'match_id = ?', whereArgs: [id]);
    for (final a in answers) {
      final answer = MatchAnswer(
        orderIndex: a['order_index'] as int,
        side: a['side'] as String,
        selectedOption: a['selected_option_id'] == null
            ? null
            : match.questions
                .firstWhere((mq) => mq.orderIndex == a['order_index'])
                .question.options
                .firstWhere((opt) => opt.optionId == a['selected_option_id']),
        isCorrect: a['is_correct'] == 1,
        responseTimeMs: a['response_time_ms'] as int,
      );
      (answer.side == 'P1' ? match.playerAnswers : match.botAnswers)[answer.orderIndex] = answer;
    }
    return match;
  }
}
