# app.py

import os, io, uuid, base64, sqlite3, csv
from PIL import Image
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
)
from werkzeug.utils import secure_filename

# DB helpers 
from db import (
    create_user, get_user_by_userid, verify_password,
    get_face_encoding_for_user, get_candidates, get_candidate_by_id,
    user_has_voted, record_vote,
    create_position, get_positions, create_candidate
)

import face_recognition, numpy as np

# ----- config -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(FACES_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTS = {"png", "jpg", "jpeg"}
ALLOWED_LOGO_EXTS = {"png", "jpg", "jpeg", "svg", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-key-change-me")
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

# ----- helpers -----
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS

def allowed_logo(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_LOGO_EXTS

def save_image_bytes(image_bytes, filename=None):
    if filename is None:
        filename = f"{uuid.uuid4().hex}.jpg"
    path = os.path.join(FACES_DIR, secure_filename(filename))
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(path, format="JPEG")
    return path

def save_logo_file(file_storage):
    fname = f"{uuid.uuid4().hex}_{secure_filename(file_storage.filename)}"
    dest = os.path.join(app.config['UPLOAD_FOLDER'], fname)
    file_storage.save(dest)
    return f"uploads/{fname}"

def get_face_encoding_from_image_file(path):
    img = face_recognition.load_image_file(path)
    encs = face_recognition.face_encodings(img)
    if len(encs) != 1:
        return None, len(encs)
    return encs[0], 1

# ----- public routes -----
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        user_id = request.form.get("user_id","").strip()
        password = request.form.get("password","")
        image_data_b64 = request.form.get("image_data", None)
        uploaded_file = request.files.get("image_file", None)

        if not name or not user_id or not password:
            flash("Provide name, user id, and password.", "danger"); return redirect(url_for("register"))

        if get_user_by_userid(user_id):
            flash("User ID exists. Choose another.", "danger"); return redirect(url_for("register"))

        saved_path = None
        if image_data_b64:
            if "," in image_data_b64:
                _, image_data_b64 = image_data_b64.split(",",1)
            try:
                image_bytes = base64.b64decode(image_data_b64)
            except Exception:
                flash("Invalid webcam image data.", "danger"); return redirect(url_for("register"))
            saved_path = save_image_bytes(image_bytes, filename=f"{user_id}_webcam.jpg")
        elif uploaded_file and uploaded_file.filename:
            if not allowed_file(uploaded_file.filename):
                flash("Unsupported file type.", "danger"); return redirect(url_for("register"))
            saved_path = save_image_bytes(uploaded_file.read(), filename=f"{user_id}_{secure_filename(uploaded_file.filename)}")
        else:
            flash("Upload image or capture from webcam.", "danger"); return redirect(url_for("register"))

        enc, count = get_face_encoding_from_image_file(saved_path)
        if enc is None:
            try: os.remove(saved_path)
            except: pass
            if count == 0:
                flash("No face detected. Use a clear frontal photo.", "danger")
            else:
                flash("Multiple faces detected. Use a photo with only your face.", "danger")
            return redirect(url_for("register"))

        try:
            create_user(name, user_id, password, face_encoding=enc)
            flash("Registration successful.", "success"); return redirect(url_for("index"))
        except Exception as e:
            try: os.remove(saved_path)
            except: pass
            flash(f"Error creating user: {e}", "danger"); return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user_id = request.form.get("user_id","").strip()
        password = request.form.get("password","")
        if not user_id or not password:
            flash("Provide credentials.", "danger"); return redirect(url_for("login"))
        if not verify_password(user_id, password):
            flash("Invalid user id or password.", "danger"); return redirect(url_for("login"))
        session.clear()
        session["pre_auth_user"] = user_id
        return render_template("login.html", step="verify", user_id=user_id)
    return render_template("login.html", step="login", user_id=None)

@app.route("/verify_face", methods=["POST"])
def verify_face():
    if "pre_auth_user" not in session:
        return jsonify({"matched":False,"message":"No login attempt."}),400
    user_id = session["pre_auth_user"]
    data = request.get_json(force=True)
    image_data_b64 = data.get("image_data","")
    if not image_data_b64:
        return jsonify({"matched":False,"message":"No image data."}),400
    if "," in image_data_b64:
        _, image_data_b64 = image_data_b64.split(",",1)
    try:
        img_bytes = base64.b64decode(image_data_b64)
    except Exception:
        return jsonify({"matched":False,"message":"Invalid image data."}),400

    tmp = os.path.join(FACES_DIR, f"verify_{uuid.uuid4().hex}.jpg")
    try:
        with open(tmp,"wb") as f: f.write(img_bytes)
    except Exception as e:
        return jsonify({"matched":False,"message":f"Failed to save image: {e}"}),500

    enc, count = get_face_encoding_from_image_file(tmp)
    try: os.remove(tmp)
    except: pass

    if enc is None:
        if count == 0:
            return jsonify({"matched":False,"message":"No face detected."}),200
        else:
            return jsonify({"matched":False,"message":"Multiple faces detected."}),200

    stored_enc = get_face_encoding_for_user(user_id)
    if stored_enc is None:
        return jsonify({"matched":False,"message":"No stored face encoding."}),400

    try:
        dist = face_recognition.face_distance([np.array(stored_enc)], np.array(enc))[0]
        TH = 0.6
        if dist <= TH:
            session.clear()
            session["user_id"] = user_id
            return jsonify({"matched":True,"message":f"Face matched (distance={dist:.3f})."}),200
        else:
            return jsonify({"matched":False,"message":f"Face did not match (distance={dist:.3f})."}),200
    except Exception as e:
        return jsonify({"matched":False,"message":f"Error comparing faces: {e}"}),500

# ----- voting -----
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **k):
        if "user_id" not in session:
            flash("Login and face verification required.", "danger"); return redirect(url_for("login"))
        return fn(*a, **k)
    return wrapper

@app.route("/vote")
@login_required
def vote():
    candidates = get_candidates()
    return render_template("vote.html", candidates=candidates, user_id=session.get("user_id"))

@app.route("/cast_vote", methods=["POST"])
@login_required
def cast_vote():
    user_id = session.get("user_id")
    candidate_id = request.form.get("candidate_id")
    if not candidate_id:
        flash("No candidate selected.", "danger"); return redirect(url_for("vote"))
    try:
        cid = int(candidate_id)
    except:
        flash("Invalid candidate.", "danger"); return redirect(url_for("vote"))

    if user_has_voted(user_id):
        flash("You have already voted.", "danger"); return redirect(url_for("vote"))

    try:
        record_vote(user_id, cid)
        # store last voted info for thank-you page
        session['last_voted_user'] = user_id
        session['last_voted_candidate'] = cid
        return redirect(url_for("thankyou"))
    except Exception as e:
        flash(f"Error recording vote: {e}", "danger"); return redirect(url_for("vote"))

@app.route("/thankyou")
def thankyou():
    user = session.pop('last_voted_user', None)
    candidate_id = session.pop('last_voted_candidate', None)
    candidate_name = None
    if candidate_id:
        cand = get_candidate_by_id(candidate_id)
        candidate_name = cand['name'] if cand else None
    return render_template("thankyou.html", user_id=user, candidate_name=candidate_name)

# ----- admin -----
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **k):
        if not session.get("is_admin"):
            flash("Admin login required.", "danger"); return redirect(url_for("admin_login"))
        return fn(*a, **k)
    return wrapper

@app.route("/admin_login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        if u == ADMIN_USER and p == ADMIN_PASS:
            session.clear(); session['is_admin'] = True
            flash("Admin logged in.", "success"); return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials.", "danger"); return redirect(url_for("admin_login"))
    return render_template("admin_login.html")

@app.route("/admin_logout")
def admin_logout():
    session.clear(); flash("Admin logged out.", "success"); return redirect(url_for("index"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

@app.route("/admin/positions", methods=["GET","POST"])
@admin_required
def admin_positions():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        if not name:
            flash("Position name required.", "danger"); return redirect(url_for("admin_positions"))
        try:
            create_position(name)
            flash("Position added.", "success")
        except Exception as e:
            flash(f"Error adding position: {e}", "danger")
        return redirect(url_for("admin_positions"))
    positions = get_positions()
    return render_template("admin_positions.html", positions=positions)

@app.route("/admin/candidates", methods=["GET","POST"])
@admin_required
def admin_candidates():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        position_id = request.form.get("position_id") or None
        bio = request.form.get("bio","").strip()
        logo = request.files.get("logo")
        if not name:
            flash("Candidate name required.", "danger"); return redirect(url_for("admin_candidates"))
        logo_rel = None
        if logo and logo.filename:
            if not allowed_logo(logo.filename):
                flash("Unsupported logo type.", "danger"); return redirect(url_for("admin_candidates"))
            try:
                logo_rel = save_logo_file(logo)
            except Exception as e:
                flash(f"Failed to save logo: {e}", "danger"); return redirect(url_for("admin_candidates"))
        try:
            pos_int = int(position_id) if position_id else None
        except:
            pos_int = None
        try:
            create_candidate(name, pos_int, bio, logo_rel)
            flash("Candidate added.", "success")
        except Exception as e:
            flash(f"Error adding candidate: {e}", "danger")
        return redirect(url_for("admin_candidates"))

    positions = get_positions()
    candidates = get_candidates()
    pos_map = {p['id']: p['name'] for p in positions}
    return render_template("admin_candidates.html", candidates=candidates, positions=positions, pos_map=pos_map)

@app.route("/admin/candidate_edit/<int:candidate_id>", methods=["GET","POST"])
@admin_required
def admin_candidate_edit(candidate_id):
    conn = sqlite3.connect(os.path.join(BASE_DIR, "database.db"))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    cand = cur.fetchone()
    if not cand:
        conn.close(); flash("Candidate not found.", "danger"); return redirect(url_for("admin_candidates"))
    if request.method == "POST":
        name = request.form.get("name","").strip()
        position_id = request.form.get("position_id") or None
        bio = request.form.get("bio","").strip()
        logo = request.files.get("logo")
        if not name:
            flash("Candidate name required.", "danger"); return redirect(url_for("admin_candidate_edit", candidate_id=candidate_id))
        logo_rel = cand["logo_path"]
        if logo and logo.filename:
            if not allowed_logo(logo.filename):
                flash("Unsupported logo type.", "danger"); return redirect(url_for("admin_candidate_edit", candidate_id=candidate_id))
            try:
                new_rel = save_logo_file(logo)
                logo_rel = new_rel
                # delete old file if exists
                if cand["logo_path"]:
                    oldp = os.path.join(BASE_DIR, "static", cand["logo_path"])
                    try: os.remove(oldp)
                    except: pass
            except Exception as e:
                flash(f"Failed to save logo: {e}", "danger"); return redirect(url_for("admin_candidate_edit", candidate_id=candidate_id))
        try:
            pos_int = int(position_id) if position_id else None
        except:
            pos_int = None
        try:
            cur.execute("""
                UPDATE candidates SET name=?, position_id=?, bio=?, logo_path=? WHERE id=?
            """, (name, pos_int, bio, logo_rel, candidate_id))
            conn.commit()
            flash("Candidate updated.", "success")
        except Exception as e:
            flash(f"Update error: {e}", "danger")
        conn.close()
        return redirect(url_for("admin_candidates"))
    conn.close()
    positions = get_positions()
    return render_template("admin_candidate_edit.html", cand=cand, positions=positions)

@app.route("/admin/candidate_delete/<int:candidate_id>", methods=["POST"])
@admin_required
def admin_candidate_delete(candidate_id):
    conn = sqlite3.connect(os.path.join(BASE_DIR, "database.db"))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
    cand = cur.fetchone()
    if not cand:
        conn.close(); flash("Candidate not found.", "danger"); return redirect(url_for("admin_candidates"))
    try:
        # delete logo file
        if cand["logo_path"]:
            try: os.remove(os.path.join(BASE_DIR, "static", cand["logo_path"]))
            except: pass
        cur.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        cur.execute("DELETE FROM votes WHERE candidate_id = ?", (candidate_id,))
        conn.commit()
        flash("Candidate and related votes deleted.", "success")
    except Exception as e:
        flash(f"Deletion error: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_candidates"))

@app.route("/results")
@admin_required
def results():
    candidates = get_candidates()
    conn = sqlite3.connect(os.path.join(BASE_DIR, "database.db"))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, candidate_id FROM votes ORDER BY id")
    votes = cur.fetchall()
    conn.close()
    cand_map = {c['id']: c['name'] for c in candidates}
    votes_display = [{"user_id": r["user_id"], "candidate_id": r["candidate_id"], "candidate_name": cand_map.get(r["candidate_id"], str(r["candidate_id"]))} for r in votes]
    return render_template("results.html", candidates=candidates, votes=votes_display)

@app.route("/admin/export_csv")
@admin_required
def admin_export_csv():
    conn = sqlite3.connect(os.path.join(BASE_DIR, "database.db"))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT v.id as vote_id, v.user_id, v.candidate_id, c.name as candidate_name, p.name as position_name
        FROM votes v
        LEFT JOIN candidates c ON v.candidate_id = c.id
        LEFT JOIN positions p ON c.position_id = p.id
        ORDER BY v.id
    """)
    rows = cur.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["vote_id","user_id","candidate_id","candidate_name","position_name"])
    for r in rows:
        writer.writerow([r["vote_id"], r["user_id"], r["candidate_id"], r["candidate_name"], r["position_name"]])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=results.csv"})

# ----- logout -----
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))

# ----- run -----
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
