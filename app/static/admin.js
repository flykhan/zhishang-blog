/* ============================================================
   纸上 · 管理后台脚本（原生 JS，无依赖）
   功能：主题切换、移动端导航折叠、删除二次确认、
         Markdown 实时预览、字数统计、Ctrl/⌘+S 保存
   说明：主题防闪烁内联脚本已在各页面 <head> 中先行执行，
         这里只负责按钮状态与后续切换。
   ============================================================ */
(function () {
  "use strict";

  const THEME_KEY = "theme";
  const root = document.documentElement;
  const EMPTY_PREVIEW = '<p class="editor-preview__empty">开始输入 Markdown，这里会实时渲染预览。</p>';

  /* ---------- 主题切换 ---------- */
  const readStoredTheme = () => {
    try {
      const value = window.localStorage.getItem(THEME_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (err) {
      return null;
    }
  };

  const syncThemeButtons = (theme) => {
    const label = theme === "dark" ? "切换到浅色模式" : "切换到深色模式";
    document.querySelectorAll(".js-theme-toggle").forEach((button) => {
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    });
  };

  const applyTheme = (theme, persist) => {
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
    if (persist) {
      try {
        window.localStorage.setItem(THEME_KEY, theme);
      } catch (err) {
        /* 隐私模式下写入失败，忽略即可 */
      }
    }
    syncThemeButtons(theme);
  };

  document.querySelectorAll(".js-theme-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(current === "dark" ? "light" : "dark", true);
    });
  });

  syncThemeButtons(root.getAttribute("data-theme") === "dark" ? "dark" : "light");

  const systemTheme = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
  if (systemTheme) {
    const onSystemThemeChange = (event) => {
      // 用户手动选择过主题时，不再跟随系统
      if (readStoredTheme()) return;
      applyTheme(event.matches ? "dark" : "light", false);
    };
    if (typeof systemTheme.addEventListener === "function") {
      systemTheme.addEventListener("change", onSystemThemeChange);
    } else if (typeof systemTheme.addListener === "function") {
      systemTheme.addListener(onSystemThemeChange);
    }
  }

  /* ---------- 移动端导航折叠 ---------- */
  const navToggle = document.getElementById("admin-nav-toggle");
  const nav = document.getElementById("admin-nav");
  const mobileQuery = window.matchMedia
    ? window.matchMedia("(max-width: 960px)")
    : null;

  const setNavOpen = (open) => {
    if (!nav || !navToggle) return;
    nav.classList.toggle("is-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    navToggle.setAttribute("aria-label", open ? "收起导航" : "展开导航");
    document.body.classList.toggle("admin-nav-open", open);
  };

  if (nav && navToggle) {
    navToggle.addEventListener("click", () => {
      setNavOpen(!nav.classList.contains("is-open"));
    });

    // 点击导航项后收起面板
    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setNavOpen(false));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setNavOpen(false);
    });

    document.addEventListener("click", (event) => {
      if (!nav.classList.contains("is-open")) return;
      if (nav.contains(event.target) || navToggle.contains(event.target)) return;
      setNavOpen(false);
    });

    if (mobileQuery) {
      const onViewportChange = (event) => {
        if (!event.matches) setNavOpen(false);
      };
      if (typeof mobileQuery.addEventListener === "function") {
        mobileQuery.addEventListener("change", onViewportChange);
      } else if (typeof mobileQuery.addListener === "function") {
        mobileQuery.addListener(onViewportChange);
      }
    }
  }

  /* ---------- 删除等危险操作二次确认（data-confirm） ---------- */
  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!form || typeof form.getAttribute !== "function") return;

      const submitter = event.submitter || document.activeElement;
      let message = "";
      if (submitter && typeof submitter.getAttribute === "function") {
        message = submitter.getAttribute("data-confirm") || "";
      }
      if (!message) message = form.getAttribute("data-confirm") || "";
      if (!message) return;

      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true
  );

  /* ---------- 编辑器：实时预览 / 字数统计 / Ctrl+S ---------- */
  const textarea = document.getElementById("content-md");
  const preview = document.getElementById("preview");
  const previewError = document.getElementById("preview-error");
  const previewState = document.getElementById("preview-state");
  const wordCounters = document.querySelectorAll("[data-word-count]");

  const showPreviewError = (message) => {
    if (previewError) {
      previewError.textContent = message;
      previewError.hidden = false;
    }
    if (previewState) previewState.textContent = "预览失败";
  };

  const hidePreviewError = () => {
    if (previewError) {
      previewError.hidden = true;
      previewError.textContent = "";
    }
    if (previewState) previewState.textContent = "实时更新";
  };

  const updateWordCount = () => {
    if (!textarea || wordCounters.length === 0) return;
    const text = textarea.value || "";
    const chars = text.replace(/\s+/g, "").length;
    const minutes = chars === 0 ? 0 : Math.max(1, Math.ceil(chars / 300));
    const label =
      chars === 0
        ? "0 字"
        : chars.toLocaleString("zh-CN") + " 字 · 约 " + minutes + " 分钟";
    wordCounters.forEach((element) => {
      element.textContent = label;
    });
  };

  let previewTimer = null;
  let inflight = null;
  let latestRequest = 0;

  const requestPreview = (content) => {
    if (!preview) return;

    const requestId = latestRequest + 1;
    latestRequest = requestId;

    if (inflight && typeof inflight.abort === "function") {
      inflight.abort();
    }

    let controller = null;
    if (typeof window.AbortController === "function") {
      controller = new window.AbortController();
      inflight = controller;
    }

    const body = new FormData();
    body.append("content_md", content);

    const options = {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    };
    if (controller) options.signal = controller.signal;

    if (previewState) previewState.textContent = "正在更新…";

    window
      .fetch("/admin/preview", options)
      .then((response) => {
        if (!response.ok) throw new Error("服务器返回 " + response.status);
        return response.json();
      })
      .then((data) => {
        if (requestId !== latestRequest) return;
        if (!data || typeof data.html !== "string") {
          throw new Error("响应格式不正确");
        }
        preview.innerHTML = data.html || EMPTY_PREVIEW;
        hidePreviewError();
      })
      .catch((err) => {
        if (requestId !== latestRequest) return;
        if (err && err.name === "AbortError") return;
        const detail = err && err.message ? "（" + err.message + "）" : "";
        showPreviewError("预览更新失败，请检查网络后重试。" + detail);
      })
      .then(() => {
        if (controller && inflight === controller) inflight = null;
      });
  };

  const refreshEditor = () => {
    updateWordCount();
    if (!textarea || !preview) return;

    if (previewTimer) window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(() => {
      const content = textarea.value || "";
      if (!content.trim()) {
        preview.innerHTML = EMPTY_PREVIEW;
        hidePreviewError();
        return;
      }
      requestPreview(content);
    }, 300);
  };

  if (textarea && preview) {
    textarea.addEventListener("input", refreshEditor);
    updateWordCount();
    const initial = textarea.value || "";
    if (initial.trim()) requestPreview(initial);
  }

  // Ctrl/⌘ + S 保存文章
  document.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey)) return;
    if (event.key !== "s" && event.key !== "S") return;
    const form = document.getElementById("post-form");
    if (!form) return;
    event.preventDefault();
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });

  // 防止重复提交（表单校验不通过时不会触发 submit 事件）
  const postForm = document.getElementById("post-form");
  if (postForm) {
    postForm.addEventListener("submit", () => {
      const saveButton = document.getElementById("editor-save");
      if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = "保存中…";
      }
    });
    window.addEventListener("pageshow", () => {
      const saveButton = document.getElementById("editor-save");
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.textContent = "保存文章";
      }
    });
  }
})();
