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


pokemogukunns = Flask(__name__)
app = pokemogukunns
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

# ※ Flask, requests, json, re, create_json_response, get_dynamic_client_version の定義済みを前提とします。

@app.route('/API/yt/videos/home', methods=['GET'])
def get_home_videos():
    """YouTubeのホームフィード（トップページ）の動画リストを取得する。
    継続トークン（continuation）によるページングに対応。
    """
    
    continuation_token = request.args.get('continuation')
    request_type = request.args.get('type') 

    # 1. 初期設定 (検索APIとほぼ同じ)
    api_key = None
    client_version_fallback = get_dynamic_client_version()
    
    try:
        # 1-2. APIキー、バージョン、VisitorDataの抽出（search_videosから流用）
        headers_html = {'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
        response = requests.get("https://www.youtube.com/", headers=headers_html, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # (APIキー、バージョン、VisitorDataの抽出ロジック...省略)
        key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html_content)
        version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
        visitor_match = re.search(r'"VISITOR_DATA"\s*:\s*"([a-zA-Z0-9%\-_=]+)"', html_content)

        if key_match:
            api_key = key_match.group(1)
            client_version = version_match.group(1) if version_match else client_version_fallback
            visitor_data = visitor_match.group(1) if visitor_match else None
        else:
            return create_json_response({'videos': [], 'error': 'ホームフィード APIキーが見つかりませんでした。'}, 500) 

        # 2. 内部APIのペイロード構築
        context_data = {
            "client": {
                "hl": "ja", 
                "gl": "JP",
                "clientName": 'WEB',
                "clientVersion": client_version,
                "platform": "DESKTOP",
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36",
            },
        }
        if visitor_data:
             context_data['client']['visitorData'] = visitor_data

        api_url_path = "/youtubei/v1/browse" 
        
        if continuation_token:
            # 継続リクエストのペイロード
            payload = {
                "continuation": continuation_token,
                "context": context_data
            }
            print(f"DEBUG: ⚠️ Raw Continuation Token: {continuation_token}")
        else:
            # 初期リクエストのペイロード
            # 🚨 テスト用修正: browseId を トレンド（急上昇）に一時的に変更
            payload = {
                "browseId": "FEtrending", # 👈 "FEwhat_to_watch" から "FEtrending" に変更
                "context": context_data
            }

        api_url = f"https://www.youtube.com{api_url_path}?key={api_key}"
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }


# 3. 内部APIを叩く前にデバッグ用のcurlコマンドを出力

        # 1. ペイロード辞書を整形せずにJSON文字列に変換
        json_payload = json.dumps(payload, ensure_ascii=False)

        # 2. ヘッダーを curl の -H 形式の文字列リストに変換
        header_parts = []
        for key, value in headers_api.items():
            header_parts.append(f'-H "{key}: {value}"')

        # 3. コマンド全体をリストとして構築し、スペースで結合
        command_parts = [
            "curl", 
            "-v", 
            "-L", 
            "-X", 
            "POST",
            f'"{api_url}"'  # URLはダブルクォートで囲む
        ]
        command_parts.extend(header_parts)
        command_parts.append(f"-d '{json_payload}'")

        final_curl_command = " ".join(command_parts)
        
        # ユーザー情報に基づき、確定した値を出力します。
        print(f"DEBUG: ⚠️ Home API CURL Command (for manual testing):{final_curl_command}")

        # 4. 内部APIを叩く (requests.postの部分)
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        # ... (以降、通常通り)

        
        # 3. 内部APIを叩く
        
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        api_response.raise_for_status() 
        api_data = api_response.json()
        
        # type=data の場合は生データを返す
        if request_type == 'data':
            return create_json_response(api_data, 200)

        
        # 4. APIデータから動画リストと継続トークンを抽出
        # ... (中略: APIコール後の api_data 取得まで)

        # 4. APIデータから動画リストと継続トークンを抽出
        videos = []
        next_continuation = None 
        
        # 4-1. 動画アイテムのリストのパス（確定）
        if continuation_token:
             # Continuation のレスポンスからアイテムを取得
            all_items = api_data.get('onResponseReceivedActions', [{}])[0].get('appendContinuationItemsAction', {}).get('continuationItems', [])
        else:
            # 初期リクエストのレスポンスからアイテムを取得
            grid_renderer = api_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [{}])[0].get('tabRenderer', {}).get('content', {}).get('richGridRenderer', {})
            all_items = grid_renderer.get('contents', []) # 👈 ここに richSectionRenderer, richItemRenderer, continuationItemRenderer が含まれる
            
        print(f"DEBUG: 🎯 all_items (動画とトークン候補) のアイテム数: {len(all_items)}")

        # 5. 動画データと継続トークンの抽出
        for item in all_items: 
            # 継続トークンを抽出 (リストの最後のアイテムに格納される)
            continuation_item = item.get('continuationItemRenderer')
            if continuation_item:
                extracted_token = continuation_item.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                next_continuation = extracted_token
                print(f"DEBUG: 🚀 次の継続トークンを抽出成功: {extracted_token}")
                continue
                
            # 動画コンテナ (richItemRenderer) を抽出
            renderer_container = item.get('richItemRenderer', {})
            if not renderer_container:
                # richSectionRenderer (メッセージなど) はスキップ
                continue 
            
            # 動画レンダラーを取得
            renderer = renderer_container.get('content', {}).get('videoRenderer')
            
            if not renderer: 
                # 動画以外のアイテム (ショート動画、広告など) はスキップ
                continue

            # 動画情報の抽出 (search_videosから流用)
            video_id = renderer.get('videoId')
            final_title = renderer.get('title', {}).get('runs', [{}])[0].get('text', 'タイトル不明')
            duration = renderer.get('lengthText', {}).get('simpleText', '')
            if duration:
                 final_title = f"{final_title} ({duration})"
            
            owner_text = renderer.get('ownerText', {}).get('runs', [{}])[0]
            channel_name = owner_text.get('text', 'チャンネル名不明')
            
            videos.append({
                'video_id': video_id,
                'title': final_title,
                'channel_name': channel_name, 
                'views': renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明'),
                'published_at': renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明'),
            })

        # 6. 結果の返却
        print(f"DEBUG: 🎬 抽出された動画数: {len(videos)}")
        if next_continuation is None:
            print("DEBUG: 🛑 next_continuation は null です。次のページは存在しないか、抽出に失敗しています。")

        return create_json_response({'videos': videos, 'next_continuation': next_continuation}, 200)

    except requests.exceptions.HTTPError as e:
        error_message = f'ホームフィード APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        return create_json_response({'error': f'ホームフィードの取得に失敗しました: {type(e).__name__}'}, 500)








# ※ create_json_response, get_dynamic_client_version, request, requests, json, re は定義済みとします。



# ※ 'create_json_response' および 'get_dynamic_client_version' は
#    この関数の外部で既に定義されていることを前提とします。

@pokemogukunns.route('/API/yt/search', methods=['GET'])
def search_videos():
    """検索キーワード(q)または継続トークン(continuation)を受け取り、動画リストと次の継続トークンを返す。
    type=dataが指定された場合、生のAPIレスポンスデータを返す。"""
    
    # URLパラメータの取得
    query_keyword = request.args.get('q')
    continuation_token = request.args.get('continuation')
    request_type = request.args.get('type') 

    if not continuation_token and not query_keyword:
        return create_json_response({'error': '検索キーワード (q) または継続トークンがありません'}, 400) 

    # 1. 初期設定
    api_key = None
    client_version_fallback = get_dynamic_client_version()
    client_name = 'WEB'
    visitor_data = None 
    
    try:
        # 1-2. APIキー、バージョン、VisitorDataの抽出
        headers_html = {'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'}
        response = requests.get("https://www.youtube.com/", headers=headers_html, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
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
        
        # 検索の種類とAPI URLを分岐: 継続トークンがあれば /browse、なければ /search
        if continuation_token:
            # Continuation リクエストは /browse エンドポイントを使用
            api_url_path = "/youtubei/v1/browse"
            payload = {
                "continuation": continuation_token,
                "context": context_data
            }
        else:
            # 初期検索リクエストは /search エンドポイントを使用
            api_url_path = "/youtubei/v1/search"
            payload = {
                "query": query_keyword, 
                "params": "EgIQAQ%3D%3D", # 動画フィルタ
                "context": context_data
            }

        api_url = f"https://www.youtube.com{api_url_path}?key={api_key}"
        print(" ⬇️ APIにしたYoutubeリンク　⬇️ ")
        print(f"{api_url}")
        
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        # 4. 内部APIを叩く
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        print(" ⬇️ curlコマンド ⬇️ ")
        print(f"curl -v -L {api_url} -H {payload} -H {headers_api}")
        api_response.raise_for_status() 
        api_data = api_response.json()
        
        # type=data の場合は生データを返す
        if request_type == 'data':
            return create_json_response(api_data, 200)

        
        # 5. APIデータから動画リストと継続トークンを抽出
        videos = []
        next_continuation = None 
        
        if continuation_token:
            # Continuation のレスポンスからアイテムを取得
            all_items = api_data.get('onResponseReceivedCommands', [{}])[0].get('appendContinuationItemsAction', {}).get('continuationItems', [])
        else:
            # 初期検索のレスポンスからアイテムを取得
            section_list_contents = api_data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
            
            # 抽出パス強化: sectionListRenderer.contents のリスト全体を探索対象とする
            all_items = []
            
            for section in section_list_contents:
                 if 'itemSectionRenderer' in section:
                     # 動画アイテムを含むリスト
                     all_items.extend(section.get('itemSectionRenderer', {}).get('contents', []))
                 
                 # 継続トークンがセクションレベルにある場合も捕捉
                 elif 'continuationItemRenderer' in section:
                      all_items.append(section)


        print(f"DEBUG: 🎯 all_items (動画とトークン候補) のアイテム数: {len(all_items)}")

        # 6. 動画データと継続トークンの抽出
        for item in all_items: 
            # 継続トークンを最初に抽出
            continuation_item = item.get('continuationItemRenderer')
            if continuation_item:
                extracted_token = continuation_item.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                
                # 🚨 next_continuation の値を確定したら、printして次の処理に進む
                next_continuation = extracted_token
                print(f"DEBUG: 🚀 ロジックで次の継続トークンを抽出成功: {extracted_token}")
                print("URLを提供します。")
                print(f"/API/yt/search?q={query_keyword}&continuation={extracted_token}")
                continue
                
            # 動画レンダラーのみを抽出
            renderer = item.get('videoRenderer') 
            if not renderer: 
                continue

            # 動画情報の抽出
            video_id = renderer.get('videoId')
            title_obj = renderer.get('title', {})
            final_title = title_obj.get('runs', [{}])[0].get('text', 'タイトル不明')
            duration = renderer.get('lengthText', {}).get('simpleText', '')
            if duration:
                 final_title = f"{final_title} ({duration})"
            
            owner_text = renderer.get('ownerText', {}).get('runs', [{}])[0]
            channel_name = owner_text.get('text', 'チャンネル名不明')
            
            videos.append({
                'video_id': video_id,
                'title': final_title,
                'channel_name': channel_name, 
                'views': renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明'),
                'published_at': renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明'),
            })

        # 7. 結果の返却
        if next_continuation is None:
            print("DEBUG: 🛑 next_continuation は null です。次のページは存在しないか、抽出に失敗しています。")


        return create_json_response({'videos': videos, 'next_continuation': next_continuation}, 200)

    except requests.exceptions.HTTPError as e:
        error_message = f'検索 APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        return create_json_response({'error': f'動画リストの取得に失敗しました: {type(e).__name__}'}, 500)


















# --- チャンネル検索 API 関数 ---

@app.route('/API/yt/search/channels', methods=['GET'])
def search_channels():
    """検索キーワード(q)または継続トークン(continuation)を受け取り、チャンネルリストと次の継続トークンを返す。"""
    
    query_keyword = request.args.get('q')
    continuation_token = request.args.get('continuation') # 🚨 継続トークンをチェック

    if not continuation_token and not query_keyword:
        return create_json_response({'error': '検索キーワード (q) または継続トークンがありません'}, 400) 

    # 1. APIキー、バージョン、VisitorDataを抽出するための初期設定
    api_key = None
    client_version_fallback = get_dynamic_client_version() # 🚨 動的バージョン設定
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
            return create_json_response({'channels': [], 'error': '検索 APIキーが見つかりませんでした。'}, 500) 

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
            # Continuation リクエストは /browse エンドポイントを使用
            api_url_path = "/youtubei/v1/browse"
            payload = {
                "continuation": continuation_token, # 🚨 continuation をペイロードに設定
                "context": context_data
            }
        else:
            # 初期検索リクエストは /search エンドポイントを使用
            api_url_path = "/youtubei/v1/search"
            payload = {
                "query": query_keyword, 
                "context": context_data # チャンネル検索のため params は設定しない (全検索結果を取得)
            }

        api_url = f"https://www.youtube.com{api_url_path}?key={api_key}"
        print(" ⬇️ APIにしたYoutubeリンク　⬇️ ")
        print(f"{api_url}")
        
        headers_api = {
            'Content-Type': 'application/json',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8'
        }
        
        # 4. 内部APIを叩く
        api_response = requests.post(api_url, json=payload, headers=headers_api, timeout=10)
        api_response.raise_for_status() 
        api_data = api_response.json()

        # 5. APIデータからチャンネルリストを抽出（ページネーション対応）
        
        if continuation_token:
            # Continuation のレスポンスからアイテムを取得
            continuation_items = api_data.get('onResponseReceivedCommands', [{}])[0].get('appendContinuationItemsAction', {}).get('continuationItems', [])
            channel_items_container = continuation_items
        else:
            # 初期検索のレスポンスからアイテムを取得
            section_list_contents = api_data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
            
            if section_list_contents and 'itemSectionRenderer' in section_list_contents[0]:
                channel_items_container = section_list_contents[0].get('itemSectionRenderer', {}).get('contents', [])
            else:
                channel_items_container = []

        channels = []
        next_continuation = None # 🚨 次の継続トークン

        for item in channel_items_container:
            # 継続トークンを抽出
            continuation_item = item.get('continuationItemRenderer')
            if continuation_item:
                next_continuation = continuation_item.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                continue
                
            # 既存のチャンネルレンダラー抽出ロジック
            renderer = item.get('channelRenderer') 
            if not renderer: continue

            # 6. チャンネルレンダラーから必要な情報を抽出
            channel_id = renderer.get('channelId')
            title_obj = renderer.get('title', {})
            channel_name = title_obj.get('simpleText', 'チャンネル名不明')
            
            subscribers_text = renderer.get('navigationEndpoint', {}).get('commandMetadata', {}).get('webCommandMetadata', {}).get('text')
            if not subscribers_text:
                subscribers_text = renderer.get('subscriberCountText', {}).get('simpleText', '登録者数不明')
            
            thumbnail_url = renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy')

            channels.append({
                'channel_id': channel_id,
                'channel_name': channel_name,
                'thumbnail_url': thumbnail_url,
                'subscribers': subscribers_text, 
            })

        # 🚨 戻り値に next_continuation を追加
        return create_json_response({'channels': channels, 'next_continuation': next_continuation}, 200)

    except requests.exceptions.HTTPError as e:
        error_message = f'チャンネル検索 APIコールが失敗しました: {e.response.status_code}'
        return create_json_response({'error': error_message}, 503)
    except Exception as e:
        return create_json_response({'error': f'チャンネル検索の取得に失敗しました: {type(e).__name__}'}, 500)


































@app.route('/API/yt/video', methods=['GET'])
def video_metadata():
    """動画視聴ページからytInitialDataをスクレイピングし、メタデータを取得して返すAPI。
    
    クエリパラメータ 'type=data' が付与されている場合、生のytInitialData (JSON) をそのまま返します。
    """
    
    video_id = request.args.get('v')
    response_type = request.args.get('type')
    
    print(f"video_id:{video_id}, type:{response_type}")
    
    if not video_id:
        return create_json_response({'error': 'Video IDがありません。'}, 400)

    # 視聴ページのURLを構築
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        print(f"Fetching URL: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        html_content = response.text
        
        # 1. HTMLからytInitialData (JSON) を抽出
        match = re.search(r'var ytInitialData = (.*?);</script>', html_content, re.DOTALL)
        if not match:
            return create_json_response({'error': 'Initial video data (ytInitialData)が見つかりませんでした。'}, 500)
        
        # 2. JSONをパース
        data = json.loads(match.group(1))
        
        # 3. 【type=data の場合は生のJSONデータをそのまま返す】
        if response_type == 'data':
            print("Response type is 'data'. Returning raw JSON data.")
            return create_json_response(data, 200)

        # 4. 通常のメタデータ抽出処理
        
        # 複雑な構造から動画の主要情報部分を特定
        contents = data.get('contents', {})
        watch_next_results = contents.get('twoColumnWatchNextResults', {}).get('results', {}).get('results', {}).get('contents', [])
        
        # メイン情報とサブ情報（チャンネルなど）のレンダラーを抽出
        primary_info = watch_next_results[0].get('videoPrimaryInfoRenderer') if len(watch_next_results) > 0 and 'videoPrimaryInfoRenderer' in watch_next_results[0] else None
        secondary_info = watch_next_results[1].get('videoSecondaryInfoRenderer') if len(watch_next_results) > 1 and 'videoSecondaryInfoRenderer' in watch_next_results[1] else None
        
        if not primary_info or not secondary_info:
            return create_json_response({'error': '動画情報の主要ブロックを解析できませんでした。'}, 500)

        # 5. 必要なメタデータの抽出
        
        # タイトル
        title = primary_info.get('title', {}).get('runs', [{}])[0].get('text', 'タイトル不明')
        
        # 視聴回数と公開日
        views = primary_info.get('viewCount', {}).get('videoViewCountRenderer', {}).get('viewCount', {}).get('simpleText', '視聴回数不明')
        published_at = primary_info.get('dateText', {}).get('simpleText', '公開日不明')
        
        # チャンネル情報
        owner = secondary_info.get('owner', {}).get('videoOwnerRenderer', {})
        channel_name = owner.get('title', {}).get('runs', [{}])[0].get('text', 'チャンネル名不明')
        channel_id = owner.get('title', {}).get('runs', [{}])[0].get('navigationEndpoint', {}).get('browseEndpoint', {}).get('browseId', '')
        
        # チャンネルアイコンURL
        profile_img_url = 'https://dummyimage.com/80x80/000/fff&text=CM' # フォールバックURL
        thumbnail_obj = owner.get('thumbnail', {})
        thumbnails = thumbnail_obj.get('thumbnails', [])

        if thumbnails:
            profile_img_url = thumbnails[-1].get('url', profile_img_url)
        
        # 説明文
        description = ''
        attributed_desc_content = secondary_info.get('attributedDescription', {}).get('content')
        if attributed_desc_content:
            description = attributed_desc_content
        else:
            # フォールバックとして従来の description.runs をチェック
            description_runs = secondary_info.get('description', {}).get('runs', [])
            description = "".join([run.get('text', '') for run in description_runs])
        
        # 6. 最終結果をまとめる
        final_data = {
            'video_id': video_id,
            'title': title,
            'views': views,
            'published_at': published_at,
            'channel_name': channel_name,
            'channel_id': channel_id,
            'profile_image_url': profile_img_url, 
            'description': description,
            # 前のダミー関数が提供していたコメント情報を再現
            'comment_count': 125,
            'comments': [{'author': 'PlayerA', 'text': '参考になりました！'}, {'author': 'PlayerB', 'text': '次も期待しています！'}]
        }
        
        print(f"Successfully extracted metadata for video: {title}")
        return create_json_response(final_data, 200)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return create_json_response({'error': f'動画が見つかりません。ID({video_id})を確認してください。'}, 404)
        # その他のHTTPエラー (例: 5xx, 403など)
        return create_json_response({'error': f'外部URLの取得に失敗しました: {e}'}, 503)
    except Exception as e:
        # 予期せぬエラー（JSON解析エラー、キーエラーなど）
        print(f"Critical error during video metadata fetching: {e}")
        return create_json_response({'error': f'サーバー側で予期せぬエラーが発生しました: {type(e).__name__}'}, 500)















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














@app.route('/API/yt/channel', methods=['GET'])
def channel_metadata():
    """チャンネルメタデータを返すAPI。文字化け対策に create_json_response を使用。
    
    クエリパラメータ 'type=data' が付与されている場合、生のytInitialData (JSON) をそのまま返します。
    """
    channel_id = request.args.get('c')
    response_type = request.args.get('type') # 💡 type パラメータを取得
    
    print(f"channel_id:{channel_id}, type:{response_type}")
    
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

        # 💡 【追加ロジック】: type=data の場合は生のJSONデータをそのまま返す
        if response_type == 'data':
            print("Response type is 'data'. Returning raw JSON data.")
            return create_json_response(data, 200)

        # 従来の情報抽出ロジック (type=dataでない場合)
        
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
        print(f"Critical error during channel metadata fetching: {e}")
        return create_json_response({'error': f'サーバー側で予期せぬエラーが発生しました: {type(e).__name__}'}, 500)

















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
