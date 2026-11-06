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
CREATE TABLE IF NOT EXISTS terms (
    word    TEXT PRIMARY KEY,
    meaning TEXT NOT NULL  -- 뜻이 여러 개면 '|'로 이어 붙임
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


def load_terms(con):
    """{단어: 뜻 또는 (뜻1, 뜻2)} — dictionary.TERMS와 같은 모양."""
    out = {}
    for word, meaning in con.execute('SELECT word, meaning FROM terms'):
        means = tuple(meaning.split('|'))
        out[word] = means if len(means) > 1 else means[0]
    return out


def save_terms(con, terms):
    """사용자 단어 뜻 전체를 저장 (빠진 단어는 지움)."""
    with con:
        con.execute('DELETE FROM terms')
        con.executemany('INSERT INTO terms VALUES (?, ?)',
                        [(w, '|'.join(m) if isinstance(m, tuple) else m) for w, m in terms.items()])
