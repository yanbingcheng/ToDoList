#!/usr/bin/env python3
"""待办事项 — 本地服务器 + 浏览器前端

数据存储在独立的 todos.json 文件中，index.html 为纯模板。
每次写入前自动备份到 backups/ 目录（保留最近 20 份）。
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime

PORT = 8765
URL = f'http://localhost:{PORT}/index.html'

_script_dir = os.path.dirname(os.path.abspath(__file__))

# Max backup files to keep
MAX_BACKUPS = 20


def _is_bundled():
    """True if running inside a py2app .app bundle."""
    return 'Contents/Resources' in os.path.dirname(os.path.abspath(__file__))


# Data lives in the .app bundle's Resources folder
if _is_bundled():
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Resources')
else:
    DATA_DIR = os.path.join(_script_dir, 'dist', 'To Do.app', 'Contents', 'Resources')

DATA_FILE = os.path.join(DATA_DIR, 'todos.json')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
HTML_FILE = os.path.join(DATA_DIR, 'index.html')
BUNDLED_HTML = os.path.join(_script_dir, 'index.html')


def read_todos():
    """Read todo list from JSON file."""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _backup_todos():
    """Create a timestamped backup of the current todos.json if it has data."""
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if len(data) == 0:
            return  # Don't backup empty files
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'todos_{ts}.json')
        shutil.copy2(DATA_FILE, backup_file)
        # Rotate: keep only the last MAX_BACKUPS
        backups = sorted([
            f for f in os.listdir(BACKUP_DIR) if f.startswith('todos_') and f.endswith('.json')
        ])
        for old in backups[:-MAX_BACKUPS]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except Exception:
        pass  # Backup failure should not block normal operation


def write_todos(data):
    """Write todo list to JSON file atomically, with backup."""
    _backup_todos()
    tmp = DATA_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def ensure_data_dir():
    """Ensure data directory and template files exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(HTML_FILE):
        shutil.copy2(BUNDLED_HTML, HTML_FILE)
    if not os.path.exists(DATA_FILE):
        write_todos([])
    else:
        # Startup backup — create a backup on first run of the session
        _backup_todos()


def server_running():
    try:
        req = urllib.request.Request(f'http://localhost:{PORT}/ping', method='GET')
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def _port_in_use():
    try:
        result = subprocess.run(
            ['lsof', '-ti', f'tcp:{PORT}'],
            capture_output=True, text=True
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _kill_port():
    try:
        result = subprocess.run(
            ['lsof', '-ti', f'tcp:{PORT}'],
            capture_output=True, text=True
        )
        for pid in result.stdout.strip().split():
            os.kill(int(pid), 9)
    except Exception:
        pass


def wait_for_server(timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_running():
            return True
        time.sleep(0.2)
    return False


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DATA_DIR, **kwargs)

    def do_GET(self):
        if self.path == '/ping':
            self._json_response(200, {'status': 'ok'})
            return
        if self.path == '/api/todos':
            self._json_response(200, read_todos())
            return
        if self.path == '/index.html' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            with open(HTML_FILE, 'rb') as f:
                self.wfile.write(f.read())
            return
        super().do_GET()

    def do_POST(self):
        if self.path == '/api/todos':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body)

                # Protection: reject empty data when file has existing data
                if len(data) == 0:
                    existing = read_todos()
                    if len(existing) > 0:
                        print(f'  [保护] 拒绝空数据覆盖，文件中有 {len(existing)} 条记录')
                        self._json_response(409, {
                            'ok': False,
                            'error': 'stale',
                            'message': '请刷新页面后重试'
                        })
                        return

                write_todos(data)
                self._json_response(200, {'ok': True})
                return
            except Exception as e:
                print(f'保存失败: {e}')

        self.send_response(404)
        self.end_headers()

    def _json_response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if args and '/ping' not in str(args[0]):
            print(f'  {fmt % args}')


def run_server():
    ensure_data_dir()
    server = http.server.HTTPServer(('localhost', PORT), Handler)
    server.allow_reuse_address = True
    print(f'待办事项服务器已启动: {URL}')
    print(f'数据文件: {DATA_FILE}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已关闭')
        server.shutdown()


def launch_browser():
    if sys.platform == 'darwin':
        subprocess.run(['open', URL], check=False)
    else:
        webbrowser.open(URL)


def _get_main_executable():
    exe_dir = os.path.dirname(sys.executable)
    for name in os.listdir(exe_dir):
        if name == 'python':
            continue
        candidate = os.path.join(exe_dir, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return sys.executable


def _start_daemon():
    if _is_bundled():
        cmd = [_get_main_executable(), '--serve']
    else:
        cmd = [sys.executable, os.path.abspath(__file__), '--serve']

    log_file = os.path.join(DATA_DIR, 'server.log')
    return subprocess.Popen(
        cmd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=open(log_file, 'a'),
        stderr=subprocess.STDOUT,
    )


def main():
    if server_running():
        print('服务器已在运行，直接打开浏览器...')
        launch_browser()
        return

    if _port_in_use():
        print('检测到残留服务器进程，正在清理...')
        _kill_port()
        time.sleep(0.5)

    server_proc = _start_daemon()

    if wait_for_server():
        print('待办事项已启动')
        launch_browser()
    else:
        print('服务器启动超时，请重试')
        server_proc.kill()


if __name__ == '__main__':
    if '--serve' in sys.argv:
        run_server()
    else:
        main()
