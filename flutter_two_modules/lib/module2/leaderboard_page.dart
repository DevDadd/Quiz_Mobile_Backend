import 'package:flutter/material.dart';

import 'leaderboard_api.dart';
import 'player_statistics_page.dart';

/// M02-A: online ranking, sorted server-side by three specification criteria.
class LeaderboardPage extends StatefulWidget {
  final LeaderboardApi api;
  const LeaderboardPage({super.key, required this.api});

  @override
  State<LeaderboardPage> createState() => _LeaderboardPageState();
}

class _LeaderboardPageState extends State<LeaderboardPage> {
  static const pageSize = 50;
  int offset = 0;
  List<Map<String, dynamic>> rows = [];
  bool loading = true;
  String? error;

  @override
  void initState() { super.initState(); load(); }

  Future<void> load({int? nextOffset}) async {
    final target = nextOffset ?? offset;
    setState(() { loading = true; error = null; });
    try {
      final result = await widget.api.getRanking(pageSize, target);
      if (!mounted) return;
      setState(() { offset = target; loading = false; });
      showRanking(result);
    } catch (e) {
      if (!mounted) return;
      setState(() => loading = false);
      showError(e.toString());
    }
  }

  void selectPlayer(int id) {
    final row = rows.firstWhere((r) => r['user_id'] == id);
    final name = (row['display_name'] ?? 'Người chơi $id').toString();
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlayerStatisticsPage(api: widget.api, playerId: id, name: name),
    ));
  }

  void showRanking(List<Map<String, dynamic>> newRows) {
    if (mounted) setState(() => rows = newRows);
  }

  void showError(String message) {
    if (mounted) setState(() => error = message);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Bảng xếp hạng')),
      body: Column(children: [
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('Sắp xếp: Tổng điểm ↓ → TB điểm đối thủ ↓ → TB thời gian thắng ↑'),
        ),
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.all(16), child: Text(error!)),
        if (!loading && error == null && rows.isEmpty)
          const Padding(padding: EdgeInsets.all(16), child: Text('Chưa có dữ liệu xếp hạng.')),
        if (rows.isNotEmpty)
          Expanded(child: SingleChildScrollView(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: const [
                  DataColumn(label: Text('Hạng')),
                  DataColumn(label: Text('Tên người chơi')),
                  DataColumn(label: Text('Tổng điểm')),
                  DataColumn(label: Text('TB điểm đối thủ')),
                  DataColumn(label: Text('TB thời gian thắng')),
                ],
                rows: rows.map((r) => DataRow(
                  onSelectChanged: (_) => selectPlayer(
                    r['user_id'] as int,
                  ),
                  cells: [
                    DataCell(Text('${r['rank']}')),
                    DataCell(Text('${r['display_name'] ?? ''}')),
                    DataCell(Text('${r['total_score']}')),
                    DataCell(Text('${r['avg_opp_score']}')),
                    DataCell(Text('${r['avg_win_time']}s')),
                  ],
                )).toList(),
              ),
            ),
          )),
        Padding(padding: const EdgeInsets.all(8), child: Row(children: [
          OutlinedButton(onPressed: loading || offset == 0
              ? null : () => load(nextOffset: (offset - pageSize).clamp(0, offset)),
            child: const Text('Trang trước')),
          const SizedBox(width: 8),
          Text('Trang ${offset ~/ pageSize + 1}'),
          const SizedBox(width: 8),
          OutlinedButton(onPressed: loading || rows.length < pageSize
              ? null : () => load(nextOffset: offset + pageSize),
            child: const Text('Trang sau')),
          const Spacer(),
          IconButton(onPressed: loading ? null : load,
              icon: const Icon(Icons.refresh), tooltip: 'Tải lại'),
        ])),
      ]),
    );
  }
}
