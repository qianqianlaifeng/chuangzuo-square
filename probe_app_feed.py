# -*- coding: utf-8 -*-
"""探测豆包移动端(App)真实创作广场信息流接口。
思路：App 里有满屏视频，网页端没有 => App 一定调了某个 feed/list 接口。
我们用移动端 UA + 常见 aid 去打，判定标准是【非 404】(401/710xxx 也算接口存在)。
"""
import json
import ssl
import urllib.request
import urllib.error

Q = ("version_code=20800&language=zh-CN&device_platform=web&aid=497858&real_aid=497858"
     "&pkg_type=release_version&pc_version=2.51.7&samantha_web=1")
# 移动端 UA
MUA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
       "Version/17.5 Mobile/15E148 Safari/604.1")

HOSTS = ["https://www.doubao.com", "https://api.doubao.com", "https://aweme.snssdk.com"]

# 候选 feed/list 路径
PATHS = [
    "/creativity/feed", "/creativity/list", "/creativity/recommend",
    "/creativity/creation/list", "/creativity/share/list", "/creativity/square",
    "/creativity/discover", "/creativity/explore", "/creativity/interest",
    "/api/creativity/feed", "/samantha/creativity/feed",
    "/creativity/home_feed", "/creativity/feed_list", "/creativity/video/feed",
    "/creativity/creation/feed", "/creation/feed", "/video_square/feed",
]

CTX = ssl._create_unverified_context()


def probe(url, method="GET", body=None):
    h = {"User-Agent": MUA, "Referer": "https://www.doubao.com/",
         "Accept": "application/json, text/plain, */*"}
    if body:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=12, context=CTX)
        return r.status, r.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)[:120]


def main():
    found = []
    for host in HOSTS:
        for p in PATHS:
            url = host + p + "?" + Q
            code, txt = probe(url)
            flag = "" if code == 404 else "  <<< 非404!"
            if code != 404:
                found.append((url, code, txt))
            print(f"[{code}] {host}{p}{flag}")
    print("\n===== 非 404 汇总（可能存在的接口） =====")
    if not found:
        print("全部 404 —— 这些候选路径都不存在")
    for url, code, txt in found:
        print(f"[{code}] {url}\n     -> {txt[:160]}")


if __name__ == "__main__":
    main()