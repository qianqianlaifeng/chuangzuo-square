# -*- coding: utf-8 -*-
"""
创作广场 · 实时直连服务
=====================================================
一个文件搞定：静态网页 + 豆包接口代理（同域，绕开 CORS / 防盗链）。

  GET  /                        -> 网页
  GET  /api/status              -> 实时广场是否已开通
  GET  /api/feed?cursor=&count= -> 实时广场信息流（需要站主已配置登录态）
  POST /api/owner/login  {cookie} -> 站主贴一次豆包 Cookie，全站生效（只存内存）
  POST /api/owner/logout         -> 关闭实时广场
  GET  /api/works                -> 公开作品墙（降级用）
  POST /api/works  {"url": ...}  -> 添加公开作品链接
  GET  /api/resolve?share_id=&vid= -> 实时调用豆包，返回视频/作者/提示词
  GET  /api/stream?url=<编码地址>   -> 代理视频/封面（解决 CDN Referer 防盗链）

为什么是「站主共享一份登录态」而不是「每人登录各的」？
  手机没有 F12 取不到自己的 Cookie，且豆包 passport 登录接口对服务端
  返回 error_code:16（App 专属风控）。详见 _old/接口实测结论-最终版.md

只用 Python 标准库，零依赖。渲染平台读 $PORT，本地默认 8788。
"""

import base64
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
FEED = "https://www.doubao.com/api/creativity/feed"
Q = ("version_code=20800&language=zh-CN&device_platform=web&aid=497858&real_aid=497858"
     "&pkg_type=release_version&pc_version=2.51.7&samantha_web=1&use-olympus-account=1")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) "
      "WindowsWechat(0x63090a13) XWEB/14315 Flue")

def _mk_ctx(verify=True):
    """构造 SSL context。
    关键：把 cipher security level 降到 1、锁 TLS1.2 —— 部分环境（含某些容器/代理）
    默认 SECLEVEL=2 会直接 RST 连接，导致 UNEXPECTED_EOF_WHILE_READING。"""
    ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except Exception:
        pass
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=1")
    except Exception:
        pass
    return ctx


_CTX = _mk_ctx(True)
_CTX_NV = _mk_ctx(False)

# 解析结果缓存：避免每次刷新都打豆包，也能防限流（视频直链约 7 天过期，10 分钟缓存足够“实时”）
_RESOLVE_TTL = 600
_CACHE = {}  # key "sid:vid" -> [timestamp, result]


def _get(url, data=None, headers=None, timeout=30):
    """带 SSL 兜底与重试的 GET/POST。
    注意：每次重试都必须新建 Request（已消费的 request 不能复用）。"""
    h = {"User-Agent": UA, "Referer": "https://www.doubao.com/"}
    if headers:
        h.update(headers)
    method = "POST" if data else "GET"
    last = None
    for attempt in range(3):
        for ctx in (_CTX, _CTX_NV):
            try:
                req = urllib.request.Request(url, data=data, headers=h, method=method)
                return urllib.request.urlopen(req, timeout=timeout, context=ctx)
            except ssl.SSLError as e:
                last = e
            except Exception as e:
                msg = str(e)
                if "UNEXPECTED_EOF" in msg or "EOF occurred" in msg or "ECONNRESET" in msg:
                    last = e
                    continue
                raise
        time.sleep(0.5 * (attempt + 1))
    raise last if last else RuntimeError("请求失败")


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


# ---------------- 登录态 ----------------
# 为什么是「站主共享一份」而不是「每个访问者各登录各的」？
#   实测结论见 _old/接口实测结论-最终版.md
#   1) 豆包所有 passport 登录接口（短信/扫码）统一返回 error_code:16「请使用应用权限」，
#      服务端无法代替用户完成登录；
#   2) 游客会话（ttwid + hook_slardar_session_id）对 /api/ 无效，仍 401；
#   3) 手机浏览器没有 F12，取不到自己的 Cookie。
#   => 「每个访问者在手机上登录自己的账号」技术上不成立。
# 落地形态：站主在电脑浏览器登录一次，把 Cookie 贴进来（只存内存）；
#           所有访客无需登录，直接实时看广场。Cookie 过期后站主再贴一次。
OWNER_COOKIE = {"v": "", "at": 0.0}
FEED_CACHE = {"at": 0.0, "items": [], "cursor": ""}
FEED_TTL = 180  # 广场列表缓存 3 分钟：既实时又不打爆豆包


def set_owner_cookie(cookie):
    OWNER_COOKIE["v"] = cookie
    OWNER_COOKIE["at"] = time.time()
    FEED_CACHE["at"] = 0.0  # 立刻失效，下次请求重新拉


def owner_cookie():
    return OWNER_COOKIE["v"] or ""


def owner_ready():
    return bool(OWNER_COOKIE["v"])


def _pick(d, *keys):
    """从 dict 里取第一个非空值。"""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def extract_works(node, out):
    """递归遍历豆包 feed 返回，抽取含视频/提示词的条目。
    结构未知 => 用启发式：找到带 play_info 或 video 直链 + prompt 的节点。"""
    if isinstance(node, list):
        for x in node:
            extract_works(x, out)
        return
    if not isinstance(node, dict):
        return

    play = node.get("play_info") if isinstance(node.get("play_info"), dict) else None
    video = ""
    poster = ""
    if play:
        video = play.get("main") or play.get("backup") or ""
        poster = play.get("poster_url") or play.get("cover_url") or ""
    # 有些节点视频直链直接在 resource_url / video_url / url
    if not video:
        for k in ("resource_url", "video_url", "url", "main"):
            v = node.get(k)
            if isinstance(v, str) and re.search(r"\.mp4|video", v):
                video = v
                break
    prompt = _pick(node, "prompt", "prompt_text", "desc", "caption", "title", "content") or ""
    author = ""
    ui = node.get("user_info") if isinstance(node.get("user_info"), dict) else None
    if ui:
        author = (ui.get("nickname") or ui.get("name") or "").strip()

    if (video and (prompt or author)) and not any(w.get("_v") == video for w in out):
        dur = ""
        m = re.search(r"时长\s*([0-9.]+)\s*s", prompt)
        if m:
            dur = m.group(1) + "s"
        model = ""
        m = re.search(r"模型\s*([0-9.]+)", prompt)
        if m:
            model = "Seedance " + m.group(1)
        out.append({
            "_v": video,
            "author": author or "豆包用户",
            "prompt": prompt,
            "duration": dur,
            "model": model,
            "video": video,
            "poster": poster,
            "share_id": _pick(node, "share_id", "item_id", "id") or "",
            "vid": _pick(node, "vid", "video_id") or "",
            "width": 720, "height": 1280,
        })
        return

    # 继续往下找
    for v in node.values():
        if isinstance(v, (dict, list)):
            extract_works(v, out)


def feed_works(cookie, cursor="", count=20):
    """用站主的 cookie 调豆包广场 feed 接口，返回作品列表。
    结构未知 => extract_works 走启发式递归，尽量把视频和提示词都捞出来。"""
    url = FEED + "?" + Q + ("&cursor=" + urllib.parse.quote(str(cursor)) if cursor else "") \
        + "&count=%d&pull_type=feed" % count
    body = json.dumps({"cursor": str(cursor), "count": count, "pull_type": "feed"}).encode("utf-8")
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Origin": "https://www.doubao.com",
        "Referer": "https://www.doubao.com/",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        r = _get(url, data=body, headers=headers, timeout=25)
        raw = r.read().decode("utf-8", "replace")
        j = json.loads(raw)
    except Exception as e:
        return {"ok": False, "error": "请求豆包失败 %s" % e, "need_login": False}
    # code=0 才是成功；401 / 登录态失效都归为 need_login
    if j.get("code") != 0 or not j.get("data"):
        return {"ok": False, "need_login": True,
                "error": "豆包返回 code=%s msg=%s（登录态可能已失效）"
                         % (j.get("code"), j.get("msg", ""))}
    works = []
    extract_works(j.get("data"), works)
    for w in works:
        w.pop("_v", None)
    next_cursor = ""
    d = j.get("data")
    if isinstance(d, dict):
        next_cursor = str(_pick(d, "cursor", "next_cursor", "has_more_cursor") or "")
    return {"ok": True, "items": works, "cursor": next_cursor}


def public_feed(cursor="", count=20):
    """给访客的广场接口：有站主登录态就实时拉，没有就明确告诉他未开通。"""
    ck = owner_cookie()
    if not ck:
        return {"ok": False, "need_owner": True,
                "error": "站主还没配置豆包登录态，当前展示的是公开作品墙"}
    # 首页走缓存，翻页实时拉
    if not cursor and (time.time() - FEED_CACHE["at"]) < FEED_TTL and FEED_CACHE["items"]:
        return {"ok": True, "items": FEED_CACHE["items"], "cursor": FEED_CACHE["cursor"], "cached": True}
    res = feed_works(ck, cursor, count)
    if res.get("ok") and not cursor:
        FEED_CACHE["items"] = res["items"]
        FEED_CACHE["cursor"] = res["cursor"]
        FEED_CACHE["at"] = time.time()
    return res


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

        if path == "/api/feed":
            cursor = q.get("cursor", [""])[0]
            count = int(q.get("count", ["20"])[0] or 20)
            return self._json(public_feed(cursor, count))

        if path == "/api/status":
            return self._json({
                "ok": True,
                "live": owner_ready(),
                "note": "实时广场已开通" if owner_ready() else "当前为公开作品墙（站主未配置登录态）",
            })

        if path == "/" or path == "":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/owner/login":
            # 站主贴 Cookie：验证一次能拉到广场才收，避免存了废的
            try:
                n = int(self.headers.get("Content-Length", "0"))
                j = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return self._json({"ok": False, "error": "请求体不是合法 JSON"}, 400)
            cookie = (j or {}).get("cookie", "").strip()
            if not cookie or "=" not in cookie:
                return self._json({"ok": False, "error": "没有拿到 Cookie"}, 400)
            res = feed_works(cookie, "", 10)
            if not res.get("ok"):
                return self._json({"ok": False, "error": res.get("error", "验证失败"),
                                   "tip": "请确认这段 Cookie 来自已登录的 doubao.com 网页"}, 400)
            set_owner_cookie(cookie)
            return self._json({"ok": True, "count": len(res.get("items", []))})
        if parsed.path == "/api/owner/logout":
            OWNER_COOKIE["v"] = ""
            OWNER_COOKIE["at"] = 0.0
            FEED_CACHE["items"] = []
            FEED_CACHE["cursor"] = ""
            FEED_CACHE["at"] = 0.0
            return self._json({"ok": True})
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
