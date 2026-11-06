"""SQLite 저장소 — 분석 결과(datasets, columns)와 사용자가 넣은 단어 뜻(terms)을 보관한다.
같은 파일을 다시 올려도 덮어쓰지 않고 새 기록으로 쌓는다."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name    TEXT    NOT NULL,
    uploaded_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    row_count    INTEGER NOT NULL,
    col_count    INTEGER NOT NULL,
    sample_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS columns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    ko_name     TEXT    NOT NULL,
    certainty   TEXT    NOT NULL CHECK (certainty IN ('확실', '추측', '추측·AI')),
    role        TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    blank_pct   REAL    NOT NULL CHECK (blank_pct BETWEEN 0 AND 100),
    description TEXT    NOT NULL,
    examples    TEXT    NOT NULL,
    UNIQUE (dataset_id, position)
);
-- 사용자가 넣은 단어 뜻과 직접 고친 역할은 주제(예: 야구, 쇼핑몰)별로 따로 둔다.
-- 같은 단어도 분야마다 뜻이 달라서 (home = 홈 플레이트 / 집), 한 주제에서 넣은 뜻이 다른 데이터에 섞이지 않게.
CREATE TABLE IF NOT EXISTS terms (
    topic   TEXT NOT NULL,
    word    TEXT NOT NULL,
    meaning TEXT NOT NULL,  -- 뜻이 여러 개면 '|'로 이어 붙임
    PRIMARY KEY (topic, word)
);
CREATE TABLE IF NOT EXISTS roles (
    topic       TEXT NOT NULL,  -- '' = 주제 없음
    column_name TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('id', 'time', 'dimension', 'measure')),
    PRIMARY KEY (topic, column_name)
);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')  # SQLite는 기본으로 외래키 검사를 끄고 있음
    con.executescript(SCHEMA)
    return con


def save_dataset(con, file_name, row_count, sample_count, table):
    """분석 결과 한 건 저장 → 새 dataset id. table은 analyze.dictionary_rows()의 결과."""
    with con:  # 중간에 실패하면 전부 취소 (반쪽짜리 기록이 남지 않게)
        cur = con.execute('INSERT INTO datasets (file_name, row_count, col_count, sample_count) VALUES (?, ?, ?, ?)',
                          (file_name, row_count, len(table), sample_count))
        con.executemany(
            'INSERT INTO columns (dataset_id, position, name, ko_name, certainty, role, kind, blank_pct, description, examples)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [(cur.lastrowid, i, r['원래 이름'], r['한글 이름'], r['확실/추측'], r['역할'], r['종류'],
              r['빈칸 비율(%)'], r['설명'], r['샘플 값']) for i, r in enumerate(table)])
    return cur.lastrowid


def list_datasets(con):
    return [dict(r) for r in con.execute('SELECT * FROM datasets ORDER BY id DESC')]


def get_columns(con, dataset_id):
    return [dict(r) for r in con.execute('SELECT * FROM columns WHERE dataset_id = ? ORDER BY position', (dataset_id,))]


def delete_dataset(con, dataset_id):
    with con:
        con.execute('DELETE FROM datasets WHERE id = ?', (dataset_id,))  # 컬럼은 ON DELETE CASCADE로 같이 지워짐


def list_topics(con):
    """단어 뜻이나 역할을 저장한 적 있는 주제들."""
    return [t for (t,) in con.execute("SELECT topic FROM terms UNION SELECT topic FROM roles WHERE topic != '' ORDER BY 1")]


def load_terms(con, topic):
    """그 주제의 {단어: 뜻 또는 (뜻1, 뜻2)} — dictionary.TERMS와 같은 모양."""
    out = {}
    for word, meaning in con.execute('SELECT word, meaning FROM terms WHERE topic = ?', (topic,)):
        means = tuple(meaning.split('|'))
        out[word] = means if len(means) > 1 else means[0]
    return out


def save_terms(con, topic, terms):
    """그 주제의 단어 뜻 전체를 저장 (빠진 단어는 지움). 다른 주제는 건드리지 않는다."""
    with con:
        con.execute('DELETE FROM terms WHERE topic = ?', (topic,))
        con.executemany('INSERT INTO terms VALUES (?, ?, ?)',
                        [(topic, w, '|'.join(m) if isinstance(m, tuple) else m) for w, m in terms.items()])


def load_roles(con, topic):
    """그 주제에서 사용자가 직접 고친 {컬럼 이름: 역할}."""
    return dict(con.execute('SELECT column_name, role FROM roles WHERE topic = ?', (topic,)).fetchall())


def save_role(con, topic, column_name, role):
    """역할 저장. role이 None이면 지워서 자동 판단으로 되돌린다."""
    with con:
        if role is None:
            con.execute('DELETE FROM roles WHERE topic = ? AND column_name = ?', (topic, column_name))
        else:
            con.execute('INSERT OR REPLACE INTO roles VALUES (?, ?, ?)', (topic, column_name, role))
