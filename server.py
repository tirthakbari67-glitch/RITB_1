from flask import Flask, request, jsonify, session, send_from_directory, redirect
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from datetime import datetime, timedelta
import os
import json
import re
import jwt

if os.environ.get("VERCEL"):
    app = Flask(__name__)
else:
    app = Flask(__name__, static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ritb_secret_2024")

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


# ─── CORS: allow localhost + Vercel + Netlify URLs ───
allowed_origins = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    re.compile(r"^https://[\w\-]+\.vercel\.app$"),
    re.compile(r"^https://[\w\-]+\.netlify\.app$"),
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
    db = get_db()
    try:
        db.execute("DELETE FROM faculty WHERE id BETWEEN 1 AND 6")
        db.execute("DELETE FROM news WHERE id BETWEEN 1 AND 6")
        db.execute("DELETE FROM events WHERE id BETWEEN 1 AND 7")
        db.execute("DELETE FROM events WHERE title = 'hjklbon'")
        db.execute("DELETE FROM users WHERE email IN ('sarah.jenkins@scholastic.edu', 'alex.student@scholastic.edu')")
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

if os.environ.get("VERCEL"):
    UPLOAD_FOLDER = "/tmp/uploads"
else:
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


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    """Serve uploaded files from the uploads folder (with fallback to repository uploads)."""
    if os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return send_from_directory(UPLOAD_FOLDER, filename)
    repo_uploads = os.path.join(os.path.dirname(__file__), "uploads")
    if os.path.exists(os.path.join(repo_uploads, filename)):
        return send_from_directory(repo_uploads, filename)
    return jsonify({"error": "File not found"}), 404


# ─────────────────────────── FILE UPLOAD ───────────────────────────
import uuid

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload an image file. No auth required so faculty can upload during registration."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Use PNG, JPG, JPEG, GIF or WebP."}), 400
    # Limit file size to 5 MB
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 5 * 1024 * 1024:
        return jsonify({"error": "File too large. Maximum size is 5 MB."}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(save_path)

    # Return the URL relative to the server root
    url = f"/uploads/{filename}"
    return jsonify({"url": url, "filename": filename}), 201




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
    total_publications = int(data.get("total_publications", 0) or 0)
    experience = int(data.get("experience", 0) or 0)
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
            """INSERT INTO faculty (user_id, name, title, department, bio, photo_url, email, research_areas, total_publications, experience)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"],
                name,
                title,
                department,
                bio,
                photo_url,
                email,
                research_areas,
                total_publications,
                experience,
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
    # Only return ACTIVE faculty on the public directory
    query = "SELECT f.*, u.status as user_status FROM faculty f JOIN users u ON f.user_id = u.id WHERE u.status = 'active'"
    params = []
    if department and department != "All":
        query += " AND f.department = ?"
        params.append(department)
    if search:
        query += " AND (f.name LIKE ? OR f.department LIKE ? OR f.research_areas LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY f.name ASC"
    faculty = rows_to_list(db.execute(query, params).fetchall())
    for f in faculty:
        try:
            f["publications"] = json.loads(f.get("publications") or "[]")
            f["courses"] = json.loads(f.get("courses") or "[]")
        except Exception:
            f["publications"] = []
            f["courses"] = []
        # Hide bio if linked user account is still pending approval
        if f.get("user_status") == "pending":
            f["bio"] = None
    db.close()
    return jsonify(faculty)


@app.route("/api/faculty/<int:faculty_id>", methods=["GET"])
def get_faculty_member(faculty_id):
    db = get_db()
    row = db.execute(
        "SELECT f.*, u.status as user_status FROM faculty f LEFT JOIN users u ON f.user_id = u.id WHERE f.id = ?",
        (faculty_id,)
    ).fetchone()
    db.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    f = dict(row)
    try:
        f["publications"] = json.loads(f.get("publications") or "[]")
        f["courses"] = json.loads(f.get("courses") or "[]")
    except Exception:
        f["publications"] = []
        f["courses"] = []
    # Hide bio until admin approves the account
    if f.get("user_status") == "pending":
        f["bio"] = None
    return jsonify(f)


@app.route("/api/faculty/me", methods=["GET"])
def get_my_faculty_profile():
    """Return the logged-in teacher's own faculty profile (including pending accounts)."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    row = db.execute(
        "SELECT f.*, u.status as user_status FROM faculty f JOIN users u ON f.user_id = u.id WHERE f.user_id = ?",
        (user["id"],)
    ).fetchone()
    db.close()
    if not row:
        return jsonify(None)
    f = dict(row)
    try:
        f["publications"] = json.loads(f.get("publications") or "[]")
        f["courses"] = json.loads(f.get("courses") or "[]")
    except Exception:
        f["publications"] = []
        f["courses"] = []
    return jsonify(f)


@app.route("/api/events/my", methods=["GET"])
def get_my_events():
    """Return only the calling teacher's own events (server-side filter, no type-mismatch)."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    events = rows_to_list(
        db.execute(
            "SELECT * FROM events WHERE organizer_id = ? ORDER BY event_date DESC",
            (user["id"],),
        ).fetchall()
    )
    db.close()
    return jsonify(events)


@app.route("/api/news/my", methods=["GET"])
def get_my_news():
    """Return only the calling teacher's own news articles."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    articles = rows_to_list(
        db.execute(
            "SELECT * FROM news WHERE author_id = ? ORDER BY published_at DESC",
            (user["id"],),
        ).fetchall()
    )
    db.close()
    return jsonify(articles)



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
        """UPDATE faculty SET name=?, title=?, department=?, bio=?, photo_url=?, email=?, research_areas=?, publications=?, courses=?, total_publications=?, experience=? WHERE id=?""",
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
            int(data.get("total_publications", fac["total_publications"] or 0) or 0),
            int(data.get("experience", fac["experience"] or 0) or 0),
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


# ─────────────────────────── ATTENDANCE ───────────────────────────


@app.route("/api/events/<int:event_id>/attendance", methods=["GET"])
def get_attendance(event_id):
    """Return attendance list; auto-seeds from ALL students in the system if empty."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        db.close()
        return jsonify({"error": "Event not found"}), 404

    rows = rows_to_list(db.execute(
        "SELECT * FROM attendance WHERE event_id = ? ORDER BY student_name ASC", (event_id,)
    ).fetchall())

    # Auto-seed from the FULL student list if nothing exists yet
    if not rows:
        now = datetime.now().isoformat()
        all_students = rows_to_list(db.execute(
            "SELECT id, name, program, year FROM users WHERE role = 'student' AND status = 'active' ORDER BY name ASC"
        ).fetchall())
        for s in all_students:
            try:
                db.execute(
                    "INSERT OR IGNORE INTO attendance "
                    "(event_id, user_id, student_name, student_branch, student_year, status, marked_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (event_id, s["id"], s["name"], s.get("program") or "", s.get("year") or "", "absent", now)
                )
            except Exception:
                pass
        db.commit()
        rows = rows_to_list(db.execute(
            "SELECT * FROM attendance WHERE event_id = ? ORDER BY student_name ASC", (event_id,)
        ).fetchall())

    db.close()
    return jsonify(rows)


@app.route("/api/events/<int:event_id>/attendance/seed", methods=["POST"])
def seed_attendance(event_id):
    """Add a student to ALL events' attendance lists (cross-event sync)."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    students = data.get("students", [])  # [{name, branch, year}]
    now = datetime.now().isoformat()
    db = get_db()

    # Get all event IDs so we can sync to all of them
    all_event_ids = [r[0] for r in db.execute("SELECT id FROM events").fetchall()]

    added_this_event = 0
    for s in students:
        name   = (s.get("name")   or "").strip()
        branch = (s.get("branch") or "").strip()
        year   = (s.get("year")   or "").strip()
        if not name:
            continue
        # Insert into every event
        for eid in all_event_ids:
            try:
                db.execute(
                    "INSERT OR IGNORE INTO attendance "
                    "(event_id, student_name, student_branch, student_year, status, marked_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (eid, name, branch, year, "absent", now)
                )
                if eid == event_id:
                    added_this_event += db.execute("SELECT changes()").fetchone()[0]
            except Exception:
                pass
    db.commit()
    db.close()
    return jsonify({"message": f"Added student(s) across {len(all_event_ids)} event(s)", "added": added_this_event})


@app.route("/api/events/<int:event_id>/attendance/<int:att_id>", methods=["PATCH"])
def mark_attendance(event_id, att_id):
    """Update status/rank for this event only; if name/branch/year changed, sync across ALL events."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    now = datetime.now().isoformat()
    db = get_db()

    row = db.execute("SELECT * FROM attendance WHERE id=? AND event_id=?", (att_id, event_id)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Record not found"}), 404

    # ── Status (per-event only) ──
    new_status = data.get("status", row["status"])
    if new_status not in ("present", "absent"):
        db.close()
        return jsonify({"error": "Status must be 'present' or 'absent'"}), 400

    # ── Rank (per-event only, null clears it) ──
    valid_ranks = (None, "", "1st", "2nd", "3rd")
    new_rank = data.get("rank", row["rank"])  # keep existing if not sent
    if new_rank == "":  # explicit clear
        new_rank = None
    if new_rank not in valid_ranks:
        db.close()
        return jsonify({"error": "Rank must be 1st, 2nd, 3rd or empty"}), 400

    # ── Student details (sync across ALL events if changed) ──
    old_name   = row["student_name"] or ""
    new_name   = (data.get("student_name")   or old_name).strip()
    new_branch = (data.get("student_branch") or row["student_branch"] or "").strip()
    new_year   = (data.get("student_year")   or row["student_year"]   or "").strip()

    details_changed = (
        new_name != old_name or
        new_branch != (row["student_branch"] or "") or
        new_year   != (row["student_year"]   or "")
    )

    # Update this event's record (status + rank + details)
    db.execute(
        "UPDATE attendance "
        "SET status=?, rank=?, student_name=?, student_branch=?, student_year=?, marked_at=? "
        "WHERE id=? AND event_id=?",
        (new_status, new_rank, new_name, new_branch, new_year, now, att_id, event_id)
    )

    # If student details changed, propagate to all OTHER events
    if details_changed and old_name:
        db.execute(
            "UPDATE attendance "
            "SET student_name=?, student_branch=?, student_year=? "
            "WHERE student_name=? AND event_id != ?",
            (new_name, new_branch, new_year, old_name, event_id)
        )

    db.commit()
    db.close()
    return jsonify({"message": "Updated", "status": new_status, "rank": new_rank})


@app.route("/api/events/<int:event_id>/attendance/bulk", methods=["POST"])
def bulk_attendance(event_id):
    """Submit all attendance at once: [{id, status}, ...]"""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    records = data.get("records", [])
    now = datetime.now().isoformat()
    db = get_db()
    for rec in records:
        att_id = rec.get("id")
        status = rec.get("status", "absent")
        if status not in ("present", "absent") or not att_id:
            continue
        db.execute(
            "UPDATE attendance SET status=?, marked_at=? WHERE id=? AND event_id=?",
            (status, now, att_id, event_id)
        )
    db.commit()
    db.close()
    return jsonify({"message": "Attendance saved"})


@app.route("/api/events/<int:event_id>/attendance/<int:att_id>", methods=["DELETE"])
def delete_attendance(event_id, att_id):
    """Remove a student from ALL events' attendance lists (cross-event sync)."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    # Get student name first so we can delete across all events
    row = db.execute("SELECT student_name FROM attendance WHERE id=? AND event_id=?", (att_id, event_id)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Record not found"}), 404
    student_name = row["student_name"]
    # Delete from ALL events
    db.execute("DELETE FROM attendance WHERE student_name=?", (student_name,))
    db.commit()
    db.close()
    return jsonify({"message": f"'{student_name}' removed from all events"})


@app.route("/api/events/<int:event_id>/attendance/stats", methods=["GET"])
def attendance_stats(event_id):
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    total   = db.execute("SELECT COUNT(*) FROM attendance WHERE event_id=?", (event_id,)).fetchone()[0]
    present = db.execute("SELECT COUNT(*) FROM attendance WHERE event_id=? AND status='present'", (event_id,)).fetchone()[0]
    absent  = total - present
    db.close()
    return jsonify({"total": total, "present": present, "absent": absent})



# ─────────────────────────── SPOTLIGHT ───────────────────────────


@app.route("/api/spotlight", methods=["GET"])
def get_spotlight():
    """
    Return ranked students (rank != null) from events held in the last 30 days.
    Each entry: { event_id, event_title, event_date, student_name, student_branch,
                  student_year, rank, status }
    Ordered: event_date DESC, then rank (1st→2nd→3rd).
    """
    cutoff = (datetime.now() - timedelta(days=30)).date().isoformat()
    db = get_db()
    rows = rows_to_list(db.execute(
        """
        SELECT a.id, a.event_id, a.student_name, a.student_branch, a.student_year,
               a.rank, a.status,
               e.title AS event_title, e.event_date, e.location
        FROM attendance a
        JOIN events e ON e.id = a.event_id
        WHERE a.rank IS NOT NULL AND a.rank != ''
          AND e.event_date >= ?
        ORDER BY e.event_date DESC,
                 CASE a.rank WHEN '1st' THEN 1 WHEN '2nd' THEN 2 WHEN '3rd' THEN 3 ELSE 9 END
        """,
        (cutoff,)
    ).fetchall())
    db.close()
    return jsonify(rows)


@app.route("/api/top-performers", methods=["GET"])
def get_top_performers():
    """
    Top 3 students by attendance in the CURRENT calendar month.
    Groups by student_name across all events whose event_date starts
    with YYYY-MM of today. Auto-resets each new month. No auth needed.
    """
    month_prefix = datetime.now().strftime("%Y-%m")
    db = get_db()
    rows = rows_to_list(db.execute(
        """
        SELECT
            a.student_name,
            a.student_branch,
            a.student_year,
            COUNT(DISTINCT a.event_id)                                   AS total_events,
            SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END)       AS present_count,
            ROUND(
                100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END)
                      / CASE WHEN COUNT(DISTINCT a.event_id) = 0 THEN 1 ELSE COUNT(DISTINCT a.event_id) END, 1
            )                                                             AS attendance_pct
        FROM attendance a
        JOIN events e ON e.id = a.event_id
        WHERE e.event_date LIKE ?
        GROUP BY a.student_name, a.student_branch, a.student_year
        HAVING total_events > 0
        ORDER BY present_count DESC, attendance_pct DESC
        LIMIT 3
        """,
        (f"{month_prefix}%",)
    ).fetchall())
    db.close()
    medal_map = {0: "1st", 1: "2nd", 2: "3rd"}
    for i, row in enumerate(rows):
        row["rank"] = medal_map.get(i, f"#{i+1}")
    return jsonify(rows)


@app.route("/api/admin/attendance-overview", methods=["GET"])
def admin_attendance_overview():
    """Return all events with attendance counts, for the admin Attendance tab."""
    user = require_auth(["admin", "teacher"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    rows = rows_to_list(db.execute(
        """
        SELECT e.id, e.title, e.event_date, e.location,
               COUNT(a.id) AS total_students,
               SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present_count,
               SUM(CASE WHEN a.rank IS NOT NULL AND a.rank != '' THEN 1 ELSE 0 END) AS ranked_count
        FROM events e
        LEFT JOIN attendance a ON a.event_id = e.id
        GROUP BY e.id
        ORDER BY e.event_date DESC
        """
    ).fetchall())
    db.close()
    return jsonify(rows)


# ─────────────────────────── Run ───────────────────────────

if __name__ == "__main__":
    init_db()
    print("\n✓ Scholastic Pulse server running at http://localhost:5000")
    print("  Admin login: admin@ritb.edu / admin123\n")
    app.run(debug=True, port=5000)
