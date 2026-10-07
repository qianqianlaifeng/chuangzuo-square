# -*- coding: utf-8 -*-
"""尝试用「游客会话」打通 feed：
先 GET doubao.com 首页收集 Set-Cookie，再带着这些 cookie 打 /api/creativity/feed。
如果 401 消失，就不用用户账号了。
"""
import http.cookiejar
import json
import ssl
import urllib.request
import urllib.error

Q = ("version_code=20800&language=zh-CN&device_platform=web&aid=497858&real_aid=497858"
     "&pkg_type=release_version&pc_version=2.51.7&samantha_web=1")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
CTX = ssl._create_unverified_context()

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
    urllib.request.HTTPSHandler(context=CTX),
)
opener.addheaders = [
    ("User-Agent", UA),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ("Accept-Language", "zh-CN,zh;q=0.9"),
]


def get(url, extra=None):
    h = {"Accept": "application/json, text/plain, */*",
         "Referer": "https://www.doubao.com/"}
    if extra:
        h.update(extra)
    req = urllib.request.Request(url, headers=h)
    try:
        r = opener.open(req, timeout=15)
        return r.status, r.read(400).decode("utf-8", "replace"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "replace"), e.headers
    except Exception as e:
        return -1, str(e)[:150], {}


print("=== 1) 访问首页，收集游客 cookie ===")
code, txt, hdrs = get("https://www.doubao.com/")
print("  首页状态:", code)
print("  收集到 cookie 数量:", len(list(jar)))
for c in jar:
    print(f"    - {c.name} (domain={c.domain})")

print("\n=== 2) 带游客 cookie 打 feed ===")
code, txt, hdrs = get("https://www.doubao.com/api/creativity/feed?" + Q)
print("  feed 状态:", code)
print("  body:", txt[:200])

print("\n=== 3) 带游客 cookie + 常见游客参数 再打 ===")
code2, txt2, _ = get("https://www.doubao.com/api/creativity/feed?" + Q +
                     "&device_platform=web&channel=website&update_version_code=20800")
print("  feed 状态:", code2)
print("  body:", txt2[:200])

print("\n=== 结论 ===")
if code in (200,) or code2 == 200:
    print("  >>> 游客会话就能打通！不用用户账号")
else:
    print("  >>> 仍是 401，feed 强制要求登录账号 Cookie")