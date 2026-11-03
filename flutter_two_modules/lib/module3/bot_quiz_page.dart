import 'dart:async';

import 'package:flutter/material.dart';

import 'bot_game_controller.dart';
import 'bot_result_page.dart';
import 'models.dart';

class BotQuizPage extends StatefulWidget {
  final BotGameController controller;
  final Match match;
  const BotQuizPage({super.key, required this.controller, required this.match});

  const BotQuizPage.showQuestions({super.key, required this.controller, required this.match});

  @override
  State<BotQuizPage> createState() => _BotQuizPageState();
}

class _BotQuizPageState extends State<BotQuizPage> {
  Timer? _timer;
  int current = 0;
  int remaining = 60;
  bool finishing = false;
  bool _dialogOpen = false;

  @override
  void initState() {
    super.initState();
    remaining = widget.controller.timeLeft(DateTime.now());
    _timer = Timer.periodic(const Duration(milliseconds: 250), (_) {
      if (!mounted || finishing) return;
      final next = widget.controller.timeLeft(DateTime.now());
      if (next != remaining) setState(() => remaining = next);
      if (next == 0) onTimeout();
    });
  }

  void choose(int order, int optionId) {
    if (finishing || remaining == 0) return;
    try {
      widget.controller.selectAnswer(order, optionId);
      setState(() {});
    } on StateError {
      onTimeout();
    }
  }

  void showQuestions(Match match) {
    if (mounted) setState(() { current = 0; match.currentQuestionIndex = 0; });
  }

  Future<void> submit() => _finish('submit');
  Future<void> onTimeout() => _finish('timeout');

  Future<void> _finish(String reason) async {
    if (finishing) return;
    setState(() => finishing = true);
    _timer?.cancel();
    if (_dialogOpen) Navigator.of(context).pop(false); // close the exit dialog first
    try {
      final result = await widget.controller.finishMatch(reason);
      if (!mounted) return;
      await showResult(result['match'] as Match, result['saved'] as bool);
    } catch (e) {
      if (!mounted) return;
      setState(() => finishing = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Lỗi: ${e.toString().replaceFirst(RegExp(r'^(Bad state|Exception): '), '')}')));
    }
  }

  Future<void> showResult(Match match, bool saved) async {
    await Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => BotResultPage.showResult(
        match: match, saved: saved, retrySave: widget.controller.retrySave),
    ));
  }

  /// Back pressed mid-match: confirm, then store the match as 'abandoned' (no score).
  Future<void> _confirmExit() async {
    if (finishing || _dialogOpen) return;
    _dialogOpen = true;
    final leave = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Thoát trận đấu?'),
        content: const Text('Trận đang diễn ra sẽ bị hủy và không được tính điểm.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Ở lại')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Thoát')),
        ],
      ),
    );
    _dialogOpen = false;
    if (!mounted || finishing || leave != true) return;
    _timer?.cancel();
    await widget.controller.abandonMatch();
    if (mounted) Navigator.of(context).pop();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final q = widget.match.questions[current];
    final selected = widget.match.playerAnswers[q.orderIndex]?.selectedOptionId;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) { if (!didPop) _confirmExit(); },
      child: Scaffold(
        appBar: AppBar(title: const Text('Thi đấu với máy')),
        body: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text('Câu ${current + 1}/${widget.match.questionCount}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                Text('${(remaining ~/ 60).toString().padLeft(2, '0')}:${(remaining % 60).toString().padLeft(2, '0')}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ]),
              const SizedBox(height: 25),
              Text(q.question.content, style: const TextStyle(fontSize: 20)),
              const SizedBox(height: 18),
              for (final option in q.question.options)
                RadioListTile<int>(
                  title: Text('${String.fromCharCode(65 + option.orderIndex)}. ${option.content}'),
                  value: option.optionId,
                  groupValue: selected,
                  onChanged: finishing || remaining == 0 ? null : (v) => choose(q.orderIndex, v!),
                ),
              const Spacer(),
              Row(children: [
                Expanded(child: OutlinedButton(
                  onPressed: current == 0 || finishing ? null : () => setState(() { current--; widget.match.currentQuestionIndex = current; }),
                  child: const Text('Câu trước'),
                )),
                const SizedBox(width: 10),
                Expanded(child: OutlinedButton(
                  onPressed: current >= widget.match.questions.length - 1 || finishing
                      ? null : () => setState(() { current++; widget.match.currentQuestionIndex = current; }),
                  child: const Text('Câu tiếp'),
                )),
              ]),
              const SizedBox(height: 10),
              FilledButton(onPressed: finishing ? null : submit,
                  child: Text(finishing ? 'Đang chấm...' : 'Nộp bài')),
            ],
          ),
        ),
      ),
    );
  }
}
