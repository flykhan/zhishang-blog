/* 「纸上」公共界面交互脚本 — 原生 JS，无依赖。 */
"use strict";

(function () {
  const root = document.documentElement;
  const THEME_KEY = "theme";
  const mediaQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  /* ---------- 主题 ---------- */

  function readStoredTheme() {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (error) {
      return null;
    }
  }

  function systemTheme() {
    return mediaQuery && mediaQuery.matches ? "dark" : "light";
  }

  function persistTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (error) {
      /* 隐私模式等场景下无法持久化，忽略即可。 */
    }
  }

  function updateThemeColor(theme) {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", theme === "dark" ? "#141412" : "#faf8f4");
    }
  }

  function applyTheme(theme, options) {
    const settings = options || {};
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
    if (settings.persist) {
      persistTheme(theme);
    }
    updateThemeColor(theme);

    const button = document.getElementById("theme-toggle");
    if (button) {
      const label = theme === "dark" ? "切换到浅色模式" : "切换到深色模式";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }
  }

  applyTheme(readStoredTheme() || systemTheme(), { persist: false });

  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      const nextTheme = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(nextTheme, { persist: true });
    });
  }

  if (mediaQuery) {
    const onSystemThemeChange = function (event) {
      /* 用户手动选择过主题时，不再跟随系统。 */
      if (!readStoredTheme()) {
        applyTheme(event.matches ? "dark" : "light", { persist: false });
      }
    };
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", onSystemThemeChange);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(onSystemThemeChange);
    }
  }

  /* ---------- 吸顶页头 ---------- */

  const siteHeader = document.querySelector(".site-header");
  if (siteHeader) {
    const STUCK_OFFSET = 120;
    const raf =
      typeof window.requestAnimationFrame === "function"
        ? window.requestAnimationFrame.bind(window)
        : function (callback) {
            return window.setTimeout(callback, 16);
          };
    let stuck = null;
    let scheduled = false;

    const syncHeader = function () {
      scheduled = false;
      const nextStuck = (window.scrollY || window.pageYOffset || 0) > STUCK_OFFSET;
      if (nextStuck !== stuck) {
        stuck = nextStuck;
        siteHeader.classList.toggle("is-stuck", stuck);
      }
    };

    const requestHeaderSync = function () {
      if (scheduled) {
        return;
      }
      scheduled = true;
      raf(syncHeader);
    };

    syncHeader();
    window.addEventListener("scroll", requestHeaderSync, { passive: true });
    window.addEventListener("resize", requestHeaderSync);
  }

  /* ---------- 返回顶部 ---------- */

  const toTop = document.getElementById("to-top");
  if (toTop) {
    let lastVisible = null;

    const updateToTop = function () {
      const visible = (window.scrollY || window.pageYOffset || 0) > 640;
      if (visible !== lastVisible) {
        lastVisible = visible;
        toTop.classList.toggle("is-visible", visible);
        toTop.setAttribute("aria-hidden", visible ? "false" : "true");
      }
    };

    updateToTop();
    window.addEventListener("scroll", updateToTop, { passive: true });
    window.addEventListener("resize", updateToTop);

    toTop.addEventListener("click", function () {
      const reduceMotion =
        window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    });
  }

  /* ---------- 阅读进度（仅文章页） ---------- */

  const progress = document.getElementById("reading-progress");
  if (progress) {
    const updateProgress = function () {
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      const ratio = max > 0 ? Math.min(1, Math.max(0, (window.scrollY || 0) / max)) : 0;
      progress.style.transform = "scaleX(" + ratio + ")";
    };

    updateProgress();
    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
  }

  /* ---------- 评论锚点：定位后给目标轻微提示 ---------- */

  const commentsSection = document.getElementById("comments");
  if (commentsSection && window.location.hash === "#comments") {
    commentsSection.classList.add("is-targeted");
  }
})();
