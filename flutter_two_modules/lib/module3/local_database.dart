import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

/// Physical storage for M03 only. Independent of PostgreSQL / online ranking.
class LocalDatabase {
  LocalDatabase._();
  static final LocalDatabase instance = LocalDatabase._();
  Database? _db;

  Future<Database> get database async {
    if (_db != null) return _db!;
    final dbPath = path.join(await getDatabasesPath(), 'quiz_bot_local_v1.db');
    final database = await openDatabase(
      dbPath,
      version: 1,
      onConfigure: (db) async => db.execute('PRAGMA foreign_keys = ON'),
      onCreate: _onCreate,
    );
    _db = database;
    await _seedQuestionBank(database);
    return database;
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE questions (
        question_id INTEGER PRIMARY KEY,
        content TEXT NOT NULL,
        category TEXT NOT NULL,
        difficulty TEXT NOT NULL
      )
    ''');
    await db.execute('''
      CREATE TABLE question_options (
        option_id INTEGER PRIMARY KEY,
        question_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        FOREIGN KEY(question_id) REFERENCES questions(question_id)
      )
    ''');
    await db.execute('''
      CREATE TABLE matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_difficulty TEXT NOT NULL,
        question_count INTEGER NOT NULL,
        time_limit_seconds INTEGER NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE match_questions (
        match_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        PRIMARY KEY(match_id, order_index),
        FOREIGN KEY(match_id) REFERENCES matches(match_id),
        FOREIGN KEY(question_id) REFERENCES questions(question_id)
      )
    ''');
    await db.execute('''
      CREATE TABLE match_participants (
        match_id INTEGER NOT NULL,
        side TEXT NOT NULL,
        result TEXT NOT NULL,
        points_earned REAL NOT NULL,
        correct_count INTEGER NOT NULL,
        duration_seconds INTEGER NOT NULL,
        PRIMARY KEY(match_id, side),
        FOREIGN KEY(match_id) REFERENCES matches(match_id)
      )
    ''');
    await db.execute('''
      CREATE TABLE match_answers (
        match_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        side TEXT NOT NULL,
        selected_option_id INTEGER,
        is_correct INTEGER NOT NULL,
        response_time_ms INTEGER NOT NULL,
        PRIMARY KEY(match_id, order_index, side),
        FOREIGN KEY(match_id, order_index)
          REFERENCES match_questions(match_id, order_index),
        FOREIGN KEY(match_id, side)
          REFERENCES match_participants(match_id, side),
        FOREIGN KEY(selected_option_id) REFERENCES question_options(option_id)
      )
    ''');
  }

  /// The asset is a small ORIGINAL demo bank. Replace it with real team data.
  Future<void> _seedQuestionBank(Database db) async {
    final existing = Sqflite.firstIntValue(
      await db.rawQuery('SELECT COUNT(*) FROM questions'),
    ) ?? 0;
    if (existing != 0) return;

    final raw = await rootBundle.loadString('assets/questions_seed.json');
    final entries = (jsonDecode(raw) as List).cast<Map<String, dynamic>>();
    await db.transaction((txn) async {
      final batch = txn.batch();
      var optionId = 1;
      for (final entry in entries) {
        final qId = entry['question_id'] as int;
        batch.insert('questions', {
          'question_id': qId,
          'content': entry['content'],
          'category': entry['category'] ?? 'Tổng hợp',
          'difficulty': entry['difficulty'] ?? 'medium',
        });
        final options = (entry['options'] as List).cast<Map<String, dynamic>>();
        for (var j = 0; j < options.length; j++) {
          batch.insert('question_options', {
            'option_id': optionId++,
            'question_id': qId,
            'content': options[j]['content'],
            'is_correct': options[j]['is_correct'] == true ? 1 : 0,
            'order_index': j,
          });
        }
      }
      await batch.commit(noResult: true);
    });
  }
}
