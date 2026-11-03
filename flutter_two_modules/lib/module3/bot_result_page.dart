import 'package:flutter/material.dart';

import 'models.dart';

class BotResultPage extends StatefulWidget {
  final Match match;
  final bool saved;
  /// Called when the first save failed; returns true when the retry succeeds.
  final Future<bool> Function()? retrySave;

  const BotResultPage({super.key, required this.match, required this.saved, this.retrySave});

  /// A named constructor matches the showResult(match, saved) message in M03.
  const BotResultPage.showResult({super.key, required this.match, required this.saved, this.retrySave});

  @override
  State<BotResultPage> createState() => _BotResultPageState();
}

class _BotResultPageState extends State<BotResultPage> {
  late bool saved = widget.saved;
  bool retrying = false;

  Match get match => widget.match;

  void backToSetup(BuildContext context) => Navigator.of(context).pop();

  void goHome(BuildContext context) =>
      Navigator.of(context).popUntil((route) => route.isFirst);

  static String _points(double v) =>
      v == v.roundToDouble() ? v.toInt().toString() : v.toString();

  Future<void> _retry() async {
    final retry = widget.retrySave;
    if (retry == null || retrying) return;
    setState(() => retrying = true);
    final ok = await retry();
    if (mounted) setState(() { saved = ok; retrying = false; });
  }

  @override
  Widget build(BuildContext context) {
    final outcome = switch (match.player.result) {
      'win' => 'Người chơi thắng', 'lose' => 'Người chơi thua', _ => 'Hòa',
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
              '${match.player.durationSeconds} giây  •  +${_points(match.player.pointsEarned)} điểm'),
          Text('BOT: ${match.bot.correctCount}/${match.questionCount}  •  '
              '${match.bot.durationSeconds} giây  •  +${_points(match.bot.pointsEarned)} điểm'),
          const SizedBox(height: 24),
          Text(saved ? 'Đã lưu kết quả trên thiết bị.' : 'Chưa lưu được kết quả trên thiết bị.'),
          if (!saved && widget.retrySave != null)
            TextButton(
              onPressed: retrying ? null : _retry,
              child: Text(retrying ? 'Đang lưu...' : 'Thử lưu lại'),
            ),
          const Text('Không cộng điểm vào BXH trực tuyến.'),
          const SizedBox(height: 24),
          FilledButton(onPressed: () => backToSetup(context),
            child: const Text('Về chọn độ khó')),
          const SizedBox(height: 10),
          FilledButton(onPressed: () => goHome(context),
            child: const Text('Trang chủ')),
        ]),
      ),
    );
  }
}
