from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_mail import Mail, Message
import sqlite3
import os
from functools import wraps
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path, override=True)

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_ADMIN')  # Your email
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')  # App password
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_DEFAULT_SENDER')  # Your email as the sender

mail = Mail(app)

USER_NAME = os.environ.get('USER_NAME')
USER_PASSWORD = os.environ.get('USER_PASSWORD')
ADMIN_NAME = os.environ.get('ADMIN_NAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
PORTAL_URL = os.environ.get('PORTAL_URL')

def init_db():
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS grievances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                mood TEXT,
                priority TEXT,
                resolved INTEGER DEFAULT 0,
                response TEXT DEFAULT ''
            )
        ''')
        conn.commit()

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
        user = request.form['username']
        pw = request.form['password']
        if user == USER_NAME and pw == USER_PASSWORD:
            session['user'] = USER_NAME
            return redirect(url_for('submit'))
        elif user == ADMIN_NAME and pw == ADMIN_PASSWORD:
            session['user'] = ADMIN_NAME
            return redirect(url_for('dashboard'))
        else:
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
        title = request.form['title']
        desc = request.form['description']
        mood = request.form['mood']
        priority = request.form['priority']
        with sqlite3.connect('grievances.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO grievances (title, description, mood, priority) VALUES (?, ?, ?, ?)",
                      (title, desc, mood, priority))
            conn.commit()
            grievance_id = c.lastrowid

        msg = Message("New Grievance from {} 💌".format(USER_NAME),
                      sender=os.environ.get('EMAIL_ADMIN'),
                      recipients=[os.environ.get('EMAIL_ADMIN')])
        msg.html = f"""
            <h3>New Grievance Submitted 💌</h3>
            <p><strong>Title:</strong> {title}</p>
            <p><strong>Mood:</strong> {mood}</p>
            <p><strong>Priority:</strong> {priority}</p>
            <p><strong>Description:</strong><br>{desc}</p>
            <hr>
            <p>Click below to respond:</p>
            <form action="https://sehaj-grievance-portal.up.railway.app/login" method="GET">
                <button type="submit" style="padding: 10px; background-color: pink; border: none; border-radius: 5px;">Respond 💌</button>
            </form>
        """
        mail.send(msg)

        flash('Grievance submitted! {} has been notified 💌'.format(ADMIN_NAME))
        return redirect(url_for('thank_you'))

    return render_template('submit.html')

def send_email_to_user(grievance_id, response):
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("SELECT title, priority, resolved FROM grievances WHERE id = ?", (grievance_id,))
        result = c.fetchone()

    if result:
        title, priority, resolved = result
        status = "Resolved ✅" if resolved == 1 else "Pending ❌"

        # Create the email message
        msg = Message("Grievance Response Received - Re: {}".format(title),
                    recipients=[os.environ.get('EMAIL_USER_RECEIVER')])

        msg.html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; color: #333;">
                <div style="background-color: #fff; padding: 20px; border-radius: 8px; width: 600px; margin: auto; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);">
                    <h2 style="color: #4CAF50;">Grievance Response Received</h2>
                    <p><strong>Title:</strong> {title}</p>
                    <p><strong>Priority:</strong> {priority}</p>
                    <p><strong>Status:</strong> {status}</p>
                    <hr>
                    <p><strong>Your Response:</strong></p>
                    <p style="background-color: #f9f9f9; padding: 10px; border-left: 4px solid #4CAF50; font-style: italic;">
                        {response}
                    </p>
                    <br>
                    <p style="color: #888;">This is an automated message from the Grievance Portal. Please do not reply.</p>
                </div>
            </body>
        </html>
        """

        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error sending email: {e}")

@app.route('/thankyou')
@login_required(USER_NAME)
def thank_you():
    return render_template('thankyou.html', user_display_name=USER_NAME, admin_display_name=ADMIN_NAME)

@app.route('/my_grievances')
@login_required(USER_NAME)
def my_grievances():
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("SELECT title, description, mood, priority, response, resolved FROM grievances")
        data = c.fetchall()
    return render_template('my_grievances.html', grievances=data)

@app.route('/view_grievances_admin')
@login_required(ADMIN_NAME)
def view_grievances_admin():
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("SELECT title, description, mood, priority, response, resolved FROM grievances")
        grievances = c.fetchall()
    return render_template('my_grievances.html', grievances=grievances)

@app.route('/respond/<int:gid>', methods=['POST'])
@login_required(ADMIN_NAME)
def respond(gid):
    response = request.form['response']
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET response = ? WHERE id = ?", (response, gid))
        conn.commit()

    send_email_to_user(gid, response)
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required(ADMIN_NAME)
def dashboard():
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM grievances")
        data = c.fetchall()
    return render_template('dashboard.html', grievances=data)

@app.route('/resolve/<int:gid>')
@login_required(ADMIN_NAME)
def resolve(gid):
    with sqlite3.connect('grievances.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE grievances SET resolved = 1 WHERE id = ?", (gid,))
        conn.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    try:
        from app import init_db
        init_db()
    except:
        pass
    app.run(host='0.0.0.0', port=5000)

