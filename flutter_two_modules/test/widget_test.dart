import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quiz_mobile_two_modules/main.dart';

void main() {
  testWidgets('M02/M03 demo entrypoint has both module buttons', (tester) async {
    await tester.pumpWidget(const QuizTwoModulesApp());
    expect(find.text('M02 – Xem bảng xếp hạng (online)'), findsOneWidget);
    expect(find.text('M03 – Thi đấu với máy (trên thiết bị)'), findsOneWidget);
    expect(find.byType(FilledButton), findsNWidgets(2));
  });
}
