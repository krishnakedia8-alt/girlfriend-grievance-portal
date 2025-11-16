from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from flask_mail import Mail, Message
import sqlite3
import os
from functools import wraps
from dotenv import load_dotenv
from pathlib import Path
from collections import Counter

# Load .env only when running locally, never override Render env
env_path = Path('.') / '.env'
RUNNING_ON_RENDER = bool(os.environ.get('PORT')) or bool(os.environ.get('RENDER'))
if not RUNNING_ON_RENDER and env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_ADMIN')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_DEFAULT_SENDER')
mail = Mail(app)

# Auth and portal config
USER_NAME = os.environ.get('USER_NAME')
USER_PASSWORD = os.environ.get('USER_PASSWORD')
ADMIN_NAME = os.environ.get('ADMIN_NAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
PORTAL_URL = os.environ.get('PORTAL_URL', '')

DB_FILE = 'grievances.db'

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            )
        """)
        conn.commit()

# Ensure DB exists on import
try:
    if not os.path.exists(DB_FILE):
        init_db()
        print('Database created on import.')
except Exception as e:
    print('Database init on import failed:', e)

def login_required(role):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if 'user' not in session or session.get('user') != role:
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

@app.route('/')
def home():
    return render_template('home.html', user_display_name=USER_NAME)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username', '')
        pw = request.form.get('password', '')
        print('Login attempt for:', user, '| Env USER_NAME:', USER_NAME, '| Env ADMIN_NAME:', ADMIN_NAME)
        if user == USER_NAME and pw == USER_PASSWORD:
            session['user'] = USER_NAME
            return redirect(url_for('submit'))
        if user == ADMIN_NAME and pw == ADMIN_PASSWORD:
            session['user'] = ADMIN_NAME
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html', user_display_name=USER_NAME)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/submit', methods=['GET', 'POST'])
@login_required(USER_NAME)
def submit():
    if request.method == 'POST':
        title = request.form['title'].strip()
        desc = request.form['description'].strip()
        mood = request.form.get('mood', '🙂')
        priority = request.form.get('priority', 'Medium')

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO grievances (title, description, mood, priority) VALUES (?, ?, ?, ?)",
                (title, desc, mood, priority)
            )
            conn.commit()
            grievance_id = c.lastrowid

        # Email to admin
        try:
            msg = Message(
                f"New Grievance from {USER_NAME} 💌",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[os.environ.get('EMAIL_ADMIN')]
            )
            btn = f'{PORTAL_URL}/login' if PORTAL_URL else '#'
            msg.html = f"""
                <h3>New Grievance Submitted 💌</h3>
                <p><strong>Title:</strong> {title}</p>
                <p><strong>Mood:</strong> {mood}</p>
                <p><strong>Priority:</strong> {priority}</p>
                <p><strong>Description:</strong><br>{desc}</p>
                <hr>
                <a href="{btn}" style="padding:10px;background-color:pink;border:none;border-radius:6px;
                text-decoration:none;color:#222;">Respond 💌</a>
            """
            mail.send(msg)
        except Exception as e:
            print("Email send failed:", e)

        flash(f'Grievance submitted. {ADMIN_NAME} has been notified.')
        return redirect(url_for('thank_you'))

    return render_template('submit.html')

@app.route('/thankyou')
@login_required(USER_NAME)
def thank_you():
    return render_template('thankyou.html', user_display_name=USER_NAME, admin_display_name=ADMIN_NAME)

@app.route('/my_grievances')
@login_required(USER_NAME)
def my_grievances():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, description, mood, priority, response, resolved, created_at, resolved_at FROM grievances ORDER BY id DESC")
        data = c.fetchall()
    return render_template('my_grievances.html', grievances=data)

@app.route('/dashboard')
@login_required(ADMIN_NAME)
def dashboard():
    # quick stats for cards
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM grievances")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM grievances WHERE resolved = 1")
        resolved = c.fetchone()[0]
        c.execute("SELECT mood FROM grievances")
        moods = [row[0] for row in c.fetchall()]
        c.execute("SELECT priority FROM grievances")
        prios = [row[0] for row in c.fetchall()]
    mood_counts = Counter(moods)
    prio_counts = Counter(prios)
    return render_template('dashboard.html',
                           total=total,
                           resolved=resolved,
                           mood_counts=mood_counts,
                           prio_counts=prio_counts)

# Admin list with filters and search
@app.route('/view_all_grievances')
@login_required(ADMIN_NAME)
def view_all_grievances():
    q = request.args.get('q', '').strip()
    mood = request.args.get('mood', '')
    priority = request.args.get('priority', '')
    status = request.args.get('status', '')

    sql = "SELECT id, title, description, mood, priority, response, resolved, created_at, resolved_at FROM grievances WHERE 1=1"
    params = []

    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"
        params += [f'%{q}%', f'%{q}%']
    if mood:
        sql += " AND mood = ?"
        params.append(mood)
    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if status in ('open', 'closed'):
        sql += " AND resolved = ?"
        params.append(1 if status == 'closed' else 0)

    sql += " ORDER BY id DESC"

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(sql, params)
        rows = c.fetchall()

    return render_template('view_all_grievances.html', grievances=rows, q=q, mood=mood, priority=priority, status=status)

@app.route('/respond/<int:gid>', methods=['POST'])
@login_required(ADMIN_NAME)
def respond(gid):
    response = request.form['response'].strip()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET response = ? WHERE id = ?", (response, gid))
        conn.commit()
    # Notify user
    try:
        send_email_to_user(gid, response)
    except Exception as e:
        print("notify user failed:", e)
    return redirect(url_for('dashboard'))

@app.route('/resolve/<int:gid>')
@login_required(ADMIN_NAME)
def resolve(gid):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE id = ?", (gid,))
        conn.commit()
    return redirect(url_for('dashboard'))

@app.route('/analytics.json')
@login_required(ADMIN_NAME)
def analytics_json():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT mood, COUNT(*) FROM grievances GROUP BY mood")
        mood = dict(c.fetchall())
        c.execute("SELECT priority, COUNT(*) FROM grievances GROUP BY priority")
        prio = dict(c.fetchall())
        c.execute("SELECT resolved, COUNT(*) FROM grievances GROUP BY resolved")
        status_raw = dict(c.fetchall())
        status = {"open": status_raw.get(0, 0), "closed": status_raw.get(1, 0)}
    return jsonify({"mood": mood, "priority": prio, "status": status})

def send_email_to_user(grievance_id, response):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT title, priority, resolved FROM grievances WHERE id = ?", (grievance_id,))
        row = c.fetchone()
    if not row:
        return
    title, priority, resolved = row
    status = "Resolved" if resolved == 1 else "Pending"
    msg = Message(
        f"Grievance Response Received - Re: {title}",
        recipients=[os.environ.get('EMAIL_USER_RECEIVER')]
    )
    msg.html = f"""
        <h3>Grievance Response</h3>
        <p><strong>Title:</strong> {title}</p>
        <p><strong>Priority:</strong> {priority}</p>
        <p><strong>Status:</strong> {status}</p>
        <hr>
        <p><strong>Response:</strong></p>
        <p style="background:#f7f7f7;padding:10px;border-radius:6px;">{response}</p>
    """
    mail.send(msg)

if __name__ == '__main__':
    try:
        init_db()
        print("Database ensured in __main__.")
    except Exception as e:
        print("Database init in __main__ failed:", e)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
