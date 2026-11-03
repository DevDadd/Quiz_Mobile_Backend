import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quiz_mobile_two_modules/module2/leaderboard_api.dart';

void main() {
  test('M02 GET xếp hạng đủ limit offset, đúng endpoint', () async {
    final client = MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/leaderboard/leaderboard/');
      expect(request.url.queryParameters['limit'], '50');
      expect(request.url.queryParameters['offset'], '0');
      return http.Response(jsonEncode([{
        'rank': 1, 'user_id': 7, 'display_name': 'Player07',
        'total_score': 22.5, 'avg_opp_score': 10.0, 'avg_win_time': 28.0,
      }]), 200);
    });
    final api = LeaderboardApi(baseUrl: 'https://example.test', client: client);
    final rows = await api.getRanking(50, 0);
    expect(rows.single['rank'], 1);
    client.close();
  });

  test('M02 GET thống kê và lịch sử đúng id', () async {
    final routes = <String>[];
    final client = MockClient((request) async {
      routes.add(request.url.path);
      if (request.url.path.endsWith('/stats/')) {
        return http.Response(jsonEncode({
          'played': 8, 'win': 3, 'draw': 3, 'lose': 2, 'avg_win_time': 30.0,
        }), 200);
      }
      expect(request.url.queryParameters['limit'], '20');
      expect(request.url.queryParameters['offset'], '0');
      return http.Response(jsonEncode([{
        'match_id': 55, 'opponent_name': 'BOT', 'result': 'draw',
        'points_earned': 0.5, 'correct_count': 8,
        'duration_seconds': 60, 'ended_at': '2026-11-01T12:00:00Z',
      }]), 200);
    });
    final api = LeaderboardApi(baseUrl: 'https://example.test', client: client);
    final stats = await api.getStats(7);
    final history = await api.getMatches(7, 20, 0);
    expect(stats['played'], 8);
    expect(history.single['opponent_name'], 'BOT');
    expect(routes, ['/leaderboard/users/7/stats/', '/leaderboard/users/7/matches/']);
    client.close();
  });
}
