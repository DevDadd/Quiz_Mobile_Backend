import 'package:flutter_test/flutter_test.dart';
import 'package:quiz_mobile_two_modules/module3/models.dart';

void main() {
  group('M03 - thắng/hòa/thua theo đúng đề bài', () {
    test('8/10 so với 6/10 phải hòa, mỗi bên không đúng hết', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 8, botCorrect: 6,
        playerSeconds: 25, botSeconds: 31,
      ), 'draw');
    });
    test('10/10 so với 6/10 người chơi thắng', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 10, botCorrect: 6,
        playerSeconds: 25, botSeconds: 31,
      ), 'win');
    });
    test('8/10 so với 10/10 bot thắng', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 8, botCorrect: 10,
        playerSeconds: 25, botSeconds: 31,
      ), 'lose');
    });
    test('cả hai đúng 10/10 thì người nhanh hơn thắng', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 10, botCorrect: 10,
        playerSeconds: 25, botSeconds: 31,
      ), 'win');
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 10, botCorrect: 10,
        playerSeconds: 32, botSeconds: 31,
      ), 'lose');
    });
    test('cả hai đúng 10/10 và bằng thời gian thì hòa', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 10, botCorrect: 10,
        playerSeconds: 31, botSeconds: 31,
      ), 'draw');
    });
    test('không ai đúng hết dù bằng điểm vẫn hòa', () {
      expect(resolveMatchOutcome(
        questionCount: 10, playerCorrect: 9, botCorrect: 9,
        playerSeconds: 20, botSeconds: 40,
      ), 'draw');
    });
  });
}

// See module3_controller_test.dart for full start -> answer -> submit -> save flow.
