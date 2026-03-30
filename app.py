import os
import psycopg2
import datetime
import time
import math
from typing import Optional
from flask import Flask, flash, redirect, render_template, request, session, send_from_directory, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta
from uuid import uuid4
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, static_folder=".", static_url_path="", template_folder=".")

# Session configuration - use Flask's built-in secure cookies
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_NAME"] = "session"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set to False for development over HTTP, True for HTTPS in production
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-2026-change-in-production")

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

SLIDES_DIR = os.path.join(app.config["UPLOAD_FOLDER"], "slideshow")
os.makedirs(SLIDES_DIR, exist_ok=True)

@app.before_request
def make_session_permanent():
    """Make session permanent on every request"""
    session.permanent = True
    app.logger.debug(f"Session data: {dict(session)}")

def get_db_config():
    config = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "sslmode": os.getenv("DB_SSLMODE", "require"),  # Neon requires SSL
    }
    env_names = {
        "host": "DB_HOST",
        "database": "DB_NAME",
        "user": "DB_USER",
        "password": "DB_PASSWORD",
    }
    missing = [env_names[name] for name, value in config.items() if name in env_names and not value]
    if missing:
        missing_vars = ", ".join(missing)
        raise RuntimeError(
            f"Database configuration is missing. Set these environment variables: {missing_vars}."
        )
    return config

def get_db():
    return psycopg2.connect(**get_db_config())

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                parent_id INTEGER,
                max_children INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        print("✓ Users table created")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Error creating users table: {e}")

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                category TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER REFERENCES users(id),
                title TEXT,
                description TEXT,
                cover_image TEXT
            );
        """)
        conn.commit()
        print("✓ Uploads table created")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Error creating uploads table: {e}")

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                data BYTEA NOT NULL,
                expiry TIMESTAMP NOT NULL
            );
        """)
        conn.commit()
        print("✓ Sessions table created")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Error creating sessions table: {e}")

    conn.close()
    print("Database initialization complete!")

# Initialize database on app startup
try:
    init_db()
except Exception as e:
    print(f"⚠ Warning: Database initialization failed on startup: {e}")
    print("Tables may not exist. Visit /init to create them manually.")

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.root_path, "favicon.ico", mimetype="image/x-icon")

@app.route("/init")
def init_route():
    try:
        init_db()
        return "Database initialized successfully!"
    except Exception as e:
        return f"Error: {e}", 500
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

def get_paginated_category(category, page, per_page=16):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, url, title, description, category, cover_image
            FROM uploads
            WHERE category = %s
            ORDER BY created_at DESC
        """, (category,))
        items = cursor.fetchall()
        conn.close()
    except psycopg2.Error as e:
        app.logger.error(f"Database error while loading category '{category}': {e}")
        return [], 1

    total_pages = max(1, math.ceil(len(items) / per_page))
    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total_pages

def get_paginated_all(page, per_page=16):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, url, title, description, category, cover_image
            FROM uploads
            ORDER BY created_at DESC
        """)
        items = cursor.fetchall()
        conn.close()
    except psycopg2.Error as e:
        app.logger.error(f"Database error while loading all uploads: {e}")
        return [], 1

    total_pages = max(1, math.ceil(len(items) / per_page))
    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total_pages

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")

        if not username or not password or not confirm:
            flash("All fields required", "error")
            return redirect("/register")

        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect("/register")

        hashed = generate_password_hash(password)
        parent_id = session.get("user_id")

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (username, password, parent_id)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (username, hashed, parent_id))
            user_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            session["user_id"] = user_id
            session["username"] = username
            flash(f"Account created successfully! Welcome, {username}!", "success")
            return redirect("/")
        except psycopg2.Error:
            flash("Username already exists", "error")
            conn.close()
            return redirect("/register")
    
    return render_template("register.html", username=session.get("username"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password required", "error")
            return redirect("/login")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        conn.close()

        if row is None or not check_password_hash(row[2], password):
            flash("Invalid username or password", "error")
            return redirect("/login")

        session["user_id"] = row[0]
        session["username"] = row[1]
        flash(f"Welcome, {username}!", "success")
        return redirect("/")

    return render_template("login.html", username=session.get("username"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/")

@app.route("/")
def index():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("home", page)

    return render_template("index.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("username"))

@app.route("/slideshows")
def slideshows():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("slideshows", page)

    return render_template("slideshows.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("username"))

@app.route("/about")
def about():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("about", page)
    
    return render_template("about.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("username"))

@app.route("/adminpanel")
@login_required
def adminpanel():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_all(page)
    conn = get_db()
    cursor = conn.cursor()
    conn.close()
    return render_template("adminpanel.html", username=session.get("username"), uploads=uploads, page=page, total_pages=total_pages)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        url = request.form.get("url")
        category = request.form.get("category")
        image = request.files.get("cover_image")

        if not url or not category or not title:
            flash("Title, URL, and category required", "error")
            return redirect("/upload")

        public_url = None
        if image and image.filename:
            if supabase is None:
                flash("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.", "error")
                return redirect("/upload")

            filename = secure_filename(image.filename)
            unique_name = f"{uuid4()}-{filename}"
            file_bytes = image.read()

            result = supabase.storage.from_("uploads").upload(unique_name, file_bytes)
            if isinstance(result, dict) and "error" in result:
                flash("Failed to upload image to storage", "error")
                return redirect("/upload")

            public_url = supabase.storage.from_("uploads").get_public_url(unique_name)

        # Save metadata + public image URL in Neon DB
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO uploads (url, category, user_id, title, description, cover_image)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (url, category, session["user_id"], title, description, public_url))
        conn.commit()
        conn.close()

        flash("URL uploaded successfully!", "success")
        # Redirect to the correct page
        if category == "home":
            return redirect("/")
        else:
            return redirect(f"/{category}")

    # GET request: load existing uploads + slideshow
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description, category, cover_image
        FROM uploads
        ORDER BY created_at DESC
    """)
    uploads = cursor.fetchall()
    conn.close()

    return render_template("adminpanel.html", username=session.get("username"), uploads=uploads)
  
@app.route("/delete-url/<int:url_id>")
@login_required
def delete_url(url_id):
    conn = get_db()
    cursor = conn.cursor()

    # Get category so we can redirect back to the correct page
    cursor.execute("SELECT category FROM uploads WHERE id = %s", (url_id,))
    row = cursor.fetchone()

    if not row:
        flash("URL not found", "error")
        return redirect("/")

    category = row[0]

    cursor.execute("DELETE FROM uploads WHERE id = %s", (url_id,))
    conn.commit()
    conn.close()

    flash("URL deleted", "success")
    # Redirect to the correct page
    if category == "home":
        return redirect("/")
    else:
        return redirect(f"/{category}")

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    init_db()
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
