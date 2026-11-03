import 'package:flutter/material.dart';

import 'models.dart';

class BotResultPage extends StatelessWidget {
  final Match match;
  final bool saved;

  const BotResultPage({super.key, required this.match, required this.saved});

  /// A named constructor matches the showResult(match, saved) message in M03.
  const BotResultPage.showResult({super.key, required this.match, required this.saved});

  void backToSetup(BuildContext context) => Navigator.of(context).pop();

  @override
  Widget build(BuildContext context) {
    final outcome = switch (match.player.result) {
      'win' => 'THẮNG', 'lose' => 'THUA', _ => 'HÒA',
    };
    return Scaffold(
      appBar: AppBar(title: const Text('Kết quả ván đấu'), automaticallyImplyLeading: false),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(outcome, textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          Text('Bạn: ${match.player.correctCount}/${match.questionCount}  •  '
              '${match.player.durationSeconds} giây  •  +${match.player.pointsEarned} điểm'),
          Text('BOT: ${match.bot.correctCount}/${match.questionCount}  •  '
              '${match.bot.durationSeconds} giây  •  +${match.bot.pointsEarned} điểm'),
          const SizedBox(height: 24),
          Text(saved ? 'Đã lưu kết quả trên thiết bị.' : 'Chưa lưu được kết quả trên thiết bị.'),
          const Text('Không cộng điểm vào BXH trực tuyến.'),
          const SizedBox(height: 24),
          FilledButton(onPressed: () => backToSetup(context),
            child: const Text('Về chọn độ khó')),
        ]),
      ),
    );
  }
}
