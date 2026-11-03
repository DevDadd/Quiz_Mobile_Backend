import 'package:flutter/material.dart';

import 'leaderboard_api.dart';

class MatchHistoryPage extends StatefulWidget {
  final LeaderboardApi api;
  final int playerId;
  final String name;
  const MatchHistoryPage({super.key, required this.api,
    required this.playerId, required this.name});

  @override
  State<MatchHistoryPage> createState() => _MatchHistoryPageState();
}

class _MatchHistoryPageState extends State<MatchHistoryPage> {
  static const pageSize = 20;
  int offset = 0;
  bool loading = false;
  String? error;
  List<Map<String, dynamic>> matches = [];

  @override
  void initState() { super.initState(); load(); }

  Future<void> load({int? nextOffset}) async {
    final target = nextOffset ?? offset;
    setState(() { loading = true; error = null; });
    try {
      final list = await widget.api.getMatches(widget.playerId, pageSize, target);
      if (!mounted) return;
      setState(() { offset = target; loading = false; });
      showHistory(list);
    } catch (e) {
      if (mounted) setState(() => loading = false);
      showError(e.toString());
    }
  }

  void showHistory(List<Map<String, dynamic>> rows) {
    if (mounted) setState(() => matches = rows);
  }

  void back() => Navigator.of(context).pop();

  void showError(String text) {
    if (mounted) setState(() => error = text);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Lịch sử: ${widget.name}')),
      body: Column(children: [
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.all(16), child: Text('Lỗi: $error')),
        if (!loading && error == null && matches.isEmpty)
          const Padding(padding: EdgeInsets.all(16), child: Text('Chưa có lịch sử thi đấu.')),
        Expanded(child: ListView.builder(
          itemCount: matches.length,
          itemBuilder: (_, index) {
            final m = matches[index];
            return Card(child: ListTile(
              title: Text('Trận #${m['match_id']} • ${m['opponent_name']}'),
              subtitle: Text('Kết quả: ${m['result']}  •  Điểm: ${m['points_earned']}\n'
                'Đúng: ${m['correct_count']}  •  Thời gian: ${m['duration_seconds']} giây\n'
                'Kết thúc: ${m['ended_at'] ?? 'Chưa kết thúc'}'),
              isThreeLine: true,
            ));
          },
        )),
        Padding(padding: const EdgeInsets.all(12), child: Row(children: [
          OutlinedButton(onPressed: loading || offset == 0
              ? null : () => load(nextOffset: (offset - pageSize).clamp(0, offset)),
            child: const Text('Trang trước')),
          const SizedBox(width: 10),
          Text('Trang ${offset ~/ pageSize + 1}'),
          const SizedBox(width: 10),
          OutlinedButton(onPressed: loading || matches.length < pageSize
              ? null : () => load(nextOffset: offset + pageSize),
            child: const Text('Trang sau')),
        ])),
      ]),
    );
  }
}
