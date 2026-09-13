import os
from hpack import table
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

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.root_path, "favicon.ico", mimetype="image/x-icon")

def get_paginated_category(category, page, per_page=16):
    response = supabase.table("uploads") \
        .select("id, url, title, description, category, cover_image, created_at") \
        .eq("category", category) \
        .order("created_at", desc=True) \
        .execute()

    items = response.data or []
    total_pages = max(1, math.ceil(len(items) / per_page))
    start = (page - 1) * per_page
    end = start + per_page

    return items[start:end], total_pages

def get_paginated_all(page, per_page=16):
    response = supabase.table("uploads") \
    .select("id, url, title, description, category, cover_image, created_at") \
    .order("created_at", desc=True) \
    .execute()
    items = response.data or []
    total_pages = max(1, math.ceil(len(items) / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


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

        result = supabase.table("users").insert({
            "username": username,
            "password": hashed,
            "parent_id": parent_id
        }).execute()

        user_id = result.data[0]["id"]

        session["user_id"] = user_id
        session["username"] = username

        flash(f"Account created successfully! Welcome, {username}!", "success")
        return redirect("/")

    return render_template("register.html", username=session.get("username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password required", "error")
            return redirect("/login")

        result = supabase.table("users") \
            .select("id, username, password") \
            .eq("username", username) \
            .single() \
            .execute()

        row = result.data

        if row is None or not check_password_hash(row["password"], password):
            flash("Invalid username or password", "error")
            return redirect("/login")

        session["user_id"] = row["id"]
        session["username"] = row["username"]

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

@app.route("/opinions")
def opinions():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("opinions", page)

    return render_template("opinions.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("username"))

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

    return render_template(
        "adminpanel.html",
        username=session.get("username"),
        uploads=uploads,
        page=page,
        total_pages=total_pages
    )


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
            filename = secure_filename(image.filename)
            unique_name = f"{uuid4()}-{filename}"
            file_bytes = image.read()

            result = supabase.storage.from_("uploads").upload(unique_name, file_bytes)

            if isinstance(result, dict) and "error" in result:
                flash("Failed to upload image to storage", "error")
                return redirect("/upload")

            public_url = supabase.storage.from_("uploads").get_public_url(unique_name)

        supabase.table("uploads").insert({
            "url": url,
            "category": category,
            "user_id": session["user_id"],
            "title": title,
            "description": description,
            "cover_image": public_url
        }).execute()

        flash("URL uploaded successfully!", "success")

        if category == "home":
            return redirect("/")
        return redirect(f"/{category}")

    response = supabase.table("uploads") \
        .select("id, url, title, description, category, cover_image, created_at") \
        .order("created_at", desc=True) \
        .execute()

    uploads = response.data or []

    return render_template(
        "adminpanel.html",
        username=session.get("username"),
        uploads=uploads
    )



@app.route("/delete-url/<int:url_id>")
@login_required
def delete_url(url_id):
    supabase.table("uploads").delete().eq("id", url_id).execute()
    flash("URL deleted successfully", "success")
    return redirect(url_for("adminpanel"))

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
