import 'package:flutter/material.dart';

import 'module2/leaderboard_api.dart';
import 'module2/leaderboard_page.dart';
import 'module3/bot_game_controller.dart';
import 'module3/bot_setup_page.dart';

/// Standalone demo of only M02 and M03. No Register/Login code was added or modified.
/// Android emulator backend: flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
const baseUrl = String.fromEnvironment('API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000');
const sessionId = String.fromEnvironment('SESSION_ID', defaultValue: '');

void main() => runApp(const QuizTwoModulesApp());

class QuizTwoModulesApp extends StatefulWidget {
  const QuizTwoModulesApp({super.key});
  @override
  State<QuizTwoModulesApp> createState() => _QuizTwoModulesAppState();
}

class _QuizTwoModulesAppState extends State<QuizTwoModulesApp> {
  late final LeaderboardApi leaderboardApi = LeaderboardApi(
    baseUrl: baseUrl,
    sessionId: sessionId.isEmpty ? null : sessionId,
  );
  final BotGameController botController = BotGameController();

  @override
  void dispose() { leaderboardApi.close(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Quiz Mobile – M02 & M03',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.blue),
      home: Scaffold(
        appBar: AppBar(title: const Text('Quiz Mobile – M02 / M03')),
        body: Builder(builder: (context) => Center(child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            FilledButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => LeaderboardPage(api: leaderboardApi),
            )), child: const Text('M02 – Xem bảng xếp hạng (online)')),
            const SizedBox(height: 20),
            FilledButton(onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => BotSetupPage(controller: botController),
            )), child: const Text('M03 – Thi đấu với máy (trên thiết bị)')),
          ],
        ))),
      ),
    );
  }
}
