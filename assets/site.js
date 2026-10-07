/* ============================================================
   创作广场 · 视频   交互逻辑（实时直连版）
   页面加载时：/api/works 取链接列表 → 逐条 /api/resolve 实时拉豆包
   视频 / 封面都经 /api/stream 同域代理，绕开 CDN 防盗链与 CORS
   ============================================================ */
(function () {
  "use strict";

  var ICON = {
    play: '<svg viewBox="0 0 24 24" width="13" height="13" fill="#fff"><path d="M8 5.2v13.6a1 1 0 0 0 1.53.85l10.5-6.8a1 1 0 0 0 0-1.7L9.53 4.35A1 1 0 0 0 8 5.2z"/></svg>',
    back: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
    copy: '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2.4"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>',
    open: '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"/><path d="M20 4l-8.5 8.5"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/></svg>',
    add: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-.6 3"/><path d="M20 5v6h-6"/></svg>'
  };

  var TAB_NAME = { discover: "发现", video: "视频", ecom: "带货模板", pimg: "P图", pet: "萌宠" };
  var state = { items: [], tab: "video", loading: false };

  var app, grid, panel, panelTitle, panelSub, detail, toastEl, updatedEl, skeleton, addBtn, refreshBtn;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* 作者名 -> 稳定的头像底色（后端没给就前端算） */
  function accentOf(name) {
    name = name || "豆包用户";
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    var hue = h % 360;
    return "hsl(" + hue + ",62%,55%)";
  }

  /* 把豆包直链包成同域代理地址，破解防盗链 / CORS */
  function streamUrl(u) {
    return u ? "/api/stream?url=" + encodeURIComponent(u) : "";
  }

  var toastTimer;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    requestAnimationFrame(function () { toastEl.classList.add("is-show"); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.classList.remove("is-show");
      setTimeout(function () { toastEl.hidden = true; }, 240);
    }, 1900);
  }

  function copyText(text) {
    if (!text) { toast("该作品没有可复制的提示词"); return; }
    function ok() { toast("提示词已复制 ✓"); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(ok, fallback);
    } else { fallback(); }
    function fallback() {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.cssText = "position:fixed;left:-9999px;top:0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        ok();
      } catch (e) { toast("复制失败，请长按选中提示词"); }
    }
  }

  function makeCard(it) {
    var card = document.createElement("button");
    card.type = "button";
    card.className = "card";

    var thumb = document.createElement("div");
    thumb.className = "thumb";
    thumb.style.setProperty("--ar", (it.width || 720) + " / " + (it.height || 1280));

    var img = document.createElement("img");
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = it.author || "";
    var p = streamUrl(it.poster);
    img.src = p;
    img.onerror = function () { img.style.visibility = "hidden"; };
    thumb.appendChild(img);

    thumb.insertAdjacentHTML("beforeend", '<span class="badge">' + ICON.play + "</span>");
    if (it.duration) {
      thumb.insertAdjacentHTML("beforeend", '<span class="badge badge--dur">' + esc(it.duration) + "</span>");
    }
    if (it.__failed) {
      var tag = document.createElement("span");
      tag.className = "badge badge--dur";
      tag.style.right = "7px"; tag.style.background = "rgba(180,40,40,.6)";
      tag.textContent = "已失效";
      thumb.appendChild(tag);
    }

    var meta = document.createElement("div");
    meta.className = "meta";
    var av = document.createElement("span");
    av.className = "avatar";
    av.textContent = (it.author || "?").trim().slice(0, 1);
    av.style.background = it.accent || accentOf(it.author);
    var nm = document.createElement("span");
    nm.className = "name";
    nm.textContent = it.author || "豆包用户";
    meta.appendChild(av);
    meta.appendChild(nm);
    var rightTag = it.model || it.definition || "";
    if (rightTag) {
      var tg = document.createElement("span");
      tg.className = "tag";
      tg.textContent = rightTag;
      meta.appendChild(tg);
    }

    card.appendChild(thumb);
    card.appendChild(meta);
    if (!it.__failed) card.addEventListener("click", function () { openDetail(it); });
    return card;
  }

  function renderGrid() {
    grid.innerHTML = "";
    if (!state.items.length) {
      grid.hidden = true;
      panel.hidden = false;
      panelTitle.textContent = "还没有收录作品";
      panelSub.innerHTML = "点右上角 <b>＋</b> 粘贴豆包 App 里的分享链接（分享 → 复制链接），作品就会实时上墙，视频和提示词都是当场从豆包拉取的。";
      var b = document.getElementById("panelBack");
      b.textContent = "刷新看看";
      b.onclick = function () { refresh(); };
      return;
    }
    var colA = document.createElement("div"); colA.className = "col";
    var colB = document.createElement("div"); colB.className = "col";
    grid.appendChild(colA); grid.appendChild(colB);
    var hA = 0, hB = 0;
    state.items.forEach(function (it, i) {
      var card = makeCard(it);
      card.style.animationDelay = Math.min(i * 45, 420) + "ms";
      var ratio = (it.height && it.width) ? it.height / it.width : 16 / 9;
      var h = ratio + 0.24;
      if (hA <= hB) { colA.appendChild(card); hA += h; }
      else { colB.appendChild(card); hB += h; }
    });
  }

  function setTab(t) {
    state.tab = t;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (x) {
      x.classList.toggle("is-active", x.dataset.tab === t);
    });
    if (t === "video") {
      grid.hidden = false;
      panel.hidden = true;
    } else {
      grid.hidden = true;
      panel.hidden = false;
      panelTitle.textContent = "「" + (TAB_NAME[t] || t) + "」频道";
      panelSub.textContent = "网页版只抓取到豆包「视频」广场的真实作品，其他频道还在豆包 App 里。";
      var b = document.getElementById("panelBack");
      b.textContent = "回到「视频」";
      b.onclick = function () { setTab("video"); };
    }
  }

  function openDetail(it) {
    var poster = streamUrl(it.poster);
    var src = streamUrl(it.video) || poster;
    detail.innerHTML =
      '<div class="detail-head">' +
        '<button class="detail-back" type="button" aria-label="返回">' + ICON.back + "</button>" +
        '<div style="min-width:0">' +
          '<div class="detail-htitle">作品详情</div>' +
          '<div class="detail-hsub">' + esc(it.model || "豆包 AI 视频") + (it.definition ? " · " + esc(it.definition) : "") + "</div>" +
        "</div>" +
      "</div>" +
      '<div class="detail-scroll">' +
        '<div class="stage"><video controls playsinline loop preload="metadata"' + (poster ? ' poster="' + esc(poster) + '"' : "") + "></video></div>" +
        '<div class="detail-body">' +
          '<div class="d-author">' +
            '<div class="d-avatar" style="background:' + (it.accent || accentOf(it.author)) + '">' + esc((it.author || "?").slice(0, 1)) + "</div>" +
            "<div><div class=\"d-name\">" + esc(it.author || "豆包用户") + '</div>' +
            '<div class="d-meta">@豆包创作广场' + (it.duration ? " · 时长 " + esc(it.duration) : "") + "</div></div>" +
          "</div>" +
          '<div class="d-label">提示词 Prompt</div>' +
          '<div class="prompt-box' + (it.prompt ? "" : " is-empty") + '">' + (it.prompt ? esc(it.prompt) : "该作品未公开提示词") + "</div>" +
          '<div class="d-actions">' +
            '<button class="btn btn--primary" type="button" data-act="copy">' + ICON.copy + "复制提示词</button>" +
            '<button class="btn" type="button" data-act="open">' + ICON.open + "原片</button>" +
          "</div>" +
          '<div class="d-usage">内容来自豆包 App 公开分享 · 实时拉取 · 仅供浏览参考</div>' +
        "</div>" +
      "</div>";

    detail.hidden = false;
    var v = detail.querySelector("video");
    v.src = src;
    var p = v.play();
    if (p && p.catch) p.catch(function () {});

    detail.querySelector(".detail-back").addEventListener("click", closeDetail);
    detail.querySelector('[data-act="copy"]').addEventListener("click", function () { copyText(it.prompt); });
    detail.querySelector('[data-act="open"]').addEventListener("click", function () {
      window.open(it.source_url, "_blank", "noopener");
    });

    try { history.pushState({ d: 1 }, ""); } catch (e) {}
  }

  function closeDetail() {
    var v = detail.querySelector("video");
    if (v) { try { v.pause(); v.removeAttribute("src"); v.load(); } catch (e) {} }
    detail.hidden = true;
    detail.innerHTML = "";
    if (history.state && history.state.d) {
      try { history.back(); } catch (e) {}
    }
  }

  /* ---------- 实时取数 ---------- */
  function fetchWorks() {
    return fetch("/api/works?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("works " + r.status);
        return r.json();
      })
      .then(function (j) { return (j && j.items) || []; });
  }

  function resolveOne(w) {
    var u = "/api/resolve?share_id=" + encodeURIComponent(w.share_id) +
            "&vid=" + encodeURIComponent(w.vid) + "&t=" + Date.now();
    return fetch(u, { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) { d.accent = accentOf(d.author); return d; }
        return { __failed: true, share_id: w.share_id, vid: w.vid, author: "已失效", prompt: "" };
      })
      .catch(function () {
        return { __failed: true, share_id: w.share_id, vid: w.vid, author: "已失效", prompt: "" };
      });
  }

  function refresh() {
    if (state.loading) return;
    state.loading = true;
    if (skeleton) skeleton.hidden = false;
    fetchWorks()
      .then(function (list) {
        return Promise.all(list.map(resolveOne));
      })
      .then(function (items) {
        state.items = items;
        renderGrid();
        updateMeta(items);
        if (skeleton) skeleton.remove();
        state.loading = false;
        var m = /[?&]open=(\d+)/.exec(location.search);
        if (m && state.items[+m[1]] && !state.items[+m[1]].__failed) openDetail(state.items[+m[1]]);
      })
      .catch(function () {
        // 静态托管（如 GitHub Pages）没有 /api/works：退回读 videos.json
        return fetch("videos.json?t=" + Date.now(), { cache: "no-store" })
          .then(function (r) { return r.json(); })
          .then(function (j) {
            var items = (j && j.items) || [];
            items.forEach(function (it) { it.accent = it.accent || accentOf(it.author); });
            state.items = items;
            renderGrid();
            updateMeta(items, j && j.updated);
            if (skeleton) skeleton.remove();
            state.loading = false;
          })
          .catch(function () {
            state.items = [];
            renderGrid();
            if (skeleton) skeleton.remove();
            state.loading = false;
          });
      });
  }

  function updateMeta(items, updated) {
    if (!updatedEl) return;
    var ok = items.filter(function (x) { return !x.__failed; }).length;
    var fail = items.length - ok;
    var s = "实时 · 共 " + ok + " 个作品 · 内容来自豆包公开分享";
    if (fail) s += "（" + fail + " 个失效）";
    if (updated) s += " · 更新于 " + updated;
    updatedEl.textContent = s;
    document.title = ok ? "创作广场 · 视频（" + ok + "）" : "创作广场 · 视频";
  }

  /* ---------- 新增作品（粘贴豆包分享链接即时上墙） ---------- */
  function addWork() {
    var link = window.prompt("粘贴豆包 App 里的分享链接\n（在作品上点「分享 → 复制链接」）");
    if (!link) return;
    link = link.trim();
    if (!link) return;
    toast("正在添加...");
    fetch("/api/works", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: link }),
      cache: "no-store"
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) {
          toast(d.added ? "已上墙 ✓ 正在刷新" : "这条已经在广场里了");
          refresh();
        } else {
          toast((d && d.error) ? ("添加失败：" + d.error) : "添加失败，链接格式不对");
        }
      })
      .catch(function () { toast("添加失败，请确认服务在运行"); });
  }

  function init() {
    app = document.getElementById("app");
    grid = document.getElementById("grid");
    panel = document.getElementById("panel");
    panelTitle = document.getElementById("panelTitle");
    panelSub = document.getElementById("panelSub");
    detail = document.getElementById("detail");
    toastEl = document.getElementById("toast");
    updatedEl = document.getElementById("updated");
    skeleton = document.getElementById("skeleton");
    addBtn = document.getElementById("addBtn");
    refreshBtn = document.getElementById("refreshBtn");

    app.appendChild(detail);

    document.getElementById("tabs").addEventListener("click", function (e) {
      var b = e.target.closest(".tab"); if (!b) return; setTab(b.dataset.tab);
    });
    document.getElementById("panelBack").addEventListener("click", function () { setTab("video"); });
    if (addBtn) addBtn.addEventListener("click", addWork);
    if (refreshBtn) refreshBtn.addEventListener("click", refresh);
    if (updatedEl) {
      updatedEl.style.cursor = "pointer";
      updatedEl.title = "点击刷新";
      updatedEl.addEventListener("click", refresh);
    }

    document.getElementById("composerInput").addEventListener("focus", function () {
      this.blur(); toast("网页版仅供浏览广场作品，创作请到豆包 App");
    });
    document.getElementById("composer").addEventListener("click", function (e) {
      if (e.target.closest(".round-btn")) toast("创作功能请在豆包 App 内使用");
    });
    document.getElementById("searchBtn").addEventListener("click", function () {
      toast("搜索请在豆包 App 内使用");
    });
    document.getElementById("chips").addEventListener("click", function (e) {
      var c = e.target.closest(".chip"); if (!c) return;
      toast("「" + c.dataset.tip + "」请在豆包 App 内使用");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !detail.hidden) closeDetail();
    });
    window.addEventListener("popstate", function () {
      if (!detail.hidden) { detail.hidden = true; detail.innerHTML = ""; }
    });

    setTab("video");
    refresh();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
