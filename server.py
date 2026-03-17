from flask import Flask, request, jsonify, session, send_from_directory, redirect
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from datetime import datetime, timedelta
import os
import json
import re
import jwt

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = "ritb_secret_2024"

# Vercel Frontend URL for redirects (only for production)
FRONTEND_URL = os.environ.get(
    "FRONTEND_URL", "https://ritb-git-main-24icmee045-1722s-projects.vercel.app"
)


@app.errorhandler(404)
def not_found(e):
    path = request.path
    if path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    # For static files, try to serve locally first
    return send_from_directory(".", path if path != "/" else "index.html")


# ─── CORS: allow all Vercel URLs + localhost ───
allowed_origins = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    re.compile(r"^https://[\w\-]+\.vercel\.app$"),
]

CORS(
    app,
    supports_credentials=True,
    origins=allowed_origins,
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    expose_headers=["Content-Type"],
)

# ─── Session cookies: SameSite=None + Secure required for cross-domain ───
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
)

# Initialize database tables on startup (required for Gunicorn/Railway)
with app.app_context():
    init_db()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────── Helpers ───────────────────────────


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def create_token(user_id):
    payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")


def require_auth(roles=None):
    """Check JWT Token; return user dict or None."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]

    try:
        data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        user_id = data["user_id"]
    except Exception:
        return None

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    if not user:
        return None
    user = dict(user)
    if roles and user["role"] not in roles:
        return None
    return user


# ─────────────────────────── Static Files ───────────────────────────


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)


# ─────────────────────────── AUTH ───────────────────────────


@app.route("/api/auth/check", methods=["POST"])
def check_user():
    """Check if email exists; return role or 'new'."""
    data = request.json
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email required"}), 400
    db = get_db()
    user = db.execute(
        "SELECT id, role, name, status FROM users WHERE email = ?", (email,)
    ).fetchone()
    db.close()
    if user:
        return jsonify(
            {
                "exists": True,
                "role": user["role"],
                "name": user["name"],
                "status": user["status"],
            }
        )
    return jsonify({"exists": False})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    if user["status"] == "pending":
        return jsonify({"error": "Account pending admin approval"}), 403

    token = create_token(user["id"])

    return jsonify(
        {
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
                "status": user["status"],
            },
        }
    )


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logged out successfully"})


@app.route("/api/auth/me", methods=["GET"])
def me():
    user = require_auth()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    user.pop("password_hash", None)
    return jsonify(user)


@app.route("/api/auth/register/student", methods=["POST"])
def register_student():
    data = request.json
    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    password = data.get("password", "")
    student_id = data.get("student_id", "")
    program = data.get("program", "")
    year = data.get("year", "")
    if not all([email, name, password]):
        return jsonify({"error": "Email, name, and password are required"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "Email already registered"}), 409
    now = datetime.now().isoformat()
    try:
        db.execute(
            """INSERT INTO users (email, password_hash, role, name, status, student_id, program, year, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email,
                generate_password_hash(password),
                "student",
                name,
                "active",
                student_id,
                program,
                year,
                now,
            ),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        token = create_token(user["id"])
        db.close()
        return jsonify(
            {
                "message": "Registration successful",
                "token": token,
                "user": {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"],
                },
            }
        ), 201
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/register/teacher", methods=["POST"])
def register_teacher():
    data = request.json
    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    password = data.get("password", "")
    department = data.get("department", "")
    title = data.get("title", "")
    bio = data.get("bio", "")
    photo_url = data.get("photo_url", "")
    research_areas = data.get("research_areas", "")
    if not all([email, name, password]):
        return jsonify({"error": "Email, name, and password are required"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "Email already registered"}), 409
    now = datetime.now().isoformat()
    try:
        db.execute(
            """INSERT INTO users (email, password_hash, role, name, status, created_at)
                      VALUES (?, ?, ?, ?, ?, ?)""",
            (email, generate_password_hash(password), "teacher", name, "pending", now),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.execute(
            """INSERT INTO faculty (user_id, name, title, department, bio, photo_url, email, research_areas)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"],
                name,
                title,
                department,
                bio,
                photo_url,
                email,
                research_areas,
            ),
        )
        db.commit()
        db.close()
        return jsonify(
            {"message": "Registration submitted. Pending admin approval."}
        ), 201
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────── NEWS ───────────────────────────


@app.route("/api/news", methods=["GET"])
def get_news():
    db = get_db()
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    query = """SELECT n.*, u.name as author_name FROM news n
               LEFT JOIN users u ON n.author_id = u.id"""
    params = []
    conditions = []
    if category and category != "All":
        conditions.append("n.category = ?")
        params.append(category)
    if search:
        conditions.append("(n.title LIKE ? OR n.excerpt LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY n.published_at DESC"
    articles = rows_to_list(db.execute(query, params).fetchall())
    db.close()
    return jsonify(articles)


@app.route("/api/news/<int:news_id>", methods=["GET"])
def get_news_item(news_id):
    db = get_db()
    article = db.execute(
        """SELECT n.*, u.name as author_name FROM news n
                            LEFT JOIN users u ON n.author_id = u.id
                            WHERE n.id = ?""",
        (news_id,),
    ).fetchone()
    db.close()
    if not article:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row_to_dict(article))


@app.route("/api/news", methods=["POST"])
def create_news():
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    now = datetime.now().isoformat()
    extra_images = json.dumps(data.get("extra_images", []))
    db = get_db()
    db.execute(
        """INSERT INTO news (title, category, content, excerpt, image_url, extra_images, author_id, published_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("title"),
            data.get("category", "General"),
            data.get("content"),
            data.get("excerpt"),
            data.get("image_url"),
            extra_images,
            user["id"],
            now,
        ),
    )
    db.commit()
    news_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return jsonify({"message": "Article created", "id": news_id}), 201


@app.route("/api/news/<int:news_id>", methods=["PUT", "PATCH"])
def update_news(news_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    article = db.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if not article:
        db.close()
        return jsonify({"error": "Not found"}), 404
    if user["role"] != "admin" and article["author_id"] != user["id"]:
        db.close()
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    extra_images = (
        json.dumps(data.get("extra_images", []))
        if "extra_images" in data
        else article["extra_images"]
    )
    db.execute(
        """UPDATE news SET title=?, category=?, content=?, excerpt=?, image_url=?, extra_images=? WHERE id=?""",
        (
            data.get("title", article["title"]),
            data.get("category", article["category"]),
            data.get("content", article["content"]),
            data.get("excerpt", article["excerpt"]),
            data.get("image_url", article["image_url"]),
            extra_images,
            news_id,
        ),
    )
    db.commit()
    db.close()
    return jsonify({"message": "Updated"})


@app.route("/api/news/<int:news_id>", methods=["DELETE"])
def delete_news(news_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    article = db.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    if not article:
        db.close()
        return jsonify({"error": "Not found"}), 404
    if user["role"] != "admin" and article["author_id"] != user["id"]:
        db.close()
        return jsonify({"error": "Forbidden"}), 403
    db.execute("DELETE FROM news WHERE id = ?", (news_id,))
    db.commit()
    db.close()
    return jsonify({"message": "Deleted"})


# ─────────────────────────── EVENTS ───────────────────────────


@app.route("/api/events", methods=["GET"])
def get_events():
    db = get_db()
    category = request.args.get("category", "")
    query = """SELECT e.*, u.name as organizer_name FROM events e
               LEFT JOIN users u ON e.organizer_id = u.id"""
    params = []
    if category and category != "All":
        query += " WHERE e.category = ?"
        params.append(category)
    query += " ORDER BY e.event_date ASC"
    events = rows_to_list(db.execute(query, params).fetchall())
    db.close()
    return jsonify(events)


@app.route("/api/events/<int:event_id>", methods=["GET"])
def get_event(event_id):
    db = get_db()
    event = db.execute(
        """SELECT e.*, u.name as organizer_name FROM events e
                          LEFT JOIN users u ON e.organizer_id = u.id
                          WHERE e.id = ?""",
        (event_id,),
    ).fetchone()
    db.close()
    if not event:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row_to_dict(event))


@app.route("/api/events", methods=["POST"])
def create_event():
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    now = datetime.now().isoformat()
    reg = data.get("registered_students", [])
    extra_images = json.dumps(data.get("extra_images", []))
    db = get_db()
    db.execute(
        """INSERT INTO events (title, category, event_date, time_start, time_end, location, description, image_url, extra_images, organizer_id, registered_students, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("title"),
            data.get("category", "General"),
            data.get("event_date"),
            data.get("time_start"),
            data.get("time_end"),
            data.get("location"),
            data.get("description"),
            data.get("image_url"),
            extra_images,
            user["id"],
            json.dumps(reg),
            now,
        ),
    )
    db.commit()
    event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return jsonify({"message": "Event created", "id": event_id}), 201


@app.route("/api/events/<int:event_id>", methods=["PUT", "PATCH"])
def update_event(event_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        db.close()
        return jsonify({"error": "Not found"}), 404
    if user["role"] != "admin" and event["organizer_id"] != user["id"]:
        db.close()
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    reg = data.get("registered_students", None)
    reg_json = json.dumps(reg) if reg is not None else event["registered_students"]
    extra_images = (
        json.dumps(data.get("extra_images", []))
        if "extra_images" in data
        else (event["extra_images"] or "[]")
    )
    db.execute(
        """UPDATE events SET title=?, category=?, event_date=?, time_start=?, time_end=?, location=?, description=?, image_url=?, extra_images=?, registered_students=? WHERE id=?""",
        (
            data.get("title", event["title"]),
            data.get("category", event["category"]),
            data.get("event_date", event["event_date"]),
            data.get("time_start", event["time_start"]),
            data.get("time_end", event["time_end"]),
            data.get("location", event["location"]),
            data.get("description", event["description"]),
            data.get("image_url", event["image_url"]),
            extra_images,
            reg_json,
            event_id,
        ),
    )
    db.commit()
    db.close()
    return jsonify({"message": "Updated"})


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        db.close()
        return jsonify({"error": "Not found"}), 404
    if user["role"] != "admin" and event["organizer_id"] != user["id"]:
        db.close()
        return jsonify({"error": "Forbidden"}), 403
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    db.close()
    return jsonify({"message": "Deleted"})


# ─────────────────────────── FACULTY ───────────────────────────


@app.route("/api/faculty", methods=["GET"])
def get_faculty():
    db = get_db()
    department = request.args.get("department", "")
    search = request.args.get("search", "")
    query = "SELECT * FROM faculty"
    params = []
    conditions = []
    if department and department != "All":
        conditions.append("department = ?")
        params.append(department)
    if search:
        conditions.append("(name LIKE ? OR department LIKE ? OR research_areas LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY name ASC"
    faculty = rows_to_list(db.execute(query, params).fetchall())
    for f in faculty:
        try:
            f["publications"] = json.loads(f.get("publications") or "[]")
            f["courses"] = json.loads(f.get("courses") or "[]")
        except Exception:
            f["publications"] = []
            f["courses"] = []
    db.close()
    return jsonify(faculty)


@app.route("/api/faculty/<int:faculty_id>", methods=["GET"])
def get_faculty_member(faculty_id):
    db = get_db()
    f = db.execute("SELECT * FROM faculty WHERE id = ?", (faculty_id,)).fetchone()
    db.close()
    if not f:
        return jsonify({"error": "Not found"}), 404
    f = dict(f)
    try:
        f["publications"] = json.loads(f.get("publications") or "[]")
        f["courses"] = json.loads(f.get("courses") or "[]")
    except Exception:
        f["publications"] = []
        f["courses"] = []
    return jsonify(f)


@app.route("/api/faculty", methods=["POST"])
def create_faculty():
    user = require_auth(["admin"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    db = get_db()
    db.execute(
        """INSERT INTO faculty (user_id, name, title, department, bio, photo_url, email, research_areas, publications, courses)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("user_id"),
            data.get("name"),
            data.get("title"),
            data.get("department"),
            data.get("bio"),
            data.get("photo_url"),
            data.get("email"),
            data.get("research_areas"),
            json.dumps(data.get("publications", [])),
            json.dumps(data.get("courses", [])),
        ),
    )
    db.commit()
    fac_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return jsonify({"message": "Faculty created", "id": fac_id}), 201


@app.route("/api/faculty/<int:faculty_id>", methods=["PUT", "PATCH"])
def update_faculty(faculty_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    fac = db.execute("SELECT * FROM faculty WHERE id = ?", (faculty_id,)).fetchone()
    if not fac:
        db.close()
        return jsonify({"error": "Not found"}), 404
    # Teachers can only edit their own profile
    if user["role"] != "admin" and fac["user_id"] != user["id"]:
        db.close()
        return jsonify({"error": "Forbidden"}), 403
    data = request.json
    db.execute(
        """UPDATE faculty SET name=?, title=?, department=?, bio=?, photo_url=?, email=?, research_areas=?, publications=?, courses=? WHERE id=?""",
        (
            data.get("name", fac["name"]),
            data.get("title", fac["title"]),
            data.get("department", fac["department"]),
            data.get("bio", fac["bio"]),
            data.get("photo_url", fac["photo_url"]),
            data.get("email", fac["email"]),
            data.get("research_areas", fac["research_areas"]),
            json.dumps(
                data.get("publications", json.loads(fac["publications"] or "[]"))
            ),
            json.dumps(data.get("courses", json.loads(fac["courses"] or "[]"))),
            faculty_id,
        ),
    )
    db.commit()
    db.close()
    return jsonify({"message": "Updated"})


@app.route("/api/faculty/<int:faculty_id>", methods=["DELETE"])
def delete_faculty(faculty_id):
    user = require_auth(["admin"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("DELETE FROM faculty WHERE id = ?", (faculty_id,))
    db.commit()
    db.close()
    return jsonify({"message": "Deleted"})


# ─────────────────────────── ADMIN ───────────────────────────


@app.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    user = require_auth(["admin"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending = db.execute(
        "SELECT COUNT(*) FROM users WHERE status = 'pending'"
    ).fetchone()[0]
    total_news = db.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    total_events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_faculty = db.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    db.close()
    return jsonify(
        {
            "total_users": total_users,
            "pending_approvals": pending,
            "total_news": total_news,
            "total_events": total_events,
            "total_faculty": total_faculty,
        }
    )


@app.route("/api/admin/users", methods=["GET"])
def admin_get_users():
    user = require_auth(["admin"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    users = rows_to_list(
        db.execute(
            "SELECT id, email, role, name, status, student_id, program, year, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    )
    db.close()
    return jsonify(users)


@app.route("/api/admin/users/<int:uid>", methods=["PATCH"])
def admin_update_user(uid):
    admin = require_auth(["admin"])
    if not admin:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    db = get_db()
    if "status" in data:
        db.execute("UPDATE users SET status = ? WHERE id = ?", (data["status"], uid))
    if "role" in data:
        db.execute("UPDATE users SET role = ? WHERE id = ?", (data["role"], uid))
    db.commit()
    db.close()
    return jsonify({"message": "Updated"})


@app.route("/api/admin/users/<int:uid>", methods=["DELETE"])
def admin_delete_user(uid):
    admin = require_auth(["admin"])
    if not admin:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    db.close()
    return jsonify({"message": "Deleted"})


# ─────────────────────────── UPLOAD ───────────────────────────


@app.route("/api/upload", methods=["POST"])
def upload_file():
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        return jsonify({"error": "Invalid file type"}), 400
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}{ext}"
    f.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({"url": f"/uploads/{filename}"})


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ─────────────────────────── Run ───────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n✓ Scholastic Pulse server running at http://localhost:5000")
    print("  Admin login: admin@ritb.edu / admin123")
    print("  Teacher login: sarah.jenkins@scholastic.edu / teacher123")
    print("  Student login: alex.student@scholastic.edu / student123\n")
    app.run(debug=True, port=5000)
