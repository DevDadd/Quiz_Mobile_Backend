import 'package:flutter/material.dart';

import 'leaderboard_api.dart';

/// M02-C: match history (GD02 right screen).
class MatchHistoryPage extends StatefulWidget {
  final LeaderboardApi api;
  final int userId;
  final String name;
  const MatchHistoryPage({super.key, required this.api,
    required this.userId, required this.name});

  @override
  State<MatchHistoryPage> createState() => _MatchHistoryPageState();
}

class _MatchHistoryPageState extends State<MatchHistoryPage> {
  // Attributes named as in Figure 5.
  int get userId => widget.userId;
  int inLimit = 20;
  int inOffset = 0;
  bool loading = false;
  String? error;
  List<Map<String, dynamic>> outHistory = [];

  @override
  void initState() { super.initState(); load(userId, inLimit, inOffset); }

  Future<void> load(int id, int limit, int offset) async {
    setState(() { loading = true; error = null; });
    try {
      final list = await widget.api.getMatches(id, limit, offset);
      if (!mounted) return;
      setState(() { inLimit = limit; inOffset = offset; loading = false; });
      showHistory(list);
    } catch (e) {
      if (mounted) setState(() => loading = false);
      showError(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  void showHistory(List<Map<String, dynamic>> rows) {
    if (mounted) setState(() => outHistory = rows);
  }

  /// Back to the player statistics.
  void back() => Navigator.of(context).pop();

  void showError(String text) {
    if (mounted) setState(() => error = text);
  }

  String _resultLabel(Object? r) => switch (r) {
        'win' => 'Thắng', 'lose' => 'Thua', 'draw' => 'Hòa', _ => '$r',
      };

  String _num(Object? v) {
    if (v is num && v == v.roundToDouble()) return v.toStringAsFixed(1);
    return '$v';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('LỊCH SỬ THI ĐẤU')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Align(alignment: Alignment.centerLeft,
            child: Text('Người chơi: ${widget.name}',
                style: const TextStyle(fontWeight: FontWeight.bold))),
        ),
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.all(16), child: Text('Lỗi: $error')),
        if (!loading && error == null && outHistory.isEmpty)
          const Padding(padding: EdgeInsets.all(16), child: Text('Chưa có lịch sử thi đấu.')),
        Expanded(child: ListView.builder(
          itemCount: outHistory.length,
          itemBuilder: (_, index) {
            final m = outHistory[index];
            return Card(child: ListTile(
              title: Text('#${m['match_id']} ${m['opponent_name']} '
                  '${_resultLabel(m['result'])} ${_num(m['points_earned'])}'),
              subtitle: Text('Đúng ${m['correct_count']}/10 · ${m['duration_seconds']} giây\n'
                'Kết thúc: ${m['ended_at'] ?? 'Chưa kết thúc'}'),
              isThreeLine: true,
            ));
          },
        )),
        Padding(padding: const EdgeInsets.all(12), child: Wrap(
          spacing: 10, runSpacing: 8, alignment: WrapAlignment.center, children: [
          OutlinedButton(
            onPressed: loading || inOffset == 0
                ? null : () => load(userId, inLimit, (inOffset - inLimit).clamp(0, inOffset)),
            child: const Text('Trang trước')),
          OutlinedButton(
            onPressed: loading || outHistory.length < inLimit
                ? null : () => load(userId, inLimit, inOffset + inLimit),
            child: const Text('Trang sau')),
          FilledButton(onPressed: back, child: const Text('Trở lại thống kê')),
        ])),
      ]),
    );
  }
}
