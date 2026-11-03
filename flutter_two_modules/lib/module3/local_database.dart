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
      version: 2,
      onConfigure: (db) async => db.execute('PRAGMA foreign_keys = ON'),
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
    _db = database;
    await _seedQuestionBank(database);
    return database;
  }

  /// v1 -> v2: add the columns of the shared design (Figure 1 / ERD).
  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      for (final sql in const [
        "ALTER TABLE matches ADD COLUMN opponent_type TEXT NOT NULL DEFAULT 'BOT'",
        'ALTER TABLE matches ADD COLUMN player1_id INTEGER',
        'ALTER TABLE matches ADD COLUMN player2_id INTEGER',
        'ALTER TABLE matches ADD COLUMN current_question_index INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE matches ADD COLUMN updated_at TEXT',
        'ALTER TABLE match_questions ADD COLUMN started_at TEXT',
        'ALTER TABLE match_participants ADD COLUMN user_id INTEGER',
        'ALTER TABLE match_participants ADD COLUMN submitted_at TEXT',
        'ALTER TABLE match_answers ADD COLUMN answered_at TEXT',
      ]) {
        await db.execute(sql);
      }
    }
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
        player1_id INTEGER,
        player2_id INTEGER,
        opponent_type TEXT NOT NULL DEFAULT 'BOT',
        bot_difficulty TEXT NOT NULL,
        question_count INTEGER NOT NULL,
        time_limit_seconds INTEGER NOT NULL,
        current_question_index INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        updated_at TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE match_questions (
        match_id INTEGER NOT NULL,
        order_index INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        started_at TEXT,
        PRIMARY KEY(match_id, order_index),
        FOREIGN KEY(match_id) REFERENCES matches(match_id),
        FOREIGN KEY(question_id) REFERENCES questions(question_id)
      )
    ''');
    await db.execute('''
      CREATE TABLE match_participants (
        match_id INTEGER NOT NULL,
        side TEXT NOT NULL,
        user_id INTEGER,
        result TEXT NOT NULL,
        points_earned REAL NOT NULL,
        correct_count INTEGER NOT NULL,
        duration_seconds INTEGER NOT NULL,
        submitted_at TEXT,
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
        answered_at TEXT,
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
