import 'package:flutter/material.dart';

import 'bot_game_controller.dart';
import 'bot_quiz_page.dart';

class BotSetupPage extends StatefulWidget {
  final BotGameController controller;
  const BotSetupPage({super.key, required this.controller});

  @override
  State<BotSetupPage> createState() => _BotSetupPageState();
}

class _BotSetupPageState extends State<BotSetupPage> {
  String difficulty = 'medium';
  bool loading = false;

  Future<void> start() async {
    if (loading) return;
    setState(() => loading = true);
    try {
      final match = await widget.controller.startMatch(difficulty);
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => BotQuizPage.showQuestions(controller: widget.controller, match: match),
      ));
    } catch (e) {
      if (mounted) showError(e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  void showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(message.replaceFirst(RegExp(r'^(Bad state|Exception): '), '')),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Thi đấu với máy')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('CHỌN ĐỘ KHÓ BOT', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            for (final option in <String, String>{
              'easy': 'Dễ', 'medium': 'Trung bình', 'hard': 'Khó',
            }.entries)
              RadioListTile<String>(
                title: Text(option.value),
                value: option.key,
                groupValue: difficulty,
                onChanged: loading ? null : (v) => setState(() => difficulty = v!),
              ),
            const SizedBox(height: 20),
            const Text('Số câu: 10      Thời gian: 60 giây'),
            const SizedBox(height: 10),
            const Text('Bộ câu hỏi: có sẵn trên thiết bị. Điểm không cộng vào BXH online.'),
            const SizedBox(height: 25),
            FilledButton(
              onPressed: loading ? null : start,
              child: Text(loading ? 'Đang chuẩn bị...' : 'Bắt đầu'),
            ),
          ],
        ),
      ),
    );
  }
}
