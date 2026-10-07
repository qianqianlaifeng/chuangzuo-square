# -*- coding: utf-8 -*-
"""
创作广场 · 实时直连服务
=====================================================
一个文件搞定：静态网页 + 豆包接口代理（同域，绕开 CORS）。

  http://127.0.0.1:8788/                  -> 网页
  GET  /api/works                         -> 作品链接列表（works.json）
  POST /api/works   {"url": "分享链接"}    -> 添加作品链接
  GET  /api/resolve?share_id=&vid=        -> 实时调用豆包，返回视频/作者/提示词
  GET  /api/stream?url=<编码后地址>        -> 代理视频/封面流（解决 CDN Referer 限制）

只用 Python 标准库，零依赖。双击「本地预览.bat」即可。
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
WORKS = os.path.join(ROOT, "works.json")
PORT = int(os.environ.get("PORT", "8788"))

API = "https://www.doubao.com/creativity/share/get_video_share_info"
Q = ("version_code=20800&language=zh-CN&device_platform=web&aid=497858&real_aid=497858"
     "&pkg_type=release_version&pc_version=2.51.7&samantha_web=1&use-olympus-account=1")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) "
      "WindowsWechat(0x63090a13) XWEB/14315 Flue")

_CTX = ssl.create_default_context()
_CTX_NV = ssl._create_unverified_context()

# 解析结果缓存：避免每次刷新都打豆包，也能防限流（视频直链约 7 天过期，10 分钟缓存足够“实时”）
_RESOLVE_TTL = 600
_CACHE = {}  # key "sid:vid" -> [timestamp, result]


def _get(url, data=None, headers=None, timeout=30):
    h = {"User-Agent": UA, "Referer": "https://www.doubao.com/"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=("POST" if data else "GET"))
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_CTX)
    except ssl.SSLError:
        return urllib.request.urlopen(req, timeout=timeout, context=_CTX_NV)


# ---------------- 作品链接存储 ----------------
def load_works():
    if not os.path.exists(WORKS):
        return []
    try:
        with open(WORKS, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("items", []) if isinstance(d, dict) else (d or [])
    except Exception:
        return []


def save_works(items):
    with open(WORKS, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)


def parse_link(s):
    sid = vid = ""
    m = re.search(r"share_id=([0-9]+)", s or "")
    if m:
        sid = m.group(1)
    m = re.search(r"(?:video_id|vid)=([A-Za-z0-9]+)", s or "")
    if m:
        vid = m.group(1)
    if not sid:
        t = (s or "").split()
        if len(t) >= 2 and t[0].isdigit():
            sid, vid = t[0], t[1]
        elif t and t[0].isdigit():
            sid = t[0]
    return sid, vid


# ---------------- 实时调用豆包 ----------------
def resolve(sid, vid):
    if not sid or not vid:
        return {"ok": False, "error": "链接里缺少 share_id 或 video_id"}
    key = sid + ":" + vid
    now = time.time()
    hit = _CACHE.get(key)
    if hit and (now - hit[0]) < _RESOLVE_TTL:
        return hit[1]
    body = json.dumps({"share_id": sid, "vid": vid, "creation_id": ""}).encode("utf-8")
    try:
        r = _get(API + "?" + Q, data=body, headers={
            "Content-Type": "application/json",
            "Origin": "https://www.doubao.com",
            "Accept": "application/json, text/plain, */*",
        }, timeout=25)
        j = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "error": "请求豆包失败 %s" % e}
    if j.get("code") != 0 or not j.get("data"):
        return {"ok": False, "error": "豆包返回 code=%s" % j.get("code")}

    d = j["data"]
    play = d.get("play_info") or {}
    ui = d.get("user_info") or {}
    prompt = (d.get("prompt") or "").strip()
    dur = ""
    m = re.search(r"时长\s*([0-9.]+)\s*s", prompt)
    if m:
        dur = m.group(1) + "s"
    model = ""
    m = re.search(r"模型\s*([0-9.]+)", prompt)
    if m:
        model = "Seedance " + m.group(1)
    result = {
        "ok": True,
        "share_id": sid,
        "vid": vid,
        "author": (ui.get("nickname") or "豆包用户").strip(),
        "prompt": prompt,
        "duration": dur,
        "model": model,
        "width": play.get("width") or 720,
        "height": play.get("height") or 1280,
        "definition": play.get("definition") or "",
        "video": play.get("main") or play.get("backup") or "",
        "poster": play.get("poster_url") or "",
        "source_url": "https://www.doubao.com/video-sharing?share_id=%s&video_id=%s" % (sid, vid),
    }
    _CACHE[key] = [now, result]
    return result


# ---------------- HTTP ----------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _json(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        if path == "/api/works":
            return self._json({"items": load_works()})

        if path == "/api/resolve":
            sid = q.get("share_id", [""])[0]
            vid = q.get("vid", [""])[0]
            return self._json(resolve(sid, vid))

        if path == "/api/stream":
            u = q.get("url", [""])[0]
            return self.stream(u)

        if path == "/" or path == "":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/works":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                j = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return self._json({"ok": False, "error": "请求体不是合法 JSON"}, 400)
            url = (j or {}).get("url", "")
            sid, vid = parse_link(url)
            if not sid or not vid:
                return self._json({"ok": False, "error": "没有从链接里识别出 share_id / video_id"}, 400)
            items = load_works()
            if not any(w.get("share_id") == sid and w.get("vid") == vid for w in items):
                items.insert(0, {"share_id": sid, "vid": vid})
                save_works(items)
                added = True
            else:
                added = False
            return self._json({"ok": True, "added": added, "items": items})
        self.send_error(405)

    def stream(self, url):
        if not url or not url.startswith("http"):
            return self.send_error(400)
        rng = self.headers.get("Range")
        req_headers = {"Accept": "*/*"}
        if rng:
            req_headers["Range"] = rng
        try:
            up = _get(url, headers=req_headers, timeout=60)
        except Exception:
            return self.send_error(502)
        status = up.status
        ctype = up.headers.get("Content-Type", "application/octet-stream")
        total = up.headers.get("Content-Length")
        crange = up.headers.get("Content-Range")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if total:
            self.send_header("Content-Length", total)
        if crange:
            self.send_header("Content-Range", crange)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=600")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                chunk = up.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    if not os.path.exists(WORKS):
        save_works([{"share_id": "41356597786354690",
                     "vid": "v0d69cg10004d6978e2ljht0i4fdpp00"}])
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 52)
    print("  创作广场 · 实时直连服务已启动")
    print("  电脑打开   http://127.0.0.1:%d/" % PORT)
    print("  手机打开   http://<本机局域网IP>:%d/" % PORT)
    print("  停止服务   按 Ctrl + C")
    print("=" * 52)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
