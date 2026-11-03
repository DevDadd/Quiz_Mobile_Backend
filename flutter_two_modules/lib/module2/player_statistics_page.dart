import 'package:flutter/material.dart';

import 'leaderboard_api.dart';
import 'match_history_page.dart';

class PlayerStatisticsPage extends StatefulWidget {
  final LeaderboardApi api;
  final int playerId;
  final String name;

  const PlayerStatisticsPage({super.key, required this.api,
    required this.playerId, required this.name});

  @override
  State<PlayerStatisticsPage> createState() => _PlayerStatisticsPageState();
}

class _PlayerStatisticsPageState extends State<PlayerStatisticsPage> {
  Map<String, dynamic>? stats;
  String? error;

  @override
  void initState() { super.initState(); load(); }

  Future<void> load() async {
    setState(() { error = null; stats = null; });
    try {
      final result = await widget.api.getStats(widget.playerId);
      showStats(result);
    } catch (e) {
      showError(e.toString());
    }
  }

  void showStats(Map<String, dynamic> newStats) {
    if (mounted) setState(() => stats = newStats);
  }

  void openHistory() {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => MatchHistoryPage(
        api: widget.api, playerId: widget.playerId, name: widget.name),
    ));
  }

  void back() => Navigator.of(context).pop();

  void showError(String text) {
    if (mounted) setState(() => error = text);
  }

  @override
  Widget build(BuildContext context) {
    final values = stats;
    return Scaffold(
      appBar: AppBar(title: Text('Thống kê: ${widget.name}')),
      body: Padding(padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (values == null && error == null) const Center(child: CircularProgressIndicator()),
          if (error != null) Text('Không lấy được thống kê: $error'),
          if (values != null) ...[
            for (final entry in <String, dynamic>{
              'Tổng số trận': values['played'],
              'Thắng': values['win'],
              'Hòa': values['draw'],
              'Thua': values['lose'],
              'TB thời gian thắng (giây)': values['avg_win_time'],
            }.entries)
              ListTile(title: Text(entry.key), trailing: Text('${entry.value}')),
            FilledButton(onPressed: openHistory, child: const Text('Xem lịch sử thi đấu')),
          ],
        ]),
      ),
    );
  }
}
