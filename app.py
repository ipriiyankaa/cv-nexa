import os
import uuid
import sqlite3
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from analyzer import (
    parse_resume,
    analyze_keywords_detailed,
    generate_insights_and_questions,
    rewrite_bullet_with_ai,
    generate_pdf_report
)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure session key for login sessions
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB Max Upload Limit
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize SQLite Database for Users
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- AUTHENTICATION ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            if request.is_json:
                return jsonify({'error': 'All fields are required'}), 400
            return render_template('login.html', error="All fields are required")

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user'] = username
            if request.is_json:
                return jsonify({'success': True})
            return redirect(url_for('home'))
        
        if request.is_json:
            return jsonify({'error': 'Invalid username or password'}), 401
        return render_template('login.html', error="Invalid username or password")

    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() if request.is_json else request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()
        session['user'] = username
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists. Choose another.'}, 400)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- PROTECTED APP ROUTES ---
@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['user'])

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized. Please login.'}, 401)
    
    if 'resume' not in request.files:
        return jsonify({'error': 'Please upload a resume file.'}, 400)

    file = request.files['resume']
    job_desc = request.form.get('job_description', '')

    if file.filename == '' or not job_desc.strip():
        return jsonify({'error': 'Both Resume and Job Description are required.'}, 400)

    unique_name = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(file_path)

    try:
        resume_text = parse_resume(file_path)
        if not resume_text.strip():
            return jsonify({'error': 'Could not extract text. Ensure PDF is text-based.'}, 400)

        score, matched, missing, breakdown = analyze_keywords_detailed(resume_text, job_desc)
        insights = generate_insights_and_questions(resume_text, job_desc, missing)
        generate_pdf_report(score, matched, missing, insights, breakdown)

        return jsonify({
            'filename': file.filename,
            'match_score': score,
            'breakdown': breakdown,
            'matched_keywords': matched,
            'missing_keywords': missing,
            'ai_insights': insights
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/analyze-batch', methods=['POST'])
def analyze_batch():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}, 401)
    
    files = request.files.getlist('resumes')
    job_desc = request.form.get('job_description', '')

    if not files or files[0].filename == '':
        return jsonify({'error': 'Please select at least one resume file.'}, 400)
    if not job_desc.strip():
        return jsonify({'error': 'Job Description is required for ranking.'}, 400)

    results = []
    for file in files:
        unique_name = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(file_path)

        try:
            resume_text = parse_resume(file_path)
            score, matched, missing, breakdown = analyze_keywords_detailed(resume_text, job_desc)
            results.append({
                'filename': file.filename,
                'score': score,
                'keyword_score': breakdown['keyword_score'],
                'matched_count': len(matched),
                'missing_count': len(missing),
                'top_skills': matched[:5]
            })
        except Exception:
            results.append({
                'filename': file.filename,
                'score': 0,
                'keyword_score': 0,
                'matched_count': 0,
                'missing_count': 0,
                'top_skills': ['Unreadable file']
            })
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    results.sort(key=lambda x: x['score'])
    return jsonify({'ranked_resumes': results})

@app.route('/rewrite-bullet', methods=['POST'])
def rewrite():
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}, 401)
    
    data = request.get_json()
    bullet = data.get('bullet', '')
    if not bullet.strip():
        return jsonify({'error': 'Please enter a bullet point to optimize.'}, 400)

    rewritten = rewrite_bullet_with_ai(bullet)
    return jsonify({'rewritten': rewritten})

@app.route('/download-report')
def download_report():
    if 'user' not in session:
        return redirect(url_for('login'))
    return send_from_directory('static', 'resume_analysis_report.pdf', as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

    