# db.py
import sqlite3
import os
import pickle  # for saving face encodings (numpy arrays) as BLOBs
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_connection():
    """
    Return a new sqlite3 connection with useful settings.
    We set row_factory to sqlite3.Row so we can access columns by name.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------
# User helpers
# -------------------------
def create_user(name: str, user_id: str, password: str, face_encoding=None):
    """
    Insert a new user into the users table.
    face_encoding: a numpy array representing face encoding; will be pickled as a BLOB if provided.
    Password is hashed using werkzeug.security.generate_password_hash.
    """
    password_hash = generate_password_hash(password)
    face_blob = pickle.dumps(face_encoding) if face_encoding is not None else None

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (name, user_id, password_hash, face_data)
            VALUES (?, ?, ?, ?)
        """, (name, user_id, password_hash, face_blob))
        conn.commit()
        return cur.lastrowid


def get_user_by_userid(user_id: str):
    """
    Return a dict-like Row for the user with the given user_id, or None if not found.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row


def verify_password(user_id: str, password: str) -> bool:
    """
    Verify the plain-text password against the stored hash for the given user_id.
    """
    user = get_user_by_userid(user_id)
    if not user:
        return False
    return check_password_hash(user["password_hash"], password)


# -------------------------
# Candidate & Position helpers (new)
# -------------------------
def create_position(name: str):
    """Insert a new position (office) such as 'President'."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO positions (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid

def get_positions():
    """Return all positions as list of sqlite3.Row."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM positions ORDER BY name")
        return cur.fetchall()

def create_candidate(name: str, position_id: int = None, bio: str = None, logo_path: str = None):
    """
    Create a candidate.
    position_id can be None.
    logo_path is a relative path stored in DB (e.g., 'uploads/logo.jpg').
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO candidates (name, votes, position_id, bio, logo_path)
            VALUES (?, 0, ?, ?, ?)
        """, (name, position_id, bio, logo_path))
        conn.commit()
        return cur.lastrowid

def get_candidates():
    """
    Return list of candidates with new fields (id, name, votes, position_id, bio, logo_path).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM candidates ORDER BY id")
        return cur.fetchall()

def get_candidate_by_id(candidate_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
        return cur.fetchone()

# -------------------------
# Voting helpers
# -------------------------
def record_vote(user_id: str, candidate_id: int):
    """
    Record a vote by a user for a candidate.
    This function should be called only after checking that the user hasn't voted before.
    It inserts into votes table and increments candidates.votes atomically inside the same connection.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        # Insert vote
        cur.execute("INSERT INTO votes (user_id, candidate_id) VALUES (?, ?)", (user_id, candidate_id))
        # Increment candidate votes count
        cur.execute("UPDATE candidates SET votes = votes + 1 WHERE id = ?", (candidate_id,))
        conn.commit()
        return cur.lastrowid


def user_has_voted(user_id: str) -> bool:
    """
    Return True if a user has already cast a vote.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM votes WHERE user_id = ? LIMIT 1", (user_id,))
        return cur.fetchone() is not None


def get_votes_count_for_candidate(candidate_id: int) -> int:
    """
    Return the vote count for a candidate (fallback: 0).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT votes FROM candidates WHERE id = ?", (candidate_id,))
        r = cur.fetchone()
        return int(r["votes"]) if r else 0

# Optional utility to decode stored face encoding blob
def get_face_encoding_for_user(user_id: str):
    """
    Return the unpickled face encoding (e.g. numpy array) for a user, or None.
    """
    user = get_user_by_userid(user_id)
    if not user:
        return None
    blob = user["face_data"]
    if blob is None:
        return None
    return pickle.loads(blob)
