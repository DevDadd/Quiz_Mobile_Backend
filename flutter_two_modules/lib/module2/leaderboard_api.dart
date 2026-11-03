import 'dart:convert';

import 'package:http/http.dart' as http;

/// HTTP/JSON interface to the existing leaderboard Django Views.
/// Authentication/login is NOT implemented here; an existing session ID may be passed in.
class LeaderboardApi {
  final String baseUrl;
  final String? sessionId;
  final http.Client _client;
  final bool _ownsClient;

  LeaderboardApi({required this.baseUrl, this.sessionId, http.Client? client})
      : _client = client ?? http.Client(),
        _ownsClient = client == null;

  Uri _url(String route, Map<String, String>? query) {
    final base = baseUrl.replaceFirst(RegExp(r'/$'), '');
    return Uri.parse('$base$route').replace(queryParameters: query);
  }

  Future<dynamic> _get(String route, [Map<String, String>? query]) async {
    final response = await _client.get(_url(route, query), headers: {
      'Accept': 'application/json',
      if (sessionId != null && sessionId!.isNotEmpty) 'Authorization': sessionId!,
    });
    final body = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final error = body is Map ? body['error'] : null;
      throw Exception(error ?? 'Lỗi API ${response.statusCode}');
    }
    return body;
  }

  Future<List<Map<String, dynamic>>> getRanking(int limit, int offset) async {
    final data = await _get('/leaderboard/leaderboard/', {
      'limit': '$limit', 'offset': '$offset',
    });
    return (data as List).map((row) => Map<String, dynamic>.from(row as Map)).toList();
  }

  Future<Map<String, dynamic>> getStats(int id) async {
    final data = await _get('/leaderboard/users/$id/stats/');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<Map<String, dynamic>>> getMatches(int id, int limit, int offset) async {
    final data = await _get('/leaderboard/users/$id/matches/', {
      'limit': '$limit', 'offset': '$offset',
    });
    return (data as List).map((row) => Map<String, dynamic>.from(row as Map)).toList();
  }

  void close() {
    if (_ownsClient) _client.close();
  }
}
