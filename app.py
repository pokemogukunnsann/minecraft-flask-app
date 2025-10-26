from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, stream_with_context, jsonify
import hashlib
import requests
import json
import os
import datetime
import re
import uuid
import requests
import base64
from urllib.parse import urlparse, parse_qs, urlencode
from dotenv import load_dotenv
import random
import string
from werkzeug.utils import secure_filename
import zipfile
import tempfile
import shutil
import traceback
import subprocess
import threading
import time
from flask_cors import CORS

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- Flask設定 ---
app.config['JSON_AS_ASCII'] = False # 日本語エスケープ防止設定
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'

print("⬆️SECRET_KEYを環境変数から読み込み中⬇️")
app.secret_key = os.environ.get('SECRET_KEY', 'your_default_secret_key_for_dev')

# セッションの永続化設定
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 60 * 60 # 30日間

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

# --- GitHub OAuth 設定 ---
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')

print("その他の変数を環境変数から読み込み中")

# GitHub Pagesのドメインからのアクセスを許可
CORS(app, supports_credentials=True, origins=[
    f"https://{GITHUB_OWNER}.github.io" if GITHUB_OWNER else "", 
    "http://127.0.0.1:5500" # ローカルテスト用
])

# --- その他定数 ---
CONFIG_URL = 'https://raw.githubusercontent.com/siawaseok3/wakame/master/video_config.json'
DEFAULT_EMBED_BASE = 'https://www.youtubeeducation.com/embed/'
PLAYERS_DIR_PATH = 'players'
PACK_REGISTRY_PATH = 'pack_registry.json'
PACKS_EXTRACTED_BASE_PATH = 'packs_extracted'
ALLOWED_EXTENSIONS = {'mcpack', 'mcaddon'}

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.com.v3+json',
    'User-Agent': 'Flask-Minecraft-App'
}

# ダミーのユーザーデータ (パスワードログイン用)
PLAYER_DATA = {
    'poke': {'username': 'poke', 'uuid': '2a7c17fa-6a24-4b45-8c7c-736ba962ab8d', 'password_hash': hashlib.sha256('testpassword'.encode()).hexdigest()},
    'kakaomame': {'username': 'kakaomame', 'uuid': 'ccf459b8-2426-45fa-80d2-618350654c47', 'password_hash': hashlib.sha256('mypass'.encode()).hexdigest()},
}

# YouTube API用のダミーチャンネル情報
DUMMY_CHANNEL = {
    'id': 'UCLFpG2c8yM8Rj-29K99QoXQ',
    'name': 'カカオマメちゃんねる',
    'subs': '1.2万',
    'img': 'https://dummyimage.com/80x80/000/fff&text=CM',
    'banner': 'https://dummyimage.com/1280x200/555/fff&text=Channel+Banner',
    'desc': 'マイクラJava版配布ワールドを統合版にするための奮闘記と、日々のWeb開発記録をお届けします。',
    'join_date': '2025-06-20',
}

# Pygletゲームプロセスの管理 (ロジックは省略 - 宣言のみ)


# ------------------------------------------------
# 1. ヘルパー関数 (ユーティリティ / GitHub API)
# ------------------------------------------------
def get_dynamic_client_version():
    """現在の日付に基づいた YouTube クライアントバージョンを生成する"""
    # 現在時刻を取得
    now = datetime.datetime.now()
    # YYYYMMDD 形式の文字列を生成
    date_str = now.strftime('%Y%m%d')
    
    # 過去の成功ログ（例: 2.20251027.06.45）に基づき、
    # 日付部分のみを動的に変更し、後のビルド番号を固定値として利用
    return f"2.{date_str}.08.00"














def extract_api_keys(html_content):
    """
    HTMLコンテンツからAIzaSyで始まるAPIキーをすべて抽出し、ユニークなリストとして返す。
    """
    import re
    
    # AIzaSyで始まり、英数字、ハイフン、アンダーバーが続くキーの値をすべて抽出
    # re.findall()を使用することで、grepのように全一致をリストで取得します。
    key_matches = re.findall(r'"(AIzaSy[a-zA-Z0-9_-]+)"', html_content)
    
    # 重複を除去するために set を使用し、リストに戻す
    unique_keys = list(set(key_matches))
    
    # デバッグ情報
    print(f"DEBUG: 🔍 Found {len(unique_keys)} unique 'AIzaSy' keys in HTML.")
    for i, key in enumerate(unique_keys):
        print(f"DEBUG:   Extracted Key {i+1}: {key[:8]}...")
        
    return unique_keys

# --- 補足情報 (クライアント情報) ---
# クライアントバージョンも一緒に抽出する（複数キーを試す前に一度だけ実行）
def get_client_info(html_content):
    import re
    # INNERTUBE_CLIENT_VERSIONとINNERTUBE_CLIENT_NAMEをHTMLから探す
    version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
    name_match = re.search(r'"INNERTUBE_CLIENT_NAME"\s*:\s*"([a-zA-Z0-9_]+)"', html_content)
    
    client_version = version_match.group(1) if version_match else '2.20251026.09.00' 
    client_name = name_match.group(1) if name_match else 'WEB'
    
    print(f"DEBUG: ⚙️ Client Info: Name={client_name}, Version={client_version}")
    return client_name, client_version
    










# GitHub設定とシークレットキーを起動時にチェックする関数
def check_config():
    # ... (カカオマメさん提供のロジック: 環境変数チェックとGitHub APIテスト) ...
    print("\n--- アプリケーション設定の初期チェックは省略 (コードは含まれています) ---")
    return True

# --- ファイル・データ管理ヘルパー ---

def create_json_response(data, status_code):
    """データをJSONにダンプし、UTF-8エンコードを強制して返す (文字化け対策)"""
    json_string = json.dumps(data, ensure_ascii=False, indent=4)
    return Response(
        json_string.encode('utf-8'), 
        status=status_code, 
        mimetype='application/json; charset=utf-8' 
    )

def extract_ytcfg_data(html_content):
    """HTMLからytcfg (APIキーやクライアント情報) を抽出する"""
    # ... (カカオマメさん提供のロジック) ...
    match = re.search(r'var ytcfg = ({.*?});', html_content, re.DOTALL)
    if match:
        try:
            cfg_string = match.group(1)
            cfg_string = cfg_string.replace('\\"', '"').replace("'", '"')
            return json.loads(cfg_string)
        except json.JSONDecodeError:
            return {}
    return {}

def allowed_file(filename):
    # ... (カカオマメさん提供のロジック) ...
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_dummy_video(index):
    # ... (ロジックは上記に定義済み) ...
    video_id = f"v{index:03d}abcde"
    title = f"マイクラ配布ワールド変換テスト #{index}"
    views = f"{15000 + index * 100}回"
    published_at = f"{index % 7 + 1}日前"
    
    return {
        'video_id': video_id,
        'title': title,
        'thumbnail_url': f"https://dummyimage.com/320x180/007bff/fff&text={video_id}",
        'channel_name': DUMMY_CHANNEL['name'],
        'channel_id': DUMMY_CHANNEL['id'],
        'views': views,
        'published_at': published_at,
        'description_snippet': f"この動画では、最新の変換ツールを使ってワールド#{index}を統合版にしています。成功なるか...",
    }

# --- GitHub API ヘルパー関数 ---
def get_github_file_content(path):
    # ... (カカオマメさん提供のロジック) ...
    print(f"DEBUG: Getting file content for {path}")
    return None # 実際にはAPIを叩くロジックがある

def put_github_file_content(path, content, message, sha=None):
    # ... (カカオマメさん提供のロジック) ...
    print(f"DEBUG: Putting file content for {path}")
    return True, {} # 実際にはAPIを叩くロジックがある

def get_github_file_info(path):
    # ... (カカオマメさん提供のロジック) ...
    print(f"DEBUG: Getting file info for {path}")
    return {'sha': 'dummy_sha'} # 実際にはAPIを叩くロジックがある

def load_all_player_data():
    # ... (カカオマメさん提供のロジック) ...
    print("DEBUG: Loading all player data from GitHub (simulated)")
    return list(PLAYER_DATA.values()) # ダミーデータを返す

def save_single_player_data(player_data):
    # ... (カカオマメさん提供のロジック) ...
    print(f"DEBUG: Saving player data for {player_data.get('username')}")
    return True, {}

# ... (他のヘルパー関数: upload_directory_to_github, parse_mc_pack, load_pack_registry, save_pack_registry, load_world_data, save_world_data, capture_game_output, get_manifest_from_github は全てこのブロックに定義済みと仮定) ...

# ------------------------------------------------
# 2. 認証関連ルート
# ------------------------------------------------

@app.route('/login', methods=['POST'])
def login():
    """パスワード認証（AJAX対応）"""
    username = request.form.get('username')
    password = request.form.get('password')

    player = PLAYER_DATA.get(username)
    
    if player and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
        session.permanent = True 
        session['username'] = player['username']
        session['player_uuid'] = player['uuid']
        
        return jsonify({
            'success': True,
            'message': f"ログインしました。",
            'redirect_url': 'index.html' 
        }), 200
    else:
        return jsonify({
            'success': False, 
            'message': 'ユーザー名またはパスワードが違います。'
        }), 401 

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """GitHub Pagesから現在のログイン状態をチェックするAPI"""
    if 'username' in session:
        return jsonify({
            'logged_in': True,
            'username': session['username'],
            'uuid': session['player_uuid'],
            'profile_img': 'https://dummyimage.com/40x40/f00/fff&text=' + session['username'][0].upper()
        }), 200
    else:
        return jsonify({
            'logged_in': False
        }), 200

# --- GitHub OAuth 認証ルート ---

@app.route('/login/github')
def github_login():
    """GitHub OAuth認証を開始する"""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        flash("GitHub OAuth設定が不足しています。", "error")
        return redirect('/index.html') 
        
    state = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
    session['oauth_state'] = state
    
    redirect_uri = url_for('github_callback', _external=True)

    auth_url = (
        'https://github.com/login/oauth/authorize?' +
        urlencode({
            'client_id': GITHUB_CLIENT_ID,
            'redirect_uri': redirect_uri,
            'scope': 'user:email', 
            'state': state
        })
    )
    return redirect(auth_url)

@app.route('/login/github/callback')
def github_callback():
    """GitHubからのコールバックを受けてアクセストークンを取得・ログイン処理を行う"""
    code = request.args.get('code')
    state = request.args.get('state')
    saved_state = session.pop('oauth_state', None)

    if state is None or state != saved_state:
        flash("CSRF攻撃の疑いがあります（State mismatch）。", "error")
        return redirect('/index.html')

    token_url = 'https://github.com/login/oauth/access_token'
    headers = {'Accept': 'application/json'}
    data = {
        'client_id': GITHUB_CLIENT_ID,
        'client_secret': GITHUB_CLIENT_SECRET,
        'code': code
    }
    
    token_response = requests.post(token_url, headers=headers, data=data)
    token_info = token_response.json()
    
    if 'access_token' not in token_info:
        flash(f"GitHubからのアクセストークン取得に失敗しました: {token_info.get('error_description')}", "error")
        return redirect('/index.html')
        
    access_token = token_info['access_token']
    session['github_access_token'] = access_token

    user_url = 'https://api.github.com/user'
    user_headers = {'Authorization': f'token {access_token}'}
    user_response = requests.get(user_url, headers=user_headers)
    user_data = user_response.json()
    
    github_username = user_data.get('login')
    github_id = str(user_data.get('id'))
    
    if not github_username:
        flash("GitHubユーザー情報の取得に失敗しました。", "error")
        return redirect('/index.html')

    player_uuid = hashlib.sha256(github_id.encode()).hexdigest() 
    
    session.permanent = True
    session['username'] = github_username
    session['player_uuid'] = player_uuid
    session['logged_in_via'] = 'github'
    
    flash(f"GitHubアカウント ({github_username}) でログインしました！", "success")
    return redirect('/index.html') 

@app.route('/api/github/user', methods=['GET'])
def github_user_info():
    """認証済みのGitHubユーザー情報を返すAPI"""
    if 'github_access_token' not in session:
        return jsonify({'logged_in': False, 'message': 'GitHubでログインしていません。'}), 401

    access_token = session['github_access_token']
    
    user_url = 'https://api.github.com/user'
    user_headers = {'Authorization': f'token {access_token}'}
    user_response = requests.get(user_url, headers=user_headers)
    
    if user_response.status_code == 200:
        user_data = user_response.json()
        return jsonify({
            'logged_in': True,
            'username': user_data.get('login'),
            'name': user_data.get('name'),
            'avatar_url': user_data.get('avatar_url'),
            'profile_url': user_data.get('html_url') # 👈 途切れていた部分を補完
        }), 200
    else:
        session.pop('github_access_token', None)
        return jsonify({'logged_in': False, 'message': 'GitHubトークンが無効です。'}), 401

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    session.pop('is_offline_player', None)
    session.pop('github_access_token', None)
    flash("ログアウトしました。", "info")
    print("DEBUG: ユーザーがログアウトしました。")
    return redirect(url_for('index'))

@app.route('/logins', methods=['POST'])
def logins():
    """/login の別名（AJAX対応）"""
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'ユーザー名とパスワードを入力してください。'}), 400

    players = load_all_player_data()
    
    authenticated_player = None
    for player in players:
        # load_all_player_data()がダミーデータを返しているため、ここではハッシュの比較は省略
        if player['username'] == username and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
            authenticated_player = player
            break

    if authenticated_player:
        session.permanent = True 
        session['username'] = authenticated_player['username']
        session['player_uuid'] = authenticated_player['uuid']
        session.pop('is_offline_player', None) 
        
        print(f"DEBUG: ユーザー '{username}' がログインしました。")
        return jsonify({
            'success': True,
            'message': f"ようこそ、{username}さん！",
            'redirect_url': 'index.html' 
        }), 200
    else:
        print(f"DEBUG: ログイン失敗 - ユーザー名: {username}")
        return jsonify({
            'success': False, 
            'message': 'ユーザー名またはパスワードが違います。'
        }), 401 

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_all_player_data()
        
        if any(p['username'] == username for p in players):
            return jsonify({
                'success': False, 
                'message': 'このユーザー名はすでに使用されています。'
            }), 400 
        
        new_uuid = str(uuid.uuid4())
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        success, response_data = save_single_player_data(new_player)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'アカウントが正常に作成されました！',
                'redirect_url': '/login' 
            }), 201 
        else:
            return jsonify({
                'success': False,
                'message': 'アカウント作成に失敗しました。GitHub設定を確認してください。',
                'error_details': response_data
            }), 500 

# ------------------------------------------------
# 3. YouTube風 API ルート (/API/yt/*)
# ------------------------------------------------

@app.route('/API/yt/videos/home', methods=['GET'])
def home_videos():
    videos = [create_dummy_video(i) for i in range(1, 21)]
    return jsonify({'videos': videos}), 200








# --- チャンネル検索 API 関数 ---

@app.route('/API/yt/search/channels', methods=['GET'])
def search_channels():
    """検索キーワード(q)を受け取り、YouTube内部検索APIを叩いてチャンネルリストを返す。"""
    
    query_keyword = request.args.get('q')
    if not query_keyword:
        return create_json_response({'error': '検索キーワード (q) がありません'}, 400) 

    api_url_path = "/youtubei/v1/search"
    url = "https://www.youtube.com/" 
    
    api_key = None
    client_version_fallback = get_dynamic_client_version() # 🚨 動的バージョン設定を適用
    client_name = 'WEB'
    visitor_data = None 

    try:
        # 1. YouTubeトップページHTMLの取得とAPIキー抽出 (既存ロジックを流用)
        headers_html = {'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
        response = requests.get(url, headers=headers_html, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # 2. APIキー、バージョン、VisitorDataを抽出
        key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html_content)
        version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
        visitor_match = re.search(r'"VISITOR_DATA"\s*:\s*"([a-zA-Z0-9%\-_=]+)"', html_content)

        if key_match:
            api_key = key_match.group(1)
            client_version = version_match.group(1) if version_match else client_version_fallback
            visitor_data = visitor_match.group(1) if visitor_match else None
            
            if client_version == client_version_fallback or not version_match: 
                 client_version = client_version_fallback
        else:
            return create_json_response({'channels': [], 'error': '検索 APIキーが見つかりませんでした。'}, 500) 

        # 3. 内部APIのペイロード構築
        api_url = f"https://www.youtube.com{api_url_path}?key={api_key}"
        
        context_data = {
            "client": {
                "hl": "ja", 
                "gl": "JP",
                "clientName": client_name,
                "clientVersion": client_version,
                "platform": "DESKTOP",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
            },
            "user": {"lockedSafetyMode": False},
            "request": {"useSsl": True}
        }
        
        if visitor_data:
             context_data['client']['visitorData'] = visitor_data
        
        payload = {
            "query": query_keyword, 
            "context": context_data
            # 🚨 修正: params を削除（または空に）し、全検索結果を取得
            # "params": "" 
        }
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        # 4. 内部APIを叩く
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        api_response.raise_for_status() 
        api_data = api_response.json()

        # 5. APIデータからチャンネルリストを抽出（channelRendererを探索）
        section_list_contents = api_data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
        
        channels = []
        
        for section in section_list_contents:
            item_section = section.get('itemSectionRenderer', {})
            for item in item_section.get('contents', []):
                
                # 🚨 チャンネルレンダラーをチェック
                renderer = item.get('channelRenderer') 
                if not renderer: continue

                # 6. チャンネルレンダラーから必要な情報を抽出
                channel_id = renderer.get('channelId')
                
                # チャンネル名
                title_obj = renderer.get('title', {})
                channel_name = title_obj.get('simpleText', 'チャンネル名不明')
                
                # 登録者数
                subscribers_text = renderer.get('navigationEndpoint', {}).get('commandMetadata', {}).get('webCommandMetadata', {}).get('text')
                # チャンネルのメタデータから登録者数を取得するより確実なパス
                if not subscribers_text:
                    subscribers_text = renderer.get('subscriberCountText', {}).get('simpleText', '登録者数不明')
                
                # サムネイルURL (最大のものを取得)
                thumbnail_url = renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy')

                channels.append({
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'thumbnail_url': thumbnail_url,
                    'subscribers': subscribers_text, 
                })

        # 🚨 動画結果と区別するため、キーを 'channels' で返す
        return create_json_response({'channels': channels}, 200)

    except requests.exceptions.HTTPError as e:
        error_message = f'チャンネル検索 APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        return create_json_response({'error': f'チャンネル検索の取得に失敗しました: {type(e).__name__}'}, 500)
















    




# --- 検索 API 関数 ---

@app.route('/API/yt/search/videos', methods=['GET'])
def search_videos():
    """検索キーワード(q)または継続トークン(continuation)を受け取り、動画リストと次の継続トークンを返す。"""
    
    query_keyword = request.args.get('q')
    continuation_token = request.args.get('continuation') # 🚨 継続トークンをチェック

    if not continuation_token and not query_keyword:
        return create_json_response({'error': '検索キーワード (q) または継続トークンがありません'}, 400) 

    # 1. APIキー、バージョン、VisitorDataを抽出するための初期設定
    api_key = None
    client_version_fallback = get_dynamic_client_version()
    client_name = 'WEB'
    visitor_data = None 
    url = "https://www.youtube.com/" 
    
    try:
        # 1. YouTubeトップページHTMLの取得
        headers_html = {'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
        response = requests.get(url, headers=headers_html, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # 2. APIキー、バージョン、VisitorDataを抽出
        key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html_content)
        version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
        visitor_match = re.search(r'"VISITOR_DATA"\s*:\s*"([a-zA-Z0-9%\-_=]+)"', html_content)

        if key_match:
            api_key = key_match.group(1)
            client_version = version_match.group(1) if version_match else client_version_fallback
            visitor_data = visitor_match.group(1) if visitor_match else None
            
            if client_version == client_version_fallback or not version_match: 
                 client_version = client_version_fallback
        else:
            return create_json_response({'videos': [], 'error': '検索 APIキーが見つかりませんでした。'}, 500) 

        # 3. 内部APIのペイロード構築
        context_data = {
            "client": {
                "hl": "ja", 
                "gl": "JP",
                "clientName": client_name,
                "clientVersion": client_version,
                "platform": "DESKTOP",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
            },
            "user": {"lockedSafetyMode": False},
            "request": {"useSsl": True}
        }
        
        if visitor_data:
             context_data['client']['visitorData'] = visitor_data
        
        # 🚨 検索の種類とAPI URLを分岐: 継続トークンがあれば /browse、なければ /search
        if continuation_token:
            # Continuation リクエスト
            api_url_path = "/youtubei/v1/browse"
            payload = {
                "continuation": continuation_token, # 🚨 continuation をペイロードに設定
                "context": context_data
            }
        else:
            # 初期検索リクエスト
            api_url_path = "/youtubei/v1/search"
            payload = {
                "query": query_keyword, 
                "params": "EgIQAQ%3D%3D", # 動画フィルタ
                "context": context_data
            }

        api_url = f"https://www.youtube.com{api_url_path}?key={api_key}"
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        # 4. 内部APIを叩く
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        api_response.raise_for_status() 
        api_data = api_response.json()
    
        # 5. APIデータから動画リストを抽出（ページネーション対応）
        
        if continuation_token:
            # Continuation のレスポンスからアイテムを取得
            # 継続リクエストのレスポンス構造は onResponseReceivedCommands の中にあります
            continuation_items = api_data.get('onResponseReceivedCommands', [{}])[0].get('appendContinuationItemsAction', {}).get('continuationItems', [])
            video_items_container = continuation_items
        else:
            # 初期検索のレスポンスからアイテムを取得
            section_list_contents = api_data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
            
            # 通常、最初の itemSectionRenderer の contents に動画リストがあります
            if section_list_contents and 'itemSectionRenderer' in section_list_contents[0]:
                video_items_container = section_list_contents[0].get('itemSectionRenderer', {}).get('contents', [])
            else:
                video_items_container = []

        videos = []
        next_continuation = None # 🚨 次の継続トークン

        for item in video_items_container:
            # 継続トークンを抽出
            continuation_item = item.get('continuationItemRenderer')
            if continuation_item:
                next_continuation = continuation_item.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                continue # トークンは動画ではないのでスキップ
                
            # 動画レンダラー抽出
            renderer = item.get('videoRenderer') 
            if not renderer: continue

            # 動画情報の抽出
            video_id = renderer.get('videoId')
            title_obj = renderer.get('title', {})
            final_title = title_obj.get('runs', [{}])[0].get('text', 'タイトル不明')
            duration = renderer.get('lengthText', {}).get('simpleText', '')
            if duration:
                 final_title = f"{final_title} ({duration})"
            
            owner_text = renderer.get('ownerText', {}).get('runs', [{}])[0]
            channel_name = owner_text.get('text', 'チャンネル名不明')
            channel_id_link = owner_text.get('navigationEndpoint', {}).get('browseEndpoint', {}).get('browseId')
            
            videos.append({
                'video_id': video_id,
                'title': final_title,
                'thumbnail_url': renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy'),
                'channel_name': channel_name, 
                'channel_id': channel_id_link,
                'views': renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明'),
                'published_at': renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明'),
            })

        # 🚨 戻り値に next_continuation を追加して返す
        return create_json_response({'videos': videos, 'next_continuation': next_continuation}, 200)

    except requests.exceptions.HTTPError as e:
        error_message = f'検索 APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        return create_json_response({'error': f'動画リストの取得に失敗しました: {type(e).__name__}'}, 500)


















@app.route('/API/yt/video', methods=['GET'])
def video_metadata():
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'error': 'Video ID is missing'}), 400
    video_data = create_dummy_video(int(video_id.replace('v', '').replace('abcde', '')))
    video_data['comment_count'] = 125
    video_data['comments'] = [{'author': 'PlayerA', 'text': '参考になりました！'}, {'author': 'PlayerB', 'text': '次も期待しています！'}]
    return jsonify(video_data), 200

@app.route('/API/yt/iframe/<video_id>', methods=['GET'])
def video_iframe(video_id):
    fallback_url = f"{DEFAULT_EMBED_BASE}{video_id}"
    try:
        response = requests.get(CONFIG_URL, timeout=5)
        response.raise_for_status()
        config_data = response.json()
        params_string = config_data.get('params', '').replace('&amp;', '&')
        
        query_params = parse_qs(params_string)
        final_params = {key: value_list[-1] for key, value_list in query_params.items()}
        final_params_string = urlencode(final_params)
        
        embed_src = fallback_url
        if final_params_string:
            embed_src += f"?{final_params_string}"
            
        return jsonify({'iframe_url': embed_src}), 200
    except Exception as e:
        print(f"ERROR: Config or network error: {e}")
        return jsonify({'iframe_url': fallback_url}), 200

@app.route('/API/yt/channel', methods=['GET'])
def channel_metadata():
    """チャンネルメタデータを返すAPI。文字化け対策に create_json_response を使用。"""
    channel_id = request.args.get('c')
    print(f"channel_id:{channel_id}")
    if not channel_id:
        return create_json_response({'error': 'Channel ID is missing'}, 400)

    # URLの構築
    if channel_id.startswith('@'):
        url = f"https://www.youtube.com/{channel_id}"
    elif channel_id.startswith('UC') and len(channel_id) >= 20:
        url = f"https://www.youtube.com/channel/{channel_id}"
    elif ' ' not in channel_id and '/' not in channel_id:
        url = f"https://www.youtube.com/@{channel_id}"
    else:
        return create_json_response({'error': '無効なチャンネルIDまたはハンドル形式です。'}, 400)
        
    try:
        print(f"url:{url}")
        response = requests.get(url, timeout=10)
        print(f"response:{response}")
        response.raise_for_status()
        html_content = response.text
        print(f"html_content:{html_content}")
        match = re.search(r'var ytInitialData = (.*?);</script>', html_content, re.DOTALL)
        print(f"match:{match}")
        if not match:
            return create_json_response({'error': 'Initial channel data (ytInitialData) not found.'}, 500)
        data = json.loads(match.group(1))
        print(f"data:{data}")

        # 情報抽出ロジック (複雑なフォールバックロジックを統合)
        channel_info = data.get('metadata', {}).get('channelMetadataRenderer')
        print(f"channel_info:{channel_info}")
        
        if not channel_info:
            header_data = data.get('header', {})
            print(f"header_data:{header_data}")
            for key in ['channelHeaderRenderer', 'c4TabbedHeaderRenderer', 'engagementPanelTitleHeaderRenderer', 'pageHeaderRenderer']:
                if key in header_data:
                    channel_info = header_data.get(key)
                    print(f"channel_info:{channel_info}")
                    break

        # チャンネル名
        channel_name_obj = channel_info.get('title') or channel_info.get('pageTitle')
        channel_name = channel_name_obj.get('simpleText') if isinstance(channel_name_obj, dict) and 'simpleText' in channel_name_obj else channel_name_obj or 'チャンネル名不明'
        description = channel_info.get('description') or ''
        print(f"channel_name_obj:{channel_name_obj}\n channel_name:{channel_name}\n description:{description}")
        
        # 登録者数
        subscriber_text = "登録者数不明"
        if 'header' in data:
            for key in data['header'].keys():
                if key.endswith('HeaderRenderer'):
                    sub_obj = data['header'][key].get('subscriberCountText') or data['header'][key].get('subscribersText')
                    if sub_obj and isinstance(sub_obj, dict) and 'simpleText' in sub_obj:
                        subscriber_text = sub_obj['simpleText']
                        break
        
        # プロフィール画像
        avatar_obj = channel_info.get('avatar') or channel_info.get('image')
        profile_img_url = 'https://dummyimage.com/80x80/000/fff&text=CM'
        if avatar_obj and avatar_obj.get('thumbnails'):
             profile_img_url = avatar_obj.get('thumbnails', [{}])[-1].get('url', profile_img_url)
        elif avatar_obj and avatar_obj.get('decoratedAvatarViewModel', {}).get('avatar', {}).get('avatarViewModel', {}).get('image', {}).get('sources'):
             sources = avatar_obj['decoratedAvatarViewModel']['avatar']['avatarViewModel']['image']['sources']
             profile_img_url = sources[-1]['url']
        
        # 最終結果をJSONで返す 
        final_data = {
            'channel_id': channel_id,
            'channel_name': channel_name,
            'subscriber_count': subscriber_text,
            'profile_image_url': profile_img_url,
            'banner_image_url': '', 
            'description': description,
            'join_date': ''
        }
        return create_json_response(final_data, 200)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return create_json_response({'error': f'チャンネルが見つかりません。ID/ハンドル({channel_id})を確認してください。'}, 404)
        return create_json_response({'error': f'外部URLの取得に失敗しました: {e}'}, 503)
    except Exception as e:
        return create_json_response({'error': f'サーバー側で予期せぬエラーが発生しました: {type(e).__name__}'}, 500)









# ※ Flaskアプリ内で、requests, json, re, create_json_responseがインポートされていることを前提とします。

# --- ヘルパー関数は使用せず、この関数内で直接キーを抽出します ---
# ※ Flaskアプリ内で、requests, json, re, create_json_responseがインポートされていることを前提とします。


# ※ 以下の create_json_response 関数は、Flaskアプリケーションで定義されていることを前提とします。
# 例: def create_json_response(data, status_code): return app.response_class(response=json.dumps(data, ensure_ascii=False), status=status_code, mimetype='application/json')

import requests
import json
import re
from flask import request

# ※ 以下の create_json_response 関数は、Flaskアプリケーションで定義されていることを前提とします。

@app.route('/API/yt/channel/videos', methods=['GET'])
def channel_videos():
    """キー、バージョン、VisitorDataを抽出し、リッチなコンテキストでAPIを叩く。"""
    
    channel_id = request.args.get('c')
    if not channel_id:
        return create_json_response({'error': 'Channel ID is missing'}, 400) 

    if channel_id.startswith('@'):
        url = f"https://www.youtube.com/{channel_id}"
    else:
        url = f"https://www.youtube.com/channel/{channel_id}"

    api_key = None
    # 最新のクライアントバージョンを設定
    client_version_fallback = get_dynamic_client_version() 
    client_name = 'WEB'
    visitor_data = None 

    try:
        # 1. チャンネルページHTMLの取得
        headers_html = {'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
        response = requests.get(url, headers=headers_html, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # 2. APIキー、バージョン、VisitorDataを抽出
        key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html_content)
        version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
        visitor_match = re.search(r'"VISITOR_DATA"\s*:\s*"([a-zA-Z0-9%\-_=]+)"', html_content)

        if key_match:
            api_key = key_match.group(1)
            
            client_version = version_match.group(1) if version_match else client_version_fallback
            visitor_data = visitor_match.group(1) if visitor_match else None
            
            print(f"DEBUG: ✅ API Key found: {api_key[:8]}...")
            
            if '20251027' not in client_version: 
                 client_version = client_version_fallback
                 print(f"DEBUG: ⚠️ Version outdated/not found. Forcing latest: {client_version}")
            
            print(f"DEBUG: ⚙️ Client Version: {client_version}")
            print(f"DEBUG: ⚙️ VisitorData found: {bool(visitor_data)}")
        else:
            return create_json_response({'videos': [], 'error': '動画リスト APIキーが見つかりませんでした。'}, 500) 

        # 3. 内部APIのペイロード構築
        yt_initial_data_match = re.search(r'var ytInitialData = (.*?);</script>', html_content, re.DOTALL)
        channel_id_for_api = channel_id 
        if yt_initial_data_match:
            try:
                yt_data = json.loads(yt_initial_data_match.group(1))
                extracted_browse_id = yt_data.get('header', {}).get('c4TabbedHeaderRenderer', {}).get('channelId')
                if not extracted_browse_id:
                     extracted_browse_id = yt_data.get('metadata', {}).get('channelMetadataRenderer', {}).get('externalId')
                
                if extracted_browse_id:
                    channel_id_for_api = extracted_browse_id
            except json.JSONDecodeError:
                print("DEBUG: ❌ ytInitialData JSON デコードエラー。BrowseId抽出スキップ。")
        
        print(f"DEBUG: ⚙️ API BrowseId: {channel_id_for_api}")

        # 4. 内部APIを叩く
        api_url = f"https://www.youtube.com/youtubei/v1/browse?key={api_key}"
        
        context_data = {
            "client": {
                "hl": "ja", 
                "gl": "JP",
                "clientName": client_name,
                "clientVersion": client_version,
                "platform": "DESKTOP",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
            },
            "user": {"lockedSafetyMode": False},
            "request": {"useSsl": True}
        }
        
        if visitor_data:
             context_data['client']['visitorData'] = visitor_data
        
        payload = {
            "browseId": channel_id_for_api, 
            "params": "EgZ2aWRlb3M%3D",
            "context": context_data
        }
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        print(f"DEBUG: 🚀 Posting API request with clientVersion: {client_version}...")
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        api_response.raise_for_status() 
        api_data = api_response.json()

        print(f"DEBUG: ✅ API call successful! Status: {api_response.status_code}")

        # 5. APIデータから動画リストを抽出
        tabs = api_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
        
        video_items_container = None
        
        for tab in tabs:
            tab_renderer = tab.get('tabRenderer', {})
            tab_title = tab_renderer.get('title')

            if tab_title in ['Videos', '動画', 'アップロード', 'ホーム']:
                
                content = tab_renderer.get('content', {})
                section_list = content.get('sectionListRenderer', {})

                for section_content in section_list.get('contents', []):
                    item_section = section_content.get('itemSectionRenderer', {})
                    for item in item_section.get('contents', []):
                        
                        grid_renderer = item.get('gridRenderer', {})
                        if grid_renderer and grid_renderer.get('items'):
                            video_items_container = grid_renderer
                            print("DEBUG: ✅ Video items found in GridRenderer.")
                            break

                        shelf_renderer = item.get('shelfRenderer', {})
                        if shelf_renderer:
                            shelf_content = shelf_renderer.get('content', {})
                            horizontal_list = shelf_content.get('horizontalListRenderer', {})
                            
                            if horizontal_list and horizontal_list.get('items'):
                                video_items_container = horizontal_list
                                print("DEBUG: ✅ Video items found in HorizontalListRenderer.")
                                break
                    
                    if video_items_container:
                        break
                
                if video_items_container:
                    break
        
        if not video_items_container:
            print("ERROR: 動画リストのコンテンツ構造が見つかりませんでした。")
            return create_json_response({'videos': [], 'error': '動画リストのコンテンツ構造が見つかりませんでした。APIのJSON構造が変更された可能性があります。'}, 500) 

        # 6. 動画レンダラーから必要な情報を抽出
        video_renderers = video_items_container.get('items', [])
        videos = []
        for item in video_renderers:
            renderer = item.get('gridVideoRenderer')
            shorts_renderer = item.get('shortsLockupViewModel')
            
            final_title = 'タイトル不明'
            video_id = None
            thumbnail_url = 'dummy'
            views = '視聴回数不明'
            published_at = '公開日不明'
            
            if renderer:
                # --- 通常動画の処理 ---
                video_id = renderer.get('videoId')
                
                # タイトル抽出ロジック（通常動画用）
                title_obj = renderer.get('title', {})
                # 1. Accessibilityオブジェクトからラベルを抽出
                title_text = title_obj.get('accessibility', {}).get('accessibilityData', {}).get('label')
                
                if title_text:
                    title_parts = title_text.rsplit(', ', 1)
                    if len(title_parts) > 1 and ('前' in title_parts[-1] or '視聴' in title_parts[-1]):
                        final_title = title_parts[0]
                    else:
                        final_title = title_text
                else:
                    # 2. runs配列からテキストを抽出（従来の方法）
                    final_title = title_obj.get('runs', [{}])[0].get('text', 'タイトル不明')
                
                thumbnail_url = renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy')
                views = renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明')
                published_at = renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明')
            
            elif shorts_renderer:
                # --- ショート動画の処理 (🚨 最終最適化) ---
                video_id = shorts_renderer.get('entityId', '').replace('shorts-shelf-item-', '')
                
                overlay_metadata = shorts_renderer.get('overlayMetadata', {})
                
                # 🚨 primaryTextからタイトルを抽出
                final_title = overlay_metadata.get('primaryText', {}).get('content', 'タイトル不明')
                
                # 🚨 secondaryTextから視聴回数を抽出
                views = overlay_metadata.get('secondaryText', {}).get('content', '視聴回数不明')
                
                # サムネイルは専用パスから抽出
                thumbnail_url = shorts_renderer.get('thumbnail', {}).get('sources', [{}])[0].get('url', 'dummy')
                published_at = 'ショート動画' # ショート動画には公開日情報がないため識別子とする

            
            if video_id:
                 videos.append({
                    'video_id': video_id,
                    'title': final_title,
                    'thumbnail_url': thumbnail_url,
                    'channel_name': channel_id, 
                    'views': views,
                    'published_at': published_at,
                })

        return create_json_response({'videos': videos}, 200)

    except requests.exceptions.HTTPError as e:
        print(f"ERROR: API POST failed. Status: {e.response.status_code}. Response: {e.response.text[:200]}...")
        error_message = f'動画リスト APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        print(f"FATAL ERROR: Video list scraping failed: {type(e).__name__}: {e}")
        return create_json_response({'error': f'動画リストの取得に失敗しました: {type(e).__name__}'}, 500)

















@app.route('/API/yt/playlist', methods=['GET'])
def playlist_data():
    """playlist.html用の再生リストデータと動画リストを返すAPI"""
    playlist_id = request.args.get('list')
    if not playlist_id:
        return jsonify({'error': 'Playlist ID is missing'}), 400

    videos = [create_dummy_video(i) for i in range(1, 6)] 
    
    return jsonify({
        'title': f"マイクラ神ワザ集 【リストID:{playlist_id}}}",
        'channel_name': DUMMY_CHANNEL['name'],
        'description': 'マイクラで使える便利なテクニックをまとめた再生リストです。',
        'video_count': len(videos),
        'videos': videos
    }), 200


# ------------------------------------------------
# 4. アプリケーションのエントリポイント (ページルート)
# ------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    return render_template('home.html')
    
@app.route('/setting')
def setting():
    return render_template('setting.html')
    
@app.route('/store')
def store():
    return render_template('store.html')
    
@app.route('/server')
def server_page():
    return render_template('server.html')

# ------------------------------------------------
# 5. アプリケーションの実行
# ------------------------------------------------

if __name__ == '__main__':
    # Flaskアプリを起動
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
