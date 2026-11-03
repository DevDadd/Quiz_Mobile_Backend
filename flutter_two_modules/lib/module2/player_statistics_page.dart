import 'package:flutter/material.dart';

import 'leaderboard_api.dart';
import 'match_history_page.dart';

/// M02-B: player statistics (GD02 middle screen).
class PlayerStatisticsPage extends StatefulWidget {
  final LeaderboardApi api;
  final int userId;
  final String name;

  const PlayerStatisticsPage({super.key, required this.api,
    required this.userId, required this.name});

  @override
  State<PlayerStatisticsPage> createState() => _PlayerStatisticsPageState();
}

class _PlayerStatisticsPageState extends State<PlayerStatisticsPage> {
  // Attributes named as in Figure 5.
  int get userId => widget.userId;
  Map<String, dynamic>? outStatistics;
  String? error;

  @override
  void initState() { super.initState(); load(userId); }

  Future<void> load(int id) async {
    setState(() { error = null; outStatistics = null; });
    try {
      final result = await widget.api.getStats(id);
      showStats(result);
    } catch (e) {
      showError(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  void showStats(Map<String, dynamic> stats) {
    if (mounted) setState(() => outStatistics = stats);
  }

  void openHistory() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => MatchHistoryPage(
        api: widget.api, userId: userId, name: widget.name),
    ));
  }

  /// Back to the leaderboard.
  void back() => Navigator.of(context).pop();

  void showError(String text) {
    if (mounted) setState(() => error = text);
  }

  @override
  Widget build(BuildContext context) {
    final values = outStatistics;
    return Scaffold(
      appBar: AppBar(title: const Text('THỐNG KÊ NGƯỜI CHƠI')),
      body: Padding(padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Người chơi: ${widget.name}',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          if (values == null && error == null) const Center(child: CircularProgressIndicator()),
          if (error != null) Text('Không lấy được thông tin người chơi: $error'),
          if (values != null)
            for (final entry in <String, dynamic>{
              'Số trận': values['played'],
              'Thắng': values['win'],
              'Hòa': values['draw'],
              'Thua': values['lose'],
              'TG thắng trung bình (giây)': values['avg_win_time'],
            }.entries)
              ListTile(title: Text(entry.key), trailing: Text('${entry.value}')),
          const Spacer(),
          FilledButton(
            onPressed: values == null ? null : openHistory,
            child: const Text('Xem lịch sử'),
          ),
          const SizedBox(height: 8),
          FilledButton(onPressed: back, child: const Text('Trở lại bảng xếp hạng')),
        ]),
      ),
    );
  }
}
