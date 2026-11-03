"""Runnable M02 Django-View SQL behavior smoke test without Django/PostgreSQL.
SQLite is used only as an SQL test double; production app remains PostgreSQL.
"""
import importlib.util, sqlite3, sys, types
from pathlib import Path

class Response:
    def __init__(self, data=None, status=200):
        self.data = data
        self.status_code = status

class APIView: pass

class FakeCursor:
    def __init__(self, db):
        self.db=db
        self.cursor=db.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    @property
    def description(self): return self.cursor.description
    def execute(self, query, args=None):
        return self.cursor.execute(query.replace('%s','?'), args or [])
    def fetchall(self): return self.cursor.fetchall()
    def fetchone(self): return self.cursor.fetchone()

class FakeConnection:
    def __init__(self, db): self.db=db
    def cursor(self): return FakeCursor(self.db)

def fake_module(name, **kwargs):
    mod=types.ModuleType(name)
    mod.__dict__.update(kwargs)
    sys.modules[name]=mod


def run():
    db=sqlite3.connect(':memory:')
    db.executescript('''
    CREATE TABLE users (user_id INTEGER PRIMARY KEY, username TEXT, display_name TEXT, total_score REAL);
    CREATE TABLE matches (match_id INTEGER PRIMARY KEY, status TEXT, opponent_type TEXT, ended_at TEXT);
    CREATE TABLE match_participants (match_id INTEGER, side TEXT, user_id INTEGER, result TEXT,
       points_earned REAL, correct_count INTEGER, duration_seconds INTEGER);
    INSERT INTO users VALUES (1,'p1','Player1',10.0),(2,'p2',NULL,12.0),(3,'p3','Player3',7.0);
    INSERT INTO matches VALUES
      (101,'finished','HUMAN','2026-11-01T12:00:00'),
      (102,'finished','BOT','2026-11-01T13:00:00'),
      (103,'ongoing','HUMAN',NULL);
    INSERT INTO match_participants VALUES
      (101,'P1',1,'win',1.0,10,10),
      (101,'P2',2,'lose',0.0,8,25),
      (102,'P1',1,'draw',0.5,8,60),
      (102,'P2',NULL,'draw',0.5,6,58),
      (103,'P1',1,'draw',0.0,0,0),
      (103,'P2',3,'draw',0.0,0,0);
    ''')
    fake_module('django')
    fake_module('django.db', connection=FakeConnection(db))
    fake_module('rest_framework')
    fake_module('rest_framework.response', Response=Response)
    fake_module('rest_framework.views', APIView=APIView)
    fake_module('authentication')
    fake_module('authentication.services', get_all_players=lambda _:[], get_auth_session=lambda _:(1,'x'))
    p = Path(__file__).parent / 'leaderboard/views.py'
    if not p.is_file():
        p = Path(__file__).parent / 'source/Quiz_Mobile_Backend-main/leaderboard/views.py'
    spec=importlib.util.spec_from_file_location('m02_views_testdouble',p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    class Request:
        def __init__(self, params=None):self.query_params=params or {}
    ranking=mod.LeaderboardView().get(Request())
    assert ranking.status_code==200,ranking.data
    assert [x['user_id'] for x in ranking.data]==[2,1,3],ranking.data
    assert [x['rank'] for x in ranking.data]==[1,2,3],ranking.data
    assert mod.LeaderboardView().get(Request({'limit':'abc'})).status_code==400
    assert mod.LeaderboardView().get(Request({'limit':'-1'})).status_code==400
    assert mod.LeaderboardView().get(Request({'limit':'101'})).status_code==400
    assert [x['rank'] for x in mod.LeaderboardView().get(Request({'limit':'1','offset':'1'})).data]==[2]
    stats=mod.UserStatsView().get(Request(),1)
    assert stats.status_code==200 and stats.data['played']==2 and stats.data['win']==1 and stats.data['draw']==1,stats.data
    stats3=mod.UserStatsView().get(Request(),3)
    assert stats3.data['played']==0,stats3.data
    history=mod.UserMatchesView().get(Request(),1)
    assert history.status_code==200 and len(history.data)==2,history.data
    assert [x['match_id'] for x in history.data]==[102,101],history.data
    assert history.data[0]['opponent_name']=='BOT',history.data
    assert history.data[1]['opponent_name']=='p2',history.data  # NULL display_name falls back to username
    assert mod.UserStatsView().get(Request(),999).status_code==404
    print('PASS M02 leaderboard ranking + pagination + stats + history + no ongoing matches')

if __name__=='__main__':
    run()
