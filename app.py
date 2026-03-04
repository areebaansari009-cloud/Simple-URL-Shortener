from flask import Flask, request, jsonify, redirect, render_template_string, abort
from flask_cors import CORS
import sqlite3
import string
import random
import os
import re
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)


# Configuration
DATABASE = 'urls.db'
SHORT_CODE_LENGTH = 6
BASE_URL = os.environ.get('RAILWAY_STATIC_URL', '')

def get_db():
    """Database connection helper - automatically closes connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # This creates a data directory.
    return conn

def init_db():
    """Initialize SQLite database with URLs table"""
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code TEXT UNIQUE NOT NULL,
                    original_url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    clicks INTEGER DEFAULT 0
                )
            ''')
            conn.commit()
        print("✅ Database is ready!")
    except sqlite3.Error as e:
        print(f"❌ Problem in database: {e}")
        raise
        init_db()

def is_valid_short_code(code):
    """Only numbers and letters are allowed for security"""
    return bool(re.match(r'^[a-zA-Z0-9]+$', code))

def generate_short_code(length=SHORT_CODE_LENGTH, max_attempts=10):
    """
    It generate unique code. If collision will occur then will try again
    """
    characters = string.ascii_letters + string.digits
    
    for attempt in range(max_attempts):
        code = ''.join(random.choices(characters, k=length))
        
        try:
            with get_db() as conn:
                c = conn.cursor()
                # first try to insert - if it will not unique then the error will occur
                c.execute(
                    'INSERT INTO urls (short_code, original_url, clicks) VALUES (?, ?, ?)',
                    (code, 'PENDING', 0)
                )
                conn.commit()
                return code
        except sqlite3.IntegrityError:
            # code already exists... so try again
            continue
    
    # After trying 10 times it won't happen then error
    raise Exception("Unique code banane mein nakaami!")

def normalize_url(url):
    """Keep URL in correct format"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def is_valid_url(url):
    """Check weather the URL is correct or wrong"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

@app.route('/')
def index():
    """Serve the frontend HTML page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/shorten', methods=['POST'])
def shorten_url():
    """API endpoint to create short URL"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL chahiye bhai!'}), 400
    
    # correct the URL
    original_url = normalize_url(data['url'])
    
    # make it Validate 
    if not is_valid_url(original_url):
        return jsonify({'error': 'wrong URL format'}), 400
    
    # Check that this URL already exists or not 
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT short_code FROM urls WHERE original_url = ?', (original_url,))
        existing = c.fetchone()
        
        if existing:
            short_code = existing['short_code']
            return jsonify({
                'short_code': short_code,
                'short_url': request.host_url + short_code,
                'original_url': original_url,
                'created': False,
                'message': 'This URL already exists'
            }), 200
    
    # Make new code
    try:
        short_code = generate_short_code()
    except Exception:
        return jsonify({'error': 'Server is busy, try in a while'}), 503
    
    # Update it's database (real URL instead of PENDING )
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                'UPDATE urls SET original_url = ? WHERE short_code = ?',
                (original_url, short_code)
            )
            conn.commit()
            
            return jsonify({
                'short_code': short_code,
                'short_url': f'{BASE_URL}/{short_code}',
                'original_url': original_url,
                'created': True
            }), 201
            
    except sqlite3.Error:
        return jsonify({'error': 'Database mein masla aa gaya'}), 500

@app.route('/<short_code>')
def redirect_to_url(short_code):
    """Redirect short code to original URL"""
    # Security check: only alphanumeric codes are allow
    if not is_valid_short_code(short_code):
        abort(404)
    
    with get_db() as conn:
        c = conn.cursor()
        
        # First check is code exist 
        c.execute('SELECT original_url FROM urls WHERE short_code = ?', (short_code,))
        result = c.fetchone()
        
        if not result:
            conn.close()
            abort(404)
        
        original_url = result['original_url']
        
        # Click count increase (atomic operation)
        c.execute('UPDATE urls SET clicks = clicks + 1 WHERE short_code = ?', (short_code,))
        conn.commit()
        
        return redirect(original_url)

@app.route('/api/stats/<short_code>')
def get_stats(short_code):
    """Get statistics for a short URL"""
    if not is_valid_short_code(short_code):
        return jsonify({'error': 'Galat short code'}), 400
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT original_url, created_at, clicks FROM urls WHERE short_code = ?', (short_code,))
        result = c.fetchone()
        
        if result:
            return jsonify({
                'short_code': short_code,
                'original_url': result['original_url'],
                'created_at': result['created_at'],
                'clicks': result['clicks']
            }), 200
        return jsonify({'error': 'Short code not found'}), 404

# Beautiful Frontend HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URL Shortener - Make Links Tiny</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            width: 100%;
            max-width: 600px;
            animation: slideUp 0.6s ease-out;
        }
        
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5em;
        }
        
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        
        .input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        
        input[type="url"] {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s ease;
            outline: none;
        }
        
        input[type="url"]:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        button {
            padding: 15px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            white-space: nowrap;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .result {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
            display: none;
            animation: fadeIn 0.4s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .result.show {
            display: block;
        }
        
        .result-label {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .short-url {
            display: flex;
            align-items: center;
            gap: 10px;
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 2px solid #e0e0e0;
        }
        
        .short-url a {
            color: #667eea;
            text-decoration: none;
            font-size: 1.2em;
            font-weight: 600;
            flex: 1;
            word-break: break-all;
        }
        
        .copy-btn {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        
        .copy-btn:hover {
            background: #5568d3;
        }
        
        .copy-btn.copied {
            background: #48bb78;
        }
        
        .error {
            background: #fed7d7;
            color: #c53030;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            display: none;
            animation: shake 0.5s;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-10px); }
            75% { transform: translateX(10px); }
        }
        
        .error.show {
            display: block;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 30px;
            padding-top: 30px;
            border-top: 1px solid #e0e0e0;
        }
        
        .feature {
            text-align: center;
        }
        
        .feature-icon {
            font-size: 2em;
            margin-bottom: 10px;
        }
        
        .feature h3 {
            color: #333;
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        
        .feature p {
            color: #666;
            font-size: 0.8em;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin-left: 10px;
            vertical-align: middle;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @media (max-width: 480px) {
            .container {
                padding: 25px;
            }
            
            h1 {
                font-size: 1.8em;
            }
            
            .input-group {
                flex-direction: column;
            }
            
            button {
                width: 100%;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔗 URL Shortener</h1>
        <p class="subtitle">Transform long, ugly links into clean, shareable URLs</p>
        
        <div class="input-group">
            <input 
                type="url" 
                id="urlInput" 
                placeholder="Paste your long URL here (e.g., https://example.com/very/long/path )" 
                required
            >
            <button id="shortenBtn" onclick="shortenUrl()">
                Shorten
            </button>
        </div>
        
        <div id="error" class="error"></div>
        
        <div id="result" class="result">
            <div class="result-label">Your shortened URL</div>
            <div class="short-url">
                <a id="shortUrl" href="#" target="_blank"></a>
                <button class="copy-btn" id="copyBtn" onclick="copyToClipboard()">Copy</button>
            </div>
        </div>
        
        <div class="features">
            <div class="feature">
                <div class="feature-icon">⚡</div>
                <h3>Fast</h3>
                <p>Instant redirection</p>
            </div>
            <div class="feature">
                <div class="feature-icon">🔒</div>
                <h3>Secure</h3>
                <p>HTTPS encryption</p>
            </div>
            <div class="feature">
                <div class="feature-icon">📊</div>
                <h3>Trackable</h3>
                <p>Click analytics</p>
            </div>
        </div>
    </div>

    <script>
        const urlInput = document.getElementById('urlInput');
        const shortenBtn = document.getElementById('shortenBtn');
        const result = document.getElementById('result');
        const error = document.getElementById('error');
        const shortUrl = document.getElementById('shortUrl');
        const copyBtn = document.getElementById('copyBtn');

        // Allow Enter key to submit
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') shortenUrl();
        });

        async function shortenUrl() {
            const url = urlInput.value.trim();
            
            // Reset UI
            error.classList.remove('show');
            result.classList.remove('show');
            
            if (!url) {
                showError('Please enter a URL');
                return;
            }
            
            // Show loading
            const originalText = shortenBtn.innerHTML;
            shortenBtn.innerHTML = 'Shortening<span class="loading"></span>';
            shortenBtn.disabled = true;
            
            try {
                const response = await fetch('/api/shorten', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: url })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to shorten URL');
                }
                
                // Display result
                shortUrl.href = data.short_url;
                shortUrl.textContent = data.short_url;
                result.classList.add('show');
                
                // Reset button
                shortenBtn.innerHTML = originalText;
                shortenBtn.disabled = false;
                
            } catch (err) {
                showError(err.message);
                shortenBtn.innerHTML = originalText;
                shortenBtn.disabled = false;
            }
        }

        function showError(message) {
            error.textContent = message;
            error.classList.add('show');
        }

        function copyToClipboard() {
            const url = shortUrl.href;
            navigator.clipboard.writeText(url).then(() => {
                copyBtn.textContent = 'Copied!';
                copyBtn.classList.add('copied');
                
                setTimeout(() => {
                    copyBtn.textContent = 'Copy';
                    copyBtn.classList.remove('copied');
                }, 2000);
            }).catch(() => {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = url;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                
                copyBtn.textContent = 'Copied!';
                setTimeout(() => {
                    copyBtn.textContent = 'Copy';
                }, 2000);
            });
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)



