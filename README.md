# 创作广场 · 视频（网页版 · 自带账号 · 实时广场）

复刻**豆包手机端「视频创作广场」**：浏览器打开即刷别人的 AI 视频，
每条都带**提示词（prompt）**和**生成效果**，**打开就是最新内容，不用先分享**。

## 两种用法

### A. 登录自己的豆包账号（推荐 · 实时满屏）
点右上角 **👤 登录图标**，用你自己的豆包账号登录后，网页会**实时读取**
`/api/creativity/feed`（豆包 App 用的真信息流），满屏作品持续更新，无需手动添加。

**怎么登录**：豆包是**手机号+验证码**登录，没有网页密码表单。做法是
在自己浏览器登录 `doubao.com` 后，把 Cookie 提供给网页：
1. 先在 <https://www.doubao.com/> 登录你的账号；
2. 回到本网页，点登录图标 → 展开「手动粘贴 Cookie」；
3. 在浏览器按 `F12` → Console，输入 `copy(document.cookie)` 回车；
4. 把复制的整串粘进去 → 点「用这段 Cookie 登录」。

登录后 12 小时内有效（服务端只存在内存、不落盘明文；重启服务即失效）。
每个访问者用自己的 cookie 只为自己拉 feed，互不混用。

### B. 免登录看种子作品
不登录也能打开，会显示 `works.json` 里的种子作品（每条仍实时从豆包拉取）。
想加作品：点 **＋** 粘贴豆包分享链接，即时上墙。

## 一键部署（点按钮就上线，手机浏览器直接开）

- **[!Deploy to Render](https://render.com/deploy?repo=https://github.com/qianqianlaifeng/chuangzuo-square)** —— 用 Render 账号点一下，自动部署，给你一个 `https://xxx.onrender.com` 手机能开的网址。
- **HuggingFace Spaces**：新建 Space → 选 **Docker** → 仓库填 `qianqianlaifeng/chuangzuo-square`，本仓库已带 `Dockerfile`。

> 这两个平台都是**免费**的，且都支持运行 Python（会注入 `PORT` 环境变量，`server.py` 已适配）。
> 部署完就是一个公网链接，手机浏览器直接打开即是实时广场。

## 广场里有哪些视频？（实测结论）

豆包**网页端没有公开的"创作广场信息流"接口**：

- `www.doubao.com/api/creativity/feed`（App 用的真 feed）→ **游客访问 401，强制登录 Cookie**。
  所以想自动拉满广场，需要**用户登录自己的账号**（见上面 A）。
- 全站只有 `get_video_share_info` 这一个**单条分享**接口能免鉴权取到视频+作者+提示词，
  但必须 `share_id + video_id` 成对，**无法枚举**——所以免登录时只能显示手动收录的作品。

免登录时内容由 `works.json` 维护（自带一条真实种子）。新增作品：

- **网页里加**：点右上角 **＋**，粘贴豆包 App 里作品的分享链接（作品上点「分享 → 复制链接」），
  即时上墙，视频和提示词当场从豆包拉取。
- **直接改文件**：编辑根目录 `works.json`，加一项 `{"share_id":"...","vid":"..."}`，重启服务即生效。

## 它怎么做到「实时」

豆包网页端没有公开的创作广场信息流接口，只有「单条分享」接口
`get_video_share_info`（需要 `share_id + video_id` 成对）。本项目的做法是：

- `server.py` 在**同域**提供代理，前端加载时实时调用豆包接口拉取视频 / 作者 / 提示词，
  视频和封面再经 `/api/stream` 同域代理转发，**绕开 CDN 防盗链和 CORS**。
- 广场里有哪些作品，由服务端 `works.json` 维护（自带一条真实种子）。
  查看者**不需要自己分享**，打开网页就直接看到实时内容；你往 `works.json` 里加链接，
  所有人下次刷新就看到新作品。

```
浏览器  ──►  server.py（同域） ──►  豆包 get_video_share_info  （实时）
              └─ /api/stream 代理视频/封面，破解防盗链
```

## 本地运行（双击即用）

1. 双击根目录的 **`启动实时服务.bat`**
2. 自动打开浏览器 `http://127.0.0.1:8788/`
3. **手机看**：把 `127.0.0.1` 换成这台电脑的局域网 IP、端口 `8788`
   （电脑和手机连同一个 WiFi 即可）。
4. 停止：关掉弹出的服务窗口即可。

> 需要 Python 3（脚本会自动找 WorkBuddy 自带的 Python；没有就提示你装一个）。

## 加作品（不用改代码）

- **网页里加**：点右上角 **＋**，粘贴豆包 App 里作品的分享链接
  （作品上点「分享 → 复制链接」），即时上墙，视频和提示词当场从豆包拉取。
- **直接改文件**：编辑根目录 `works.json`，加一项 `{"share_id":"...","vid":"..."}`，
  重启服务即生效。

## 部署说明（重要）

- **GitHub Pages 是纯静态托管，跑不了 `server.py` 的代理**。如果直接把本目录推到 Pages，
  前端会自动回退读 `videos.json`（只有种子视频，非实时）。
- 想要「实时直连」效果，需要把 `server.py` 跑在一个**能运行 Python 的地方**：
  - 自己电脑（上面的 .bat 方式，局域网友好）；
  - 或支持 Python 的托管，如 **HuggingFace Spaces / Render / PythonAnywhere** 等
    （监听环境变量 `PORT` 即可，`server.py` 已支持）。

## 目录

```
server.py            实时直连服务（静态网页 + 豆包接口代理 + 视频流代理）
index.html           页面结构（标签栏 / 两列瀑布流 / 详情 / 底部创作入口）
assets/site.css      样式（浅色主题 · 手机优先 · 桌面居中成手机框）
assets/site.js       交互（实时拉取 / 瀑布流 / 详情 / 复制提示词 / ＋添加）
works.json           广场作品链接列表（服务端维护）
videos.json          静态兜底数据（仅种子视频，供纯静态托管回退）
启动实时服务.bat     双击即用启动器（GBK + CRLF，cmd 不乱码）
make_launcher.py     生成上面的 .bat
_old/               历史方案与探测产物（已弃用）
```

## 技术

零依赖，仅用 Python 标准库 `http.server` + `urllib`。`server.py` 同时承担：
静态文件服务、`/api/works`（作品列表）、`POST /api/works`（新增链接）、
`/api/resolve`（实时调豆包 share 接口）、`/api/feed`（用登录 Cookie 实时拉广场）、
`POST /api/login`（存 Cookie 发会话 token）、`/api/logout`、
`/api/stream`（代理视频/封面，支持 Range 拖动）。

> 兼容性：`server.py` 把 TLS 锁在 1.2 并把 cipher security level 降到 1，
> 否则部分容器/代理环境会以默认 SECLEVEL=2 直接 RST 连接
> （表现为 `UNEXPECTED_EOF_WHILE_READING`）。
