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

app = Flask(__name__)

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
#app.secret_key = os.getenv('SECRET_KEY')
print("⬆️SECRET_KEYを環境変数から読み込み中⬇️")
app.secret_key = os.environ.get('SECRET_KEY', 'your_default_secret_key_for_dev')

CONFIG_URL = 'https://raw.githubusercontent.com/siawaseok3/wakame/master/video_config.json'
DEFAULT_EMBED_BASE = 'https://www.youtubeeducation.com/embed/'
# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')
print("その他の変数を環境変数から読み込み中")

# GitHub Pagesのドメインからのアクセスを許可
# TODO: 実際のGitHub Pagesのドメインに置き換える必要があります
CORS(app, supports_credentials=True, origins=[
    f"https://{GITHUB_OWNER}.github.io", 
    "http://127.0.0.1:5500" # ローカルテスト用
])

# セッションの永続化設定（Cookieの有効期限を長くする）
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 60 * 60 # 30日間

# ダミーのユーザーデータ (以前の作業で作成済みと仮定)
PLAYER_DATA = {
    'poke': {'username': 'poke', 'uuid': '2a7c17fa-6a24-4b45-8c7c-736ba962ab8d', 'password_hash': hashlib.sha256('testpassword'.encode()).hexdigest()},
    'kakaomame': {'username': 'kakaomame', 'uuid': 'ccf459b8-2426-45fa-80d2-618350654c47', 'password_hash': hashlib.sha256('mypass'.encode()).hexdigest()},
}

# app.py の上部に追加してください
def extract_ytcfg_data(html_content):
    """HTMLからytcfg (APIキーやクライアント情報) を抽出する"""
    # ytcfgは 'var ytcfg = {...' の形式で埋め込まれている
    match = re.search(r'var ytcfg = ({.*?});', html_content, re.DOTALL)
    if match:
        try:
            cfg_string = match.group(1)
            # JSONが厳密でないため、エスケープや引用符の修正を試みる
            cfg_string = cfg_string.replace('\\"', '"').replace("'", '"')
            # 最終的に JSON.loads で解析
            return json.loads(cfg_string)
        except json.JSONDecodeError:
            # 解析失敗時は空を返す
            return {}
    return {}

# GitHub設定とシークレットキーを起動時にチェックする関数
def check_config():
    print("\n--- アプリケーション設定の初期チェックを開始します ---")

    config_ok = True

    if not GITHUB_TOKEN:
        print("エラー: GITHUB_TOKEN が .env ファイルに設定されていません。")
        print("GitHub Personal Access Tokenを生成し、.envファイルに 'GITHUB_TOKEN=\"YOUR_TOKEN_HERE\"' の形式で設定してください。")
        config_ok = False
    if not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: GITHUB_OWNER または GITHUB_REPO が .env ファイルに設定されていません。")
        print(".envファイルに 'GITHUB_OWNER=\"あなたのGitHubユーザー名\"' と 'GITHUB_REPO=\"あなたのリポジトリ名\"' を設定してください。")
        config_ok = False
    
    if not app.secret_key:
        print("エラー: SECRET_KEY が .env ファイルに設定されていません。")
        print("セッションの永続化のために、.envファイルに 'SECRET_KEY=\"あなたの非常に長いランダムな秘密鍵\"' を設定してください。")
        print("例: SECRET_KEY=\"supersecretkeythatisverylongandrandomandhardtoguessthisisforproductionuse\"")
        config_ok = False

    if not config_ok:
        print("--- アプリケーション設定の初期チェックを完了しました (エラーあり) ---\n")
        return False

    api_base_url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.com.v3+json',
        'User-Agent': 'Flask-Minecraft-App-Startup-Check'
    }

    test_file_path = 'player_data.json'
    url = f'{api_base_url}/{test_file_path}'

    print(f"DEBUG: GitHub APIアクセスをテスト中: {url}")
    print(f"DEBUG: GITHUB_OWNER: {GITHUB_OWNER}")
    print(f"DEBUG: GITHUB_REPO: {GITHUB_REPO}")
    print(f"DEBUG: GITHUB_TOKEN (最初の5文字): {GITHUB_TOKEN[:5]}*****")

    try:
        response = requests.get(url, headers=headers)

        print(f"DEBUG: レスポンスステータスコード: {response.status_code}")

        if response.status_code == 200 or response.status_code == 404:
            print("成功: GitHub APIへのアクセスが確認できました。トークンとリポジトリ設定は有効です。")
            print("--- アプリケーション設定の初期チェックを完了しました ---\n")
            return True
        elif response.status_code == 401:
            print("\nエラー: 401 Unauthorized - 認証情報が無効です（Bad credentials）。")
            print("GitHubトークンが間違っているか、期限切れか、権限が不足しています。")
            print("GitHubで新しいトークンを生成し、'repo'スコープ（または'Contents'の'Read and write'）を付与して、.envファイルを更新してください。")
            return False
        elif response.status_code == 403:
            print("\nエラー: 403 Forbidden - アクセスが拒否されました。")
            print("トークンにリポジトリへのアクセス権限がありません（例: プライベートリポジトリへのアクセス）。")
            print("GitHubトークンの権限（スコープ）が不足している可能性があります。'repo'スコープが付与されているか確認してください。")
            return False
        else:
            print(f"\n予期せぬエラー: Status {response.status_code}")
            print(f"GitHub APIからの応答: {response.text}")
            print("GitHub APIへのアクセス中に問題が発生しました。")
            return False

    except requests.exceptions.RequestException as e:
        print(f"\nネットワークエラーが発生しました: {e}")
        print("GitHub APIに接続できませんでした。インターネット接続を確認するか、GitHubのステータスを確認してください。")
        return False

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.com.v3+json',
    'User-Agent': 'Flask-Minecraft-App'
}

# --- ファイルアップロード設定 ---
ALLOWED_EXTENSIONS = {'mcpack', 'mcaddon'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- GitHub API ヘルパー関数 ---
def get_github_file_content(path):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        try:
            json_response = response.json()
            content_b64 = json_response.get('content')
            
            if content_b64:
                decoded_content = base64.b64decode(content_b64).decode('utf-8')
                if decoded_content.strip():
                    return json.loads(decoded_content)
                else:
                    print(f"DEBUG: Decoded content for {path} is empty or whitespace only.")
                    return None
            else:
                print(f"DEBUG: 'content' key not found in GitHub API response for {path}.")
                return None
        except json.JSONDecodeError as e:
            print(f"ERROR: JSONDecodeError when parsing GitHub API response for {path}: {e}")
            print(f"Response text: {response.text[:200]}...")
            return None
        except Exception as e:
            print(f"ERROR: Unexpected error in get_github_file_content for {path}: {e}")
            return None
    elif response.status_code == 404:
        print(f"DEBUG: File not found on GitHub: {path}. Status: 404.")
        return None
    else:
        print(f"DEBUG: Failed to get content for {path}. Status: {response.status_code}, Response: {response.text}")
        return None

def put_github_file_content(path, content, message, sha=None):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    
    if isinstance(content, bytes):
        encoded_content = base64.b64encode(content).decode('utf-8')
    elif isinstance(content, str) and content.startswith(('ey', 'PD94bWwgdmVyc2lvbj', 'UEs')):
        encoded_content = content
    else:
        encoded_content = base64.b64encode(json.dumps(content, indent=4).encode('utf-8')).decode('utf-8')

    data = {
        'message': message,
        'content': encoded_content
    }
    if sha:
        data['sha'] = sha

    response = requests.put(url, headers=HEADERS, json=data)
    
    if not response.status_code in [200, 201]:
        print(f"ERROR: GitHub PUT failed for {path}. Status: {response.status_code}, Response: {response.text}")
        try:
            error_json = response.json()
            print(f"GitHub API Error Details: {json.dumps(error_json, indent=2)}")
        except json.JSONDecodeError:
            pass

    return response.status_code in [200, 201], response.json()

def get_github_file_info(path):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    if response.status_code not in [404]:
        print(f"DEBUG: Failed to get file info for {path}. Status: {response.status_code}, Response: {response.text}")
    return None

def upload_directory_to_github(local_dir_path, github_base_path, commit_message):
    success_count = 0
    fail_count = 0
    
    print(f"DEBUG: Starting directory upload from '{local_dir_path}' to GitHub path '{github_base_path}'")
    for root, _, files in os.walk(local_dir_path):
        for file_name in files:
            local_file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(local_file_path, local_dir_path)
            github_path = os.path.join(github_base_path, relative_path).replace(os.sep, '/')

            # GitHubのファイルサイズ制限（1MB）を考慮して、大きすぎるファイルはスキップ
            if os.path.getsize(local_file_path) > 1024 * 1024: # 1MB
                print(f"WARNING: Skipping large file (>{1}MB): {local_file_path}. GitHub API has a 1MB file size limit for direct content uploads.")
                continue

            try:
                with open(local_file_path, 'rb') as f:
                    file_content_bytes = f.read()
                
                existing_file_info = get_github_file_info(github_path)
                sha = existing_file_info['sha'] if existing_file_info else None
                
                file_success, file_response = put_github_file_content(
                    github_path,
                    file_content_bytes,
                    f"{commit_message}: {relative_path}",
                    sha
                )
                if file_success:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"ERROR: Failed to upload/update {github_path}. Response: {file_response}")

            except Exception as e:
                fail_count += 1
                print(f"ERROR: Error processing local file {local_file_path} for upload: {e}")
    
    print(f"INFO: Directory upload finished. Success: {success_count}, Failed: {fail_count}")
    return fail_count == 0

# --- プレイヤーデータ管理のリファクタリング ---
PLAYERS_DIR_PATH = 'players'

def load_all_player_data():
    all_players = []
    url = f'{GITHUB_API_BASE_URL}/{PLAYERS_DIR_PATH}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        print(f"DEBUG: Listing contents of {PLAYERS_DIR_PATH}. Items found: {len(response.json())}")
        for item in response.json():
            if item['type'] == 'file' and item['name'].endswith('.json'):
                player_file_path = f'{PLAYERS_DIR_PATH}/{item["name"]}'
                print(f"DEBUG: Attempting to load player data from: {player_file_path}")
                player_content = get_github_file_content(player_file_path)
                if player_content:
                    all_players.append(player_content)
                    print(f"DEBUG: Successfully loaded player: {player_content.get('username', 'N/A')}")
                else:
                    print(f"DEBUG: Could not load player data from {player_file_path}. Skipping.")
    elif response.status_code == 404:
        print(f"DEBUG: Players directory '{PLAYERS_DIR_PATH}' not found on GitHub. Assuming no players yet.")
    else:
        print(f"DEBUG: Failed to list players directory {PLAYERS_DIR_PATH}. Status: {response.status_code}, Response: {response.text}")
    return all_players

def save_single_player_data(player_data):
    player_uuid = player_data.get('uuid')
    if not player_uuid:
        print("ERROR: Player data has no UUID. Cannot save.")
        return False, {"message": "Player data missing UUID"}

    path = f'{PLAYERS_DIR_PATH}/{player_uuid}.json'
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = f'{"Update" if sha else "Create"} player data for {player_data.get("username", "unknown")}'
    success, response = put_github_file_content(path, player_data, message, sha)
    if not success:
        print(f"ERROR: save_single_player_data failed for {path}. Response: {response}")
    return success, response

# --- パックレジストリ管理 ---
PACK_REGISTRY_PATH = 'pack_registry.json'
PACKS_EXTRACTED_BASE_PATH = 'packs_extracted'

def load_pack_registry():
    registry = get_github_file_content(PACK_REGISTRY_PATH)
    return registry if registry is not None else []

def save_pack_registry(registry_data):
    path = PACK_REGISTRY_PATH
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = 'Update pack registry'
    success, response = put_github_file_content(path, registry_data, message, sha)
    if not success:
        print(f"ERROR: save_pack_registry failed for {path}. Response: {response}")
    return success, response

def parse_mc_pack(pack_file_path):
    pack_info = None
    temp_dir = None
    print(f"DEBUG: Starting parse_mc_pack for: {pack_file_path}")
    try:
        temp_dir = tempfile.mkdtemp()
        print(f"DEBUG: Created temporary extraction directory: {temp_dir}")
        
        if not zipfile.is_zipfile(pack_file_path):
            print(f"ERROR: File is not a valid ZIP file: {pack_file_path}")
            return None, None

        with zipfile.ZipFile(pack_file_path, 'r') as zip_ref:
            print(f"DEBUG: Contents of zip file {pack_file_path}:")
            zip_contents = zip_ref.namelist()
            for name in zip_contents:
                print(f"  - {name}")

            manifest_in_zip_path = None
            for name in zip_contents:
                if name.endswith('manifest.json') and 'manifest.json' in name:
                    manifest_in_zip_path = name
                    break
            
            if manifest_in_zip_path:
                print(f"DEBUG: Found manifest.json inside zip at: {manifest_in_zip_path}")
                with zip_ref.open(manifest_in_zip_path) as manifest_file:
                    manifest = json.load(manifest_file)
                
                print(f"DEBUG: manifest.json found and loaded. Content: {json.dumps(manifest, indent=2)}")
                
                header = manifest.get('header', {})
                modules = manifest.get('modules', [])

                pack_id = header.get('uuid')
                pack_name = header.get('name')
                pack_version = header.get('version')
                pack_type = "unknown"

                for module in modules:
                    if module.get('type') == 'resources':
                        pack_type = 'resource'
                        break
                    elif module.get('type') == 'data':
                        pack_type = 'behavior'
                        break
                    elif module.get('type') == 'script':
                        pack_type = 'behavior'
                        break
                    elif module.get('type') == 'client_data':
                        pack_type = 'resource'
                        break
                    elif module.get('type') == 'skin_pack':
                        pack_type = 'skin'
                        break
                
                if pack_id and pack_name and pack_version:
                    sanitized_pack_name = secure_filename(pack_name)
                    pack_info = {
                        'id': pack_id,
                        'name': pack_name,
                        'version': pack_version,
                        'type': pack_type,
                        'filename': os.path.basename(pack_file_path),
                        'sanitized_name': sanitized_pack_name,
                        'extracted_path': f'{PACKS_EXTRACTED_BASE_PATH}/{pack_type}/{sanitized_pack_name}'
                    }
                    print(f"DEBUG: Parsed pack info successfully: {pack_info}")

                    zip_ref.extractall(temp_dir)
                    print(f"DEBUG: Full pack extracted to: {temp_dir}")

                else:
                    print(f"WARNING: manifest.json missing essential header info (uuid, name, or version): {manifest_in_zip_path}")
            else:
                print(f"WARNING: manifest.json not found anywhere in pack: {pack_file_path}")
                
    except zipfile.BadZipFile:
        print(f"ERROR: Not a valid zip file (BadZipFile): {pack_file_path}")
        traceback.print_exc()
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid manifest.json format in {pack_file_path}: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR: Error processing pack {pack_file_path}: {e}")
        traceback.print_exc()
    finally:
        pass 
    return pack_info, temp_dir

def list_available_packs():
    registry = load_pack_registry()
    print(f"DEBUG: Loaded pack registry: {registry}")
    return registry

def load_world_data(player_uuid):
    worlds = []
    world_dir_path = f'worlds/{player_uuid}'
    url = f'{GITHUB_API_BASE_URL}/{world_dir_path}'
    response = requests.get(url, headers=HEADERS)

    print(f"DEBUG: Attempting to list world directory: {world_dir_path}. Status: {response.status_code}")
    if response.status_code == 200:
        github_items = response.json()
        print(f"DEBUG: Found {len(github_items)} items in {world_dir_path} on GitHub.")

        for item in github_items:
            print(f"DEBUG: Processing item: {item['name']} (Type: {item['type']})")
            if item['type'] == 'file' and item['name'].endswith('.json') and '-metadata-' in item['name']:
                filename_without_ext = item['name'].rsplit('.json', 1)[0]
                
                parts_by_metadata = filename_without_ext.split('-metadata-')
                
                if len(parts_by_metadata) == 2:
                    world_name_from_filename = parts_by_metadata[0]
                    uuid_part = parts_by_metadata[1]
                    
                    if len(uuid_part) == 73 and uuid_part[36] == '-':
                        player_uuid_in_filename = uuid_part[:36]
                        world_uuid_from_filename = uuid_part[37:]
                    else:
                        print(f"DEBUG: Invalid UUID format in filename (length/hyphen check): '{item['name']}'. UUID part: '{uuid_part}'. Skipping.")
                        continue

                    if player_uuid_in_filename != player_uuid:
                        print(f"DEBUG: Skipping world '{item['name']}' as player UUID in filename ({player_uuid_in_filename}) does not match current user ({player_uuid}).")
                        continue

                    print(f"DEBUG: Loading metadata for world: {item['name']}")
                    metadata_content = get_github_file_content(f'{world_dir_path}/{item["name"]}')
                    if metadata_content:
                        worlds.append({
                            'world_name': metadata_content.get('world_name', world_name_from_filename),
                            'world_uuid': metadata_content.get('world_uuid', world_uuid_from_filename),
                            'player_uuid': metadata_content.get('player_uuid', player_uuid),
                            'seed': metadata_content.get('seed', 'N/A'),
                            'game_mode': metadata_content.get('game_mode', 'survival'),
                            'cheats_enabled': metadata_content.get('cheats_enabled', False),
                            'resource_packs': metadata_content.get('resource_packs', []),
                            'behavior_packs': metadata_content.get('behavior_packs', [])
                        })
                        print(f"DEBUG: Successfully added world: {metadata_content.get('world_name', 'N/A')} (UUID: {metadata_content.get('world_uuid', 'N/A')})")
                    else:
                        print(f"DEBUG: Could not load metadata content for {item['name']}. Skipping.")
                else:
                    print(f"DEBUG: Filename format mismatch (no -metadata- separator): '{item['name']}'. Skipping.")
            else:
                print(f"DEBUG: Skipping non-metadata file or non-json: '{item['name']}'.")
    elif response.status_code == 404:
        print(f"DEBUG: World directory '{world_dir_path}' not found on GitHub. Assuming no worlds for this player.")
    else:
        print(f"DEBUG: Failed to load world directory {world_dir_path}. Status: {response.status_code}, Response: {response.text}")
    return worlds

def save_world_data(player_uuid, world_name, data):
    world_uuid_for_path = data.get('world_uuid', str(uuid.uuid4()))
    path = f'worlds/{player_uuid}/{world_name}-metadata-{player_uuid}-{world_uuid_for_path}.json'
    
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = f'{"Update" if sha else "Create"} world metadata for {world_name}'
    success, response = put_github_file_content(path, data, message, sha)
    if not success:
        print(f"ERROR: save_world_data failed for {path}. Response: {response}")
    return success



# Pygletゲームプロセスの管理
game_process = None
game_output_buffer = []
game_output_lock = threading.Lock()

# Pygletゲームの出力をリアルタイムでキャプチャするスレッド
def capture_game_output(pipe):
    global game_output_buffer
    for line in iter(pipe.readline, b''):
        with game_output_lock:
            game_output_buffer.append(line.decode('utf-8'))
    pipe.close()

# GitHubからmanifest.jsonをダウンロードする関数
def get_manifest_from_github(repo_path):
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("GitHub認証情報が設定されていません。manifest.jsonをダウンロードできません。")
        return None

    url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{repo_path}/manifest.json'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.com.v3.raw', # 生のファイルコンテンツを取得
        'User-Agent': 'Flask-Minecraft-Server'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
        return json.loads(response.text)
    except requests.exceptions.RequestException as e:
        print(f"manifest.jsonのダウンロード中にエラーが発生しました: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"manifest.jsonのデコード中にエラーが発生しました: {e}")
        return None








# ------------------------------
# 2. 認証関連ルート (GitHub Pagesからのfetch POSTに対応)
# ------------------------------

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    player = PLAYER_DATA.get(username)
    
    if player and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
        # 認証成功
        session.permanent = True 
        session['username'] = player['username']
        session['player_uuid'] = player['uuid']
        
        # NOTE: Flaskはレスポンスに自動的にセッションCookie (Set-Cookie) を含めます
        return jsonify({
            'success': True,
            'message': f"ログインしました。",
            'redirect_url': 'index.html' 
        }), 200
    else:
        # 認証失敗
        return jsonify({
            'success': False, 
            'message': 'ユーザー名またはパスワードが違います。'
        }), 401 
        print("ログインページの表示…")

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """GitHub Pagesから現在のログイン状態をチェックするAPI"""
    if 'username' in session:
        return jsonify({
            'logged_in': True,
            'username': session['username'],
            'uuid': session['player_uuid'],
            # 必要に応じてプロフィール画像URLなども含める
            'profile_img': 'https://dummyimage.com/40x40/f00/fff&text=' + session['username'][0].upper()
        }), 200
    else:
        return jsonify({
            'logged_in': False
        }), 200
        print("ステータスページの表示…")


# ... /register ルートも同様にJSONを返すAPIとして実装されます ...

# ------------------------------
# 3. YouTube風 API ルート (/API/yt/*)
# ------------------------------

# --- ダミーデータ ---
DUMMY_CHANNEL = {
    'id': 'UCLFpG2c8yM8Rj-29K99QoXQ',
    'name': 'カカオマメちゃんねる',
    'subs': '1.2万',
    'img': 'https://dummyimage.com/80x80/000/fff&text=CM',
    'banner': 'https://dummyimage.com/1280x200/555/fff&text=Channel+Banner',
    'desc': 'マイクラJava版配布ワールドを統合版にするための奮闘記と、日々のWeb開発記録をお届けします。',
    'join_date': '2025-06-20',
}

def create_dummy_video(index):
    """ダミー動画データを生成するヘルパー関数"""
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

# --- API実装 ---

@app.route('/API/yt/videos/home', methods=['GET'])
def home_videos():
    """index.html用の動画グリッドデータを返すAPI"""
    videos = [create_dummy_video(i) for i in range(1, 21)]
    return jsonify({'videos': videos}), 200
    print("ホームに表示するvideo APIの表示…")
    

@app.route('/API/yt/search', methods=['GET'])
def search_videos():
    """search.html用の検索結果リストを返すAPI"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'results': []}), 200

    # 検索クエリに基づいたダミーデータを生成
    results = [create_dummy_video(i) for i in range(1, 11)]
    for i, result in enumerate(results):
        result['title'] = f"【検索結果】{query}を含む動画 #{i+1}"
    
    return jsonify({'results': results}), 200
    print("検索APIの表示…")


@app.route('/API/yt/video', methods=['GET'])
def video_metadata():
    """watch.html用の単一動画メタデータを返すAPI"""
    video_id = request.args.get('v')
    if not video_id:
        return jsonify({'error': 'Video ID is missing'}), 400

    video_data = create_dummy_video(int(video_id.replace('v', '').replace('abcde', '')))
    
    # コメントデータも追加（watch.htmlで必要になる可能性）
    video_data['comment_count'] = 125
    video_data['comments'] = [{'author': 'PlayerA', 'text': '参考になりました！'}, {'author': 'PlayerB', 'text': '次も期待しています！'}]
    
    return jsonify(video_data), 200
    print("video APIの表示…")





@app.route('/API/yt/iframe/<video_id>', methods=['GET'])
def video_iframe(video_id):
    """
    iframeタグ用の埋め込みURLをJSONで返すAPI
    GitHubの設定ファイルからパラメータを動的に取得するロジックを実装。
    """
    
    # 失敗時のフォールバックURL（デフォルト）
    fallback_url = f"{DEFAULT_EMBED_BASE}{video_id}"
    
    try:
        # 1. GitHubから設定ファイルをフェッチ (タイムアウト設定推奨)
        # NOTE: 外部リクエストには requests ライブラリを使用
        response = requests.get(CONFIG_URL, timeout=5)
        response.raise_for_status() # HTTPエラー (4xx, 5xx) を例外として処理
        
        config_data = response.json()
        params_string = config_data.get('params', '')

        # 2. パラメータのクリーニングと処理 (JSロジックの再現)
        
        # &amp; を & に置換 (JSロジックの再現)
        params_string = params_string.replace('&amp;', '&')
        
        # クエリ文字列を辞書として解析 (parse_qsは値をリストで返す)
        query_params = parse_qs(params_string)
        
        # URLSearchParamsの動作を模倣: キーが重複した場合、リストの最後の値を採用
        final_params = {}
        for key, value_list in query_params.items():
            # decodeURIComponentの処理はparse_qsが自動でやってくれる
            final_params[key] = value_list[-1]
            
        # URLエンコードし、クエリ文字列を構築
        final_params_string = urlencode(final_params)
        
        # 3. 最終的な埋め込みURLを構築
        embed_src = fallback_url # デフォルトをセット
        if final_params_string:
            embed_src += f"?{final_params_string}"
            
        print(f"DEBUG: Iframe URL generated with config: {embed_src}")
        return jsonify({'iframe_url': embed_src}), 200
        
    except requests.exceptions.RequestException as e:
        # 外部フェッチ失敗 (ネットワーク、404など)
        print(f"ERROR: Config file fetch failed, falling back: {e}")
        # フォールバックURLを返す
        return jsonify({'iframe_url': fallback_url}), 200
        
    except json.JSONDecodeError as e:
        # JSON解析失敗
        print(f"ERROR: Config file JSON decoding failed, falling back: {e}")
        # フォールバックURLを返す
        return jsonify({'iframe_url': fallback_url}), 200
        
    except Exception as e:
        # その他の予期せぬエラー
        print(f"ERROR: Unexpected error in iframe API, falling back: {e}")
        # フォールバックURLを返す
        return jsonify({'iframe_url': fallback_url}), 200
        print("動画埋め込みlink APIの表示…")












# ... (他の設定やインポートは省略されています) ...

@app.route('/API/yt/channel', methods=['GET'])
def channel_metadata():
    # ... (URL生成、HTML取得、JSON抽出のロジックはV7/V8と同じ) ...
    print(f"DEBUG: Attempting to scrape URL: {url}")
    data = None 

    try:
        # 1. HTML取得とJSON抽出のコード (省略せずに全てtryブロック内に含む)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        match = re.search(r'var ytInitialData = (.*?);</script>', html_content, re.DOTALL)
        if not match:
            return jsonify({'error': 'Initial channel data (ytInitialData) not found.'}), 500
        data = json.loads(match.group(1))

        # 2. 必要な情報の抽出 (最も可能性の高いレンダラーを優先)
        
        channel_info = data.get('metadata', {}).get('channelMetadataRenderer')
        
        if not channel_info:
            # チャンネルヘッダーをフォールバックとして探索 (pageHeaderRendererも含む)
            header_data = data.get('header', {})
            for key in ['channelHeaderRenderer', 'c4TabbedHeaderRenderer', 'engagementPanelTitleHeaderRenderer', 'pageHeaderRenderer']: # 👈 pageHeaderRendererを追加
                if key in header_data:
                    channel_info = header_data.get(key)
                    print(f"DEBUG: Found channel info in fallback renderer: {key}")
                    break

        if not channel_info:
            return Response(json.dumps({'error': 'メタデータ構造が見つかりません。'}, ensure_ascii=False), mimetype='application/json'), 500

        # 情報抽出 (タイトルは simpleText 構造にも対応)
        
        channel_name_obj = channel_info.get('title') or channel_info.get('pageTitle')
        if isinstance(channel_name_obj, dict) and 'simpleText' in channel_name_obj:
             channel_name = channel_name_obj['simpleText']
        else:
             channel_name = channel_name_obj or 'チャンネル名不明'
             
        description = channel_info.get('description') or ''
        
        # 登録者数は header のみから探す
        subscriber_text = "登録者数不明"
        if 'header' in data:
            header_data = data['header']
            for key in header_data.keys():
                if key.endswith('HeaderRenderer'):
                    header = header_data.get(key)
                    if header:
                        sub_obj = header.get('subscriberCountText') or header.get('subscribersText')
                        if sub_obj and isinstance(sub_obj, dict) and 'simpleText' in sub_obj:
                            subscriber_text = sub_obj['simpleText']
                            break

        # プロフィール画像
        avatar_obj = channel_info.get('avatar') or channel_info.get('image') # pageHeaderRendererのimageに対応
        if avatar_obj and avatar_obj.get('thumbnails'):
             profile_img_url = avatar_obj.get('thumbnails', [{}])[-1].get('url', 'https://dummyimage.com/80x80/000/fff&text=CM')
        elif avatar_obj and avatar_obj.get('decoratedAvatarViewModel', {}).get('avatar', {}).get('avatarViewModel', {}).get('image', {}).get('sources'): # pageHeaderRendererの複雑な構造に対応
             sources = avatar_obj['decoratedAvatarViewModel']['avatar']['avatarViewModel']['image']['sources']
             profile_img_url = sources[-1]['url']
        else:
             profile_img_url = 'https://dummyimage.com/80x80/000/fff&text=CM'
        
        # 最終結果をJSONで返す (ensure_ascii=Falseで日本語をエスケープしない)
        final_data = {
            'channel_id': channel_id,
            'channel_name': channel_name,
            'subscriber_count': subscriber_text,
            'profile_image_url': profile_img_url,
            'banner_image_url': '', 
            'description': description,
            'join_date': ''
        }
        json_response = json.dumps(final_data, ensure_ascii=False, indent=4)
        return Response(json_response, mimetype='application/json'), 200

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return Response(json.dumps({'error': f'チャンネルが見つかりません。ID/ハンドル({channel_id})を確認してください。'}, ensure_ascii=False), mimetype='application/json'), 404
        return Response(json.dumps({'error': f'外部URLの取得に失敗しました: {e}'}, ensure_ascii=False), mimetype='application/json'), 503
    except Exception as e:
        print(f"ERROR: Unexpected error in channel API: {e}")
        return Response(json.dumps({'error': f'サーバー側で予期せぬエラーが発生しました: {type(e).__name__}'}, ensure_ascii=False), mimetype='application/json'), 500


        

@app.route('/API/yt/channel/videos', methods=['GET'])
def channel_videos():
    """
    内部 API (/youtubei/v1/browse) を使用して、チャンネルの動画リストを返す。
    ytcfgからAPIキーを取得し、APIを叩く。
    """
    channel_id = request.args.get('c')
    if not channel_id:
        return jsonify({'error': 'Channel ID is missing'}), 400

    # チャンネルURLを構築し、HTMLを取得
    if channel_id.startswith('@'):
        url = f"https://www.youtube.com/{channel_id}"
    elif 'UC' in channel_id or '@' not in channel_id:
        url = f"https://www.youtube.com/channel/{channel_id}"
    else:
        url = f"https://www.youtube.com/@{channel_id}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_content = response.text

        # 1. ytcfgからAPIキーとクライアント情報を取得
        ytcfg = extract_ytcfg_data(html_content)
        api_key = ytcfg.get('INNERTUBE_API_KEY')
        client_name = ytcfg.get('client', {}).get('clientName', 'WEB')
        client_version = ytcfg.get('client', {}).get('clientVersion', '2.20251025.09.00')

        if not api_key:
            return jsonify({'videos': [], 'error': '動画リスト APIキーが見つかりませんでした。'}), 500

        # 2. APIエンドポイントURLとペイロードを構築
        api_url = f"https://www.youtube.com/youtubei/v1/browse?key={api_key}"
        
        # 内部APIを叩くためのペイロード。videosタブを取得するためのbrowseIdとparamsを使用
        payload = {
            # BROWSE_ID_FOR_VIDEOS_TAB_CONTENT はチャンネルIDのUC...形式である必要あり
            # 今回は /videos にアクセスした際のコンテキストを使用するため、browseIdを元に構築
            "browseId": channel_id if channel_id.startswith('UC') else None,
            "params": "EgZ2aWRlb3M%3D", # Base64 for 'videos' - 動画タブの内容を取得するためのパラメータ
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

        # 4. JSONレスポンスから動画リストを抽出 (このパスは比較的安定しています)
        contents_path = api_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [{}])
        
        # 最初のタブ (動画タブ) の中を深く探索
        videos_tab_content = contents_path[0].get('tabRenderer', {}).get('content', {}) \
                               .get('sectionListRenderer', {}).get('contents', [{}])[0] \
                               .get('itemSectionRenderer', {}).get('contents', [{}])[0] \
                               .get('gridRenderer', {})

        video_renderers = videos_tab_content.get('items', [])
                       
        videos = []
        for item in video_renderers:
            renderer = item.get('gridVideoRenderer')
            if not renderer: continue

            video_id = renderer.get('videoId')
            title = renderer.get('title', {}).get('runs', [{}])[0].get('text', 'タイトル不明')
            
            published_time = renderer.get('publishedTimeText', {}).get('simpleText', '公開日不明')
            view_count_text = renderer.get('viewCountText', {}).get('simpleText', '視聴回数不明')
            thumbnail_url = renderer.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', 'dummy')

            videos.append({
                'video_id': video_id,
                'title': title,
                'thumbnail_url': thumbnail_url,
                'channel_name': channel_id, 
                'views': view_count_text,
                'published_at': published_time,
            })

        print(f"DEBUG: Found {len(videos)} videos via internal API.")
        return jsonify({'videos': videos}), 200

    except Exception as e:
        print(f"ERROR: Internal API video list scraping failed: {e}")
        return jsonify({'error': f'動画リストの取得に失敗しました: {type(e).__name__}'}), 500
    print("チャンネル動画データAPIの表示…")
        


@app.route('/API/yt/playlist', methods=['GET'])
def playlist_data():
    """playlist.html用の再生リストデータと動画リストを返すAPI"""
    playlist_id = request.args.get('list')
    if not playlist_id:
        return jsonify({'error': 'Playlist ID is missing'}), 400

    videos = [create_dummy_video(i) for i in range(1, 6)] # 5本の動画
    
    return jsonify({
        'title': f"マイクラ神ワザ集 【リストID:{playlist_id}}}",
        'channel_name': DUMMY_CHANNEL['name'],
        'description': 'マイクラで使える便利なテクニックをまとめた再生リストです。',
        'video_count': len(videos),
        'videos': videos
    }), 200
    print("プレイリストAPIの表示…")


# ------------------------------
# 4. アプリケーションのエントリポイント
# ------------------------------



# Vercelデプロイ用: Vercelは 'app' オブジェクトを自動でエクスポートします

@app.route('/')
def index():
    print("indexページを表示しました")
    message = request.args.get('message')
    return render_template('index.html', message=message)

        
@app.route('/home')
def home():
    print("ホームページを表示しました")
    message = request.args.get('message')
    return render_template('home.html', message=message)
    

@app.route('/setting')
def setting():
    print("設定ページを表示しました")
    return render_template('setting.html')
    

@app.route('/store')
def store():
    print("ストアページを表示しました")
    return render_template('store.html')
    


# ... 他のimport (hashlibなど) は省略

# ... (app = Flask(__name__), SECRET_KEYの設定、load_all_player_data関数などは省略)

@app.route('/logins', methods=['POST'])
# GETリクエストはGitHub Pages側で処理するため、POSTのみ残します
def logins():
    # GitHub Pagesからの fetch POST を想定
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'ユーザー名とパスワードを入力してください。'}), 400

    # ユーザーデータ読み込み (load_all_player_data() は実装済みと仮定)
    players = load_all_player_data()
    
    authenticated_player = None
    for player in players:
        # データベースのハッシュ値と入力されたパスワードのハッシュ値を比較
        # hashlib.sha256(password.encode()).hexdigest() は実装済みと仮定
        if player['username'] == username and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
            authenticated_player = player
            break

    if authenticated_player:
        # 認証成功
        session.permanent = True 
        session['username'] = authenticated_player['username']
        session['player_uuid'] = authenticated_player['uuid']
        session.pop('is_offline_player', None) 
        
        print(f"DEBUG: ユーザー '{username}' がログインしました。セッションCookieがセットされました。")
        
        # 🌟 JSONを返す (Flaskのredirectは削除) 🌟
        return jsonify({
            'success': True,
            'message': f"ようこそ、{username}さん！",
            # 成功後、GitHub Pages側で遷移させるURLを渡す
            'redirect_url': 'index.html' # GitHub Pagesのホーム画面へ
        }), 200
    else:
        # 認証失敗
        print(f"DEBUG: ログイン失敗 - ユーザー名: {username}")
        return jsonify({
            'success': False, 
            'message': 'ユーザー名またはパスワードが違います。'
        }), 401 # 401 Unauthorized

# ... 他のルート（/register, /API/...）

    print("ログインページ(サブ)を表示しました")
    return render_template('login.html')
    

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    session.pop('is_offline_player', None)
    flash("ログアウトしました。", "info")
    print("DEBUG: ユーザーがログアウトしました。")
    return redirect(url_for('home'))

# ... 省略 ...

@app.route('/register', methods=['GET', 'POST'])
def register():
    # GETリクエスト（直接アクセス）の場合は、通常通りテンプレートを返す
    if request.method == 'GET':
        return render_template('register.html')
    
    # POSTリクエスト（GitHub PagesからのAJAXを想定）
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_all_player_data()
        
        if any(p['username'] == username for p in players):
            # 失敗: ユーザー名重複
            # flash('このユーザー名はすでに使用されています。', "error") # AJAXではflashは使えない
            return jsonify({
                'success': False, 
                'message': 'このユーザー名はすでに使用されています。'
            }), 400 # 400 Bad Request
        
        new_uuid = str(uuid.uuid4())
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        success, response_data = save_single_player_data(new_player)
        
        if success:
            # 成功: JSONを返す
            # flash('アカウントが正常に作成されました！ログインしてください。', "success") # AJAXではflashは使えない
            return jsonify({
                'success': True,
                'message': 'アカウントが正常に作成されました！',
                'redirect_url': 'https://minecraft-flask-app-gold.vercel.app/login' 
            }), 201 # 201 Created
        else:
            # 失敗: GitHub保存エラー
            return jsonify({
                'success': False,
                'message': 'アカウント作成に失敗しました。GitHub設定を確認してください。',
                'error_details': response_data
            }), 500 # 500 Internal Server Error

# ... 省略 ...
    



    

@app.route('/server')
def server_page():
    print("サーバーページを表示しました")
    return render_template('server.html')


if __name__ == '__main__':
    # Flaskアプリを起動
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False) # use_reloader=False でPygletが二重起動するのを防ぐ

