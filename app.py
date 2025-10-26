from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, stream_with_context, jsonify
import hashlib
import requests
import json
import os
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
game_process = None
game_output_buffer = []
game_output_lock = threading.Lock()


# ------------------------------------------------
# 1. ヘルパー関数 (ユーティリティ / GitHub API)
# ------------------------------------------------
def extract_ytcfg_data(html_content):
    """
    HTMLからYouTube内部設定 (ytcfg) を抽出し、INNERTUBE_API_KEYおよびクライアント情報を取得する。
    直接的なキー名での正規表現検索を最優先にする。
    """
    import re
    import json

    # 1. 最優先: INNERTUBE_API_KEY, CLIENT_VERSION, CLIENT_NAMEを直接探す
    # キーと値を個別に、最も緩い形式でキャプチャする（シングルクォートやバックスラッシュの心配を減らす）
    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([a-zA-Z0-9_-]+)"', html_content)
    version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([0-9\.]+)"', html_content)
    name_match = re.search(r'"INNERTUBE_CLIENT_NAME"\s*:\s*"([a-zA-Z0-9_]+)"', html_content)

    if key_match:
        api_key = key_match.group(1)
        client_version = version_match.group(1) if version_match else '2.20251026.09.00' 
        client_name = name_match.group(1) if name_match else 'WEB'
        
        print(f"DEBUG: API Key found via direct regex search: {api_key[:8]}...")
        return {
            'INNERTUBE_API_KEY': api_key,
            'client': {
                'clientName': client_name,
                'clientVersion': client_version
            }
        }

    # 2. ytcfg.set( ... ) パターン (フォールバック)
    match_ytcfg_set = re.search(r'ytcfg\.set\s*\(\s*(\{.+?\})\s*\);', html_content, re.DOTALL)
    if match_ytcfg_set:
        try:
            cfg_string = match_ytcfg_set.group(1)
            ytcfg = json.loads(cfg_string)
            if ytcfg.get('INNERTUBE_API_KEY'):
                print("DEBUG: API Key found via ytcfg.set pattern.")
                return ytcfg
        except json.JSONDecodeError:
            pass

    # 3. 完全に失敗した場合
    return {}
    










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
                'redirect_url': 'https://minecraft-flask-app-gold.vercel.app/login' 
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
    
@app.route('/API/yt/search', methods=['GET'])
def search_videos():
    query = request.args.get('q', '')
    results = [create_dummy_video(i) for i in range(1, 11)]
    for i, result in enumerate(results):
        result['title'] = f"【検索結果】{query}を含む動画 #{i+1}"
    return jsonify({'results': results}), 200

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
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        match = re.search(r'var ytInitialData = (.*?);</script>', html_content, re.DOTALL)
        if not match:
            return create_json_response({'error': 'Initial channel data (ytInitialData) not found.'}, 500)
        data = json.loads(match.group(1))

        # 情報抽出ロジック (複雑なフォールバックロジックを統合)
        channel_info = data.get('metadata', {}).get('channelMetadataRenderer')
        
        if not channel_info:
            header_data = data.get('header', {})
            for key in ['channelHeaderRenderer', 'c4TabbedHeaderRenderer', 'engagementPanelTitleHeaderRenderer', 'pageHeaderRenderer']:
                if key in header_data:
                    channel_info = header_data.get(key)
                    break

        # チャンネル名
        channel_name_obj = channel_info.get('title') or channel_info.get('pageTitle')
        channel_name = channel_name_obj.get('simpleText') if isinstance(channel_name_obj, dict) and 'simpleText' in channel_name_obj else channel_name_obj or 'チャンネル名不明'
        description = channel_info.get('description') or ''
        
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









@app.route('/API/yt/channel/videos', methods=['GET'])
def channel_videos():
    """内部 API (/youtubei/v1/browse) を使用して、チャンネルの動画リストを返す。"""
    channel_id = request.args.get('c')
    if not channel_id:
        return create_json_response({'error': 'Channel ID is missing'}, 400) 

    if channel_id.startswith('@'):
        url = f"https://www.youtube.com/{channel_id}"
    else:
        url = f"https://www.youtube.com/channel/{channel_id}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text

        # 1. 修正された extract_ytcfg_data で APIキーとクライアント情報を取得
        ytcfg = extract_ytcfg_data(html_content)
        api_key = ytcfg.get('INNERTUBE_API_KEY')
        client_name = ytcfg.get('client', {}).get('clientName', 'WEB')
        client_version = ytcfg.get('client', {}).get('clientVersion', '2.20251025.09.00')

        if not api_key:
            # APIキーが取得できない場合はエラーレスポンスを返す
            return create_json_response({'videos': [], 'error': '動画リスト APIキーが見つかりませんでした。'}, 500) 

        # 2. APIエンドポイントURLとペイロードを構築
        api_url = f"https://www.youtube.com/youtubei/v1/browse?key={api_key}"
        
        # Invidiousと同じ原理で、動画タブの初期C-Tokenに相当する 'params' を設定
        payload = {
            "browseId": channel_id,
            "params": "EgZ2aWRlb3M%3D", # Base64 for 'videos'
            "context": {
                "client": {
                    "hl": "ja",
                    "clientName": client_name,
                    "clientVersion": client_version
                },
                "user": {},
                "request": {"useSsl": True}
            }
        }
        
        # 3. 内部APIを叩く (POSTリクエスト)
        api_response = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'})
        api_response.raise_for_status()
        api_data = api_response.json()

        # 4. JSONレスポンスから動画リストを抽出 (ロジックは変更なし)
        contents_path = api_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [{}])
        
        videos_tab_content = None
        for tab in contents_path:
             # タブのタイトルで「Videos」「動画」「アップロード」のいずれかを探す
             if tab.get('tabRenderer', {}).get('title') in ['Videos', '動画', 'アップロード']:
                 videos_tab_content = tab['tabRenderer']['content'] \
                                         .get('sectionListRenderer', {}).get('contents', [{}])[0] \
                                         .get('itemSectionRenderer', {}).get('contents', [{}])[0] \
                                         .get('gridRenderer', {})
                 break
        
        if not videos_tab_content:
            return create_json_response({'videos': [], 'error': '動画リストのコンテンツ構造が見つかりませんでした。'}, 500) 

        video_renderers = videos_tab_content.get('items', [])
        videos = []
        for item in video_renderers:
            renderer = item.get('gridVideoRenderer')
            if not renderer: continue

            videos.append({
                'video_id': renderer.get('videoId'),
                'title': renderer.get('title', {}).get('runs', [{}])[0].get('text', 'タイトル不明'),
                'thumbnail_url': renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy'),
                'channel_name': channel_id, 
                'views': renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明'),
                'published_at': renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明'),
            })

        return create_json_response({'videos': videos}, 200)

    except Exception as e:
        print(f"ERROR: Internal API video list scraping failed: {type(e).__name__}: {e}")
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
