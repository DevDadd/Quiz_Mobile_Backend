import 'package:flutter/material.dart';

import 'leaderboard_api.dart';
import 'player_statistics_page.dart';

/// M02-A: online ranking (GD02 left screen), sorted server-side by three criteria.
class LeaderboardPage extends StatefulWidget {
  final LeaderboardApi api;
  const LeaderboardPage({super.key, required this.api});

  @override
  State<LeaderboardPage> createState() => _LeaderboardPageState();
}

class _LeaderboardPageState extends State<LeaderboardPage> {
  // Attributes named as in Figure 5.
  int inLimit = 50;
  int inOffset = 0;
  List<Map<String, dynamic>> outRanking = [];
  bool loading = true;
  String? error;
  int? selectedId;

  @override
  void initState() { super.initState(); load(); }

  /// load(): loads the page described by inLimit / inOffset.
  Future<void> load() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await widget.api.getRanking(inLimit, inOffset);
      if (!mounted) return;
      setState(() { loading = false; selectedId = null; });
      showRanking(result);
    } catch (e) {
      if (!mounted) return;
      setState(() => loading = false);
      showError(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _goToOffset(int offset) async {
    final previous = inOffset;
    inOffset = offset;
    await load();
    if (error != null) setState(() => inOffset = previous);
  }

  void selectPlayer(int id) {
    final row = outRanking.firstWhere((r) => r['user_id'] == id);
    final name = (row['display_name'] ?? 'Người chơi $id').toString();
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlayerStatisticsPage(api: widget.api, userId: id, name: name),
    ));
  }

  void showRanking(List<Map<String, dynamic>> rows) {
    if (mounted) setState(() => outRanking = rows);
  }

  void showError(String text) {
    if (mounted) setState(() => error = text);
  }

  void goHome() => Navigator.of(context).popUntil((route) => route.isFirst);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('BẢNG XẾP HẠNG')),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text('Số dòng: [$inLimit]   Trang: [${inOffset ~/ inLimit + 1}]'),
          ),
        ),
        if (loading) const LinearProgressIndicator(),
        if (error != null) Padding(padding: const EdgeInsets.all(16), child: Text(error!)),
        if (!loading && error == null && outRanking.isEmpty)
          const Padding(padding: EdgeInsets.all(16), child: Text('Chưa có dữ liệu xếp hạng.')),
        if (outRanking.isNotEmpty)
          Expanded(child: SingleChildScrollView(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                showCheckboxColumn: false,
                columns: const [
                  DataColumn(label: Text('Hạng')),
                  DataColumn(label: Text('Tên')),
                  DataColumn(label: Text('Điểm')),
                  DataColumn(label: Text('TB đối thủ')),
                  DataColumn(label: Text('TG thắng')),
                ],
                rows: outRanking.map((r) => DataRow(
                  selected: r['user_id'] == selectedId,
                  onSelectChanged: (_) => setState(() => selectedId = r['user_id'] as int),
                  cells: [
                    DataCell(Text('${r['rank']}')),
                    DataCell(Text('${r['display_name'] ?? ''}')),
                    DataCell(Text('${r['total_score']}')),
                    DataCell(Text('${r['avg_opp_score']}')),
                    DataCell(Text('${r['avg_win_time']} s')),
                  ],
                )).toList(),
              ),
            ),
          ))
        else
          const Spacer(),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
            FilledButton(
              onPressed: loading || selectedId == null ? null : () => selectPlayer(selectedId!),
              child: const Text('Chọn người chơi'),
            ),
            FilledButton(onPressed: loading ? null : load, child: const Text('Tải lại')),
            OutlinedButton(
              onPressed: loading || inOffset == 0
                  ? null : () => _goToOffset((inOffset - inLimit).clamp(0, inOffset)),
              child: const Text('Trang trước'),
            ),
            OutlinedButton(
              onPressed: loading || outRanking.length < inLimit
                  ? null : () => _goToOffset(inOffset + inLimit),
              child: const Text('Trang sau'),
            ),
            OutlinedButton(onPressed: goHome, child: const Text('Trang chủ')),
          ]),
        ),
        const Padding(
          padding: EdgeInsets.only(bottom: 12),
          child: Text('Sắp xếp: Điểm ↓ → TB điểm đối thủ ↓ → TG thắng trung bình ↑',
              style: TextStyle(fontSize: 12)),
        ),
      ]),
    );
  }
}
