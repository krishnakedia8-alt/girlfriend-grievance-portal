from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
import os
from datetime import datetime
from functools import wraps
import resend

# Load environment variables
ADMIN_NAME = os.getenv("ADMIN_NAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
USER_NAME = os.getenv("USER_NAME")
USER_PASSWORD = os.getenv("USER_PASSWORD")

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_USER_RECEIVER = os.getenv("EMAIL_USER_RECEIVER")

PORTAL_URL = os.getenv("PORTAL_URL")
SECRET = os.getenv("FLASK_SECRET", "defaultsecret")

resend.api_key = RESEND_API_KEY

app = Flask(__name__)
app.secret_key = SECRET


###########################################################
# DATABASE INITIALIZATION
###########################################################
def init_db():
    with sqlite3.connect("grievances.db") as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS grievances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                mood TEXT,
                priority TEXT,
                resolved INTEGER DEFAULT 0,
                response TEXT DEFAULT '',
                created_at TEXT
            )
        """)
        conn.commit()


###########################################################
# LOGIN DECORATOR
###########################################################
def login_required(role):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session or session["user"] != role:
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return decorated
    return wrapper


###########################################################
# EMAIL FUNCTIONS (RESEND)
###########################################################
def send_admin_notification(title, mood, priority, desc):
    resend.Emails.send({
        "from": "noreply@grievance-portal.krishna",
        "to": ADMIN_NAME,
        "subject": f"New Grievance Submitted by {USER_NAME}",
        "html": f"""
        <h2>New Grievance</h2>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Mood:</strong> {mood}</p>
        <p><strong>Priority:</strong> {priority}</p>
        <p><strong>Description:</strong><br>{desc}</p>
        <br>
        <a href="{PORTAL_URL}/login">Open Dashboard</a>
        """
    })


def send_user_response(grievance_id, title, response_text, priority, resolved):
    status = "Resolved" if resolved else "Pending"
    resend.Emails.send({
        "from": "noreply@grievance-portal.krishna",
        "to": EMAIL_USER_RECEIVER,
        "subject": f"Response Received for: {title}",
        "html": f"""
        <h2>Your grievance has an update</h2>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Priority:</strong> {priority}</p>
        <p><strong>Status:</strong> {status}</p>
        <p><strong>Response:</strong></p>
        <p>{response_text}</p>
        """
    })


###########################################################
# ROUTES
###########################################################
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        if u == USER_NAME and p == USER_PASSWORD:
            session["user"] = USER_NAME
            return redirect(url_for("submit"))

        if u == ADMIN_NAME and p == ADMIN_PASSWORD:
            session["user"] = ADMIN_NAME
            return redirect(url_for("dashboard"))

        flash("Invalid login")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/submit", methods=["GET", "POST"])
@login_required(USER_NAME)
def submit():
    if request.method == "POST":
        title = request.form["title"]
        desc = request.form["description"]
        mood = request.form["mood"]
        priority = request.form["priority"]
        created_at = datetime.now().isoformat()

        with sqlite3.connect("grievances.db") as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO grievances (title, description, mood, priority, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (title, desc, mood, priority, created_at))
            conn.commit()
            gid = c.lastrowid

        send_admin_notification(title, mood, priority, desc)

        flash("Grievance submitted!")
        return redirect(url_for("thank_you"))

    return render_template("submit.html")


@app.route("/thank_you")
@login_required(USER_NAME)
def thank_you():
    return render_template("thankyou.html")


@app.route("/dashboard")
@login_required(ADMIN_NAME)
def dashboard():
    with sqlite3.connect("grievances.db") as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, mood, priority, resolved FROM grievances ORDER BY created_at DESC")
        data = c.fetchall()
    return render_template("dashboard.html", grievances=data)


@app.route("/view_all")
@login_required(ADMIN_NAME)
def view_all():
    with sqlite3.connect("grievances.db") as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM grievances ORDER BY created_at DESC")
        data = c.fetchall()
    return render_template("view_all.html", grievances=data)


@app.route("/respond/<int:gid>", methods=["POST"])
@login_required(ADMIN_NAME)
def respond(gid):
    response_text = request.form["response"]

    with sqlite3.connect("grievances.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET response=? WHERE id=?", (response_text, gid))
        conn.commit()

        c.execute("SELECT title, priority, resolved FROM grievances WHERE id=?", (gid,))
        title, priority, resolved = c.fetchone()

    send_user_response(gid, title, response_text, priority, resolved)

    return redirect(url_for("dashboard"))


@app.route("/resolve/<int:gid>")
@login_required(ADMIN_NAME)
def resolve(gid):
    with sqlite3.connect("grievances.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET resolved=1 WHERE id=?", (gid,))
        conn.commit()

    return redirect(url_for("dashboard"))


###########################################################
# RUN SERVER
###########################################################
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
