# -*- coding: utf-8 -*-
"""对比测试：share 接口(已知免鉴权能通) vs feed 接口(401)。
看 feed 401 的响应头里，提示需要哪种鉴权（Cookie / Authorization / X-Sign 等）。
"""
import json
import ssl
import urllib.request
import urllib.error

Q = ("version_code=20800&language=zh-CN&device_platform=web&aid=497858&real_aid=497858"
     "&pkg_type=release_version&pc_version=2.51.7&samantha_web=1")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
      "Version/17.5 Mobile/15E148 Safari/604.1")
CTX = ssl._create_unverified_context()


def probe(name, url, method="GET", body=None):
    h = {"User-Agent": UA, "Referer": "https://www.doubao.com/",
         "Accept": "application/json, text/plain, */*"}
    if body:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    print("=" * 60)
    print(f"[{name}] {method} {url.split('?')[0]}")
    try:
        r = urllib.request.urlopen(req, timeout=12, context=CTX)
        print("  状态:", r.status)
        for k, v in r.headers.items():
            if k.lower() in ("www-authenticate", "set-cookie", "content-type", "x-tt-logid"):
                print(f"  {k}: {v[:120]}")
        print("  body:", r.read(200).decode("utf-8", "replace")[:180])
    except urllib.error.HTTPError as e:
        print("  状态:", e.code)
        for k, v in e.headers.items():
            if k.lower() in ("www-authenticate", "set-cookie", "content-type", "x-tt-logid", "location"):
                print(f"  {k}: {v[:160]}")
        print("  body:", e.read(200).decode("utf-8", "replace")[:180])
    except Exception as e:
        print("  错误:", str(e)[:120])


# 1. 已知的 share 接口（免鉴权，对照组）
probe("share-对照",
      "https://www.doubao.com/creativity/share/get_video_share_info?" + Q,
      "POST", json.dumps({"share_id": "41356597786354690",
                          "vid": "v0d69cg10004d6978e2ljht0i4fdpp00",
                          "creation_id": ""}).encode())

# 2. feed 接口（401，看缺啥）
probe("feed-GET", "https://www.doubao.com/api/creativity/feed?" + Q)

# 3. feed 接口 POST 空 body
probe("feed-POST", "https://www.doubao.com/api/creativity/feed?" + Q,
      "POST", json.dumps({}).encode())

# 4. feed 接口带常见游客参数
probe("feed-游客", "https://www.doubao.com/api/creativity/feed?" + Q +
      "&device_id=1234567890123456&iid=1234567890123456&ac=wifi")