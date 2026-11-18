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

  /* ---------- 通用小工具 ---------- */

  const requestFrame =
    typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame.bind(window)
      : function (callback) {
          return window.setTimeout(callback, 16);
        };

  function prefersReducedMotion() {
    return Boolean(
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      try {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.setAttribute("aria-hidden", "true");
        area.style.position = "fixed";
        area.style.top = "-9999px";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        area.setSelectionRange(0, area.value.length);
        const ok = document.execCommand("copy");
        document.body.removeChild(area);
        if (ok) {
          resolve();
        } else {
          reject(new Error("copy failed"));
        }
      } catch (error) {
        reject(error);
      }
    });
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  /* ---------- 文章目录（TOC） ---------- */

  const tocList = document.getElementById("toc-list");
  const postAside = document.getElementById("post-aside");
  const postLayout = document.querySelector(".post-layout");

  if (tocList && postAside && postLayout) {
    const tocHeadings = Array.prototype.slice
      .call(document.querySelectorAll(".prose h2[id], .prose h3[id]"))
      .filter(function (heading) {
        return Boolean(heading.id);
      });

    if (tocHeadings.length < 2) {
      /* 标题太少时目录没有意义，直接隐藏整块并保留原布局。 */
      postAside.hidden = true;
      postAside.setAttribute("aria-hidden", "true");
    } else {
      const tocItems = [];
      const tocNav = document.getElementById("post-toc") || postAside;

      const tocClose = document.createElement("button");
      tocClose.type = "button";
      tocClose.className = "toc-close";
      tocClose.setAttribute("aria-label", "关闭目录");
      tocClose.textContent = "×";
      tocNav.insertBefore(tocClose, tocNav.firstChild);

      const tocToggle = document.createElement("button");
      tocToggle.type = "button";
      tocToggle.className = "toc-toggle";
      tocToggle.textContent = "目录";
      tocToggle.setAttribute("aria-expanded", "false");
      tocToggle.setAttribute("aria-controls", "post-aside");
      const postHeader = postLayout.querySelector(".post-header");
      if (postHeader) {
        /* 放在文章信息之后，阅读位置更自然；滚动时仍由 sticky 固定在页头下方。 */
        postHeader.insertAdjacentElement("afterend", tocToggle);
      } else {
        postLayout.insertBefore(tocToggle, postLayout.firstChild);
      }

      const tocBackdrop = document.createElement("div");
      tocBackdrop.className = "toc-backdrop";
      tocBackdrop.setAttribute("aria-hidden", "true");
      document.body.appendChild(tocBackdrop);

      let lastTocFocus = null;
      let cancelActiveScroll = null;

      const isTocOpen = function () {
        return document.body.classList.contains("is-toc-open");
      };

      const closeTocDrawer = function (returnFocus) {
        if (!isTocOpen()) {
          return;
        }
        document.body.classList.remove("is-toc-open");
        tocToggle.setAttribute("aria-expanded", "false");
        if (returnFocus) {
          const target =
            lastTocFocus && document.contains(lastTocFocus) ? lastTocFocus : tocToggle;
          target.focus({ preventScroll: true });
        }
      };

      const openTocDrawer = function () {
        if (isTocOpen()) {
          return;
        }
        lastTocFocus = document.activeElement;
        document.body.classList.add("is-toc-open");
        tocToggle.setAttribute("aria-expanded", "true");
        /* 抽屉先由 hidden 变为可见，等一帧后再移入焦点。 */
        requestFrame(function () {
          if (!isTocOpen()) {
            return;
          }
          const firstTarget = tocItems.length ? tocItems[0].link : tocClose;
          firstTarget.focus({ preventScroll: true });
        });
      };

      /* 自定义平滑滚动：吸顶头会在滚动过程中收缩，逐帧重算目标可避免偏移。 */
      const scrollToHeading = function (heading) {
        const focusHeading = function () {
          const previousTabindex = heading.getAttribute("tabindex");
          heading.setAttribute("tabindex", "-1");
          heading.focus({ preventScroll: true });
          if (previousTabindex === null) {
            heading.addEventListener(
              "blur",
              function () {
                heading.removeAttribute("tabindex");
              },
              { once: true }
            );
          }
        };

        const resolveDesiredTop = function () {
          const header = document.querySelector(".site-header");
          const headerBottom = header ? header.getBoundingClientRect().bottom : 24;
          return Math.max(96, Math.min(headerBottom + 24, 160));
        };

        /* 显式 instant，避免被全局 scroll-behavior:smooth 拖慢逐帧动画。 */
        const scrollInstant = function (top) {
          try {
            window.scrollTo({ top: top, behavior: "instant" });
          } catch (error) {
            window.scrollTo(0, top);
          }
        };

        const targetDocTop = function () {
          return (
            heading.getBoundingClientRect().top +
            (window.scrollY || 0) -
            resolveDesiredTop()
          );
        };

        /* 新的目录跳转会接管上一次尚未结束的滚动动画。 */
        if (cancelActiveScroll) {
          cancelActiveScroll();
          cancelActiveScroll = null;
        }

        if (prefersReducedMotion()) {
          /* 吸顶头在滚动后立即收缩，下一帧再对齐一次即可避免偏差。 */
          scrollInstant(targetDocTop());
          requestFrame(function () {
            scrollInstant(targetDocTop());
            focusHeading();
          });
          return;
        }

        const startY = window.scrollY || window.pageYOffset || 0;
        let startTime = null;
        let duration = 500;
        let finished = false;

        const finish = function () {
          if (finished) {
            return;
          }
          finished = true;
          window.removeEventListener("wheel", cancelScroll);
          window.removeEventListener("touchstart", cancelScroll);
          if (cancelActiveScroll === cancelScroll) {
            cancelActiveScroll = null;
          }
          focusHeading();
        };

        const cancelScroll = function () {
          if (finished) {
            return;
          }
          finished = true;
          window.removeEventListener("wheel", cancelScroll);
          window.removeEventListener("touchstart", cancelScroll);
          if (cancelActiveScroll === cancelScroll) {
            cancelActiveScroll = null;
          }
        };

        window.addEventListener("wheel", cancelScroll, { passive: true });
        window.addEventListener("touchstart", cancelScroll, { passive: true });
        cancelActiveScroll = cancelScroll;

        const step = function (now) {
          if (finished) {
            return;
          }
          if (startTime === null) {
            startTime = now;
            duration = Math.min(
              700,
              Math.max(300, Math.abs(targetDocTop() - startY) * 0.25)
            );
          }
          const elapsed = now - startTime;
          const t = Math.min(1, elapsed / duration);
          const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
          scrollInstant(Math.round(startY + (targetDocTop() - startY) * eased));
          if (t < 1) {
            requestFrame(step);
            return;
          }
          /* 收尾再对齐一次，消除吸顶头收缩带来的几十像素误差。 */
          scrollInstant(targetDocTop());
          finish();
        };
        requestFrame(step);
      };

      tocHeadings.forEach(function (heading) {
        const item = document.createElement("li");
        item.className =
          "toc-item" + (heading.tagName === "H3" ? " toc-item--h3" : "");

        const link = document.createElement("a");
        link.className = "toc-link";
        link.href = "#" + heading.id;
        link.textContent = heading.textContent.replace(/\s+/g, " ").trim() || heading.id;
        link.addEventListener("click", function (event) {
          event.preventDefault();
          closeTocDrawer(false);
          scrollToHeading(heading);
          if (window.history && typeof window.history.replaceState === "function") {
            window.history.replaceState(null, "", "#" + heading.id);
          }
        });

        item.appendChild(link);
        tocList.appendChild(item);
        tocItems.push({ heading: heading, link: link });
      });

      tocToggle.addEventListener("click", function () {
        if (isTocOpen()) {
          closeTocDrawer(true);
        } else {
          openTocDrawer();
        }
      });
      tocClose.addEventListener("click", function () {
        closeTocDrawer(true);
      });
      tocBackdrop.addEventListener("click", function () {
        closeTocDrawer(true);
      });

      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape" || !isTocOpen()) {
          return;
        }
        if (document.querySelector(".image-lightbox[open]")) {
          /* 灯箱优先，交给原生 dialog 处理。 */
          return;
        }
        closeTocDrawer(true);
      });

      /* 抽屉打开时把 Tab 焦点限制在目录内。 */
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Tab" || !isTocOpen()) {
          return;
        }
        const focusables = [tocClose]
          .concat(
            tocItems.map(function (entry) {
              return entry.link;
            })
          )
          .filter(function (element) {
            return element.offsetParent !== null;
          });
        if (!focusables.length) {
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });

      if (window.matchMedia) {
        const desktopTocQuery = window.matchMedia("(min-width: 1120px)");
        const onTocViewportChange = function (event) {
          if (event.matches) {
            closeTocDrawer(false);
          }
        };
        if (typeof desktopTocQuery.addEventListener === "function") {
          desktopTocQuery.addEventListener("change", onTocViewportChange);
        } else if (typeof desktopTocQuery.addListener === "function") {
          desktopTocQuery.addListener(onTocViewportChange);
        }
      }

      /* 滚动高亮当前章节（吸顶头下方留约 120px 判定线）。 */
      const TOC_OFFSET = 130;
      let activeTocEntry = null;
      let tocSyncScheduled = false;

      const setActiveTocEntry = function (entry) {
        if (!entry || activeTocEntry === entry) {
          return;
        }
        tocItems.forEach(function (item) {
          item.link.classList.toggle("is-active", item === entry);
          if (item === entry) {
            item.link.setAttribute("aria-current", "location");
          } else {
            item.link.removeAttribute("aria-current");
          }
        });
        activeTocEntry = entry;
      };

      const syncTocActive = function () {
        tocSyncScheduled = false;
        if (!tocItems.length) {
          return;
        }
        let current = tocItems[0];
        tocItems.forEach(function (entry) {
          if (entry.heading.getBoundingClientRect().top - TOC_OFFSET <= 0) {
            current = entry;
          }
        });
        const doc = document.documentElement;
        const scrolled = window.scrollY || window.pageYOffset || 0;
        if (window.innerHeight + scrolled >= doc.scrollHeight - 4) {
          current = tocItems[tocItems.length - 1];
        }
        setActiveTocEntry(current);
      };

      const requestTocSync = function () {
        if (tocSyncScheduled) {
          return;
        }
        tocSyncScheduled = true;
        requestFrame(syncTocActive);
      };

      syncTocActive();
      window.addEventListener("scroll", requestTocSync, { passive: true });
      window.addEventListener("resize", requestTocSync);
    }
  }

  /* ---------- 代码块：语言角标 + 复制 ---------- */

  const codeLanguage = function (code, pre) {
    const className = [code.className, pre.className].join(" ");
    const match =
      className.match(/language-([a-z0-9_+#.-]+)/i) ||
      className.match(/lang-([a-z0-9_+#.-]+)/i);
    return match ? match[1].toLowerCase() : "代码";
  };

  const prosePres = Array.prototype.slice.call(document.querySelectorAll(".prose pre"));

  prosePres.forEach(function (pre) {
    if (pre.parentElement && pre.parentElement.classList.contains("code-block")) {
      return;
    }
    const code = pre.querySelector("code") || pre;
    const wrapper = document.createElement("div");
    wrapper.className = "code-block";
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const toolbar = document.createElement("div");
    toolbar.className = "code-toolbar";

    const languageLabel = document.createElement("span");
    languageLabel.className = "code-lang";
    languageLabel.textContent = codeLanguage(code, pre);

    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "code-copy";
    copyButton.textContent = "复制";
    copyButton.setAttribute("aria-label", "复制代码");

    const copyStatus = document.createElement("span");
    copyStatus.className = "code-copy-status sr-only";
    copyStatus.setAttribute("role", "status");
    copyStatus.setAttribute("aria-live", "polite");

    toolbar.appendChild(languageLabel);
    toolbar.appendChild(copyButton);
    toolbar.appendChild(copyStatus);
    wrapper.insertBefore(toolbar, pre);

    let copyResetTimer = null;
    const showCopyState = function (ok) {
      copyButton.textContent = ok ? "已复制" : "复制失败";
      copyButton.classList.toggle("is-copied", ok);
      copyButton.classList.toggle("is-failed", !ok);
      copyStatus.textContent = ok
        ? "代码已复制到剪贴板"
        : "复制失败，请手动选中代码复制";
      if (copyResetTimer) {
        window.clearTimeout(copyResetTimer);
      }
      copyResetTimer = window.setTimeout(function () {
        copyButton.textContent = "复制";
        copyButton.classList.remove("is-copied", "is-failed");
        copyStatus.textContent = "";
      }, 1800);
    };

    copyButton.addEventListener("click", function () {
      copyToClipboard(code.textContent).then(
        function () {
          showCopyState(true);
        },
        function () {
          showCopyState(false);
        }
      );
    });

    /* 横向滚动阴影：可滚动时右缘加深，滚到结尾时淡出。 */
    const syncCodeShadow = function () {
      const scrollable = pre.scrollWidth - pre.clientWidth > 2;
      wrapper.classList.toggle("is-scrollable", scrollable);
      wrapper.classList.toggle(
        "is-scrolled-end",
        scrollable && pre.scrollLeft + pre.clientWidth >= pre.scrollWidth - 2
      );
    };

    pre.addEventListener("scroll", syncCodeShadow, { passive: true });
    window.addEventListener("resize", syncCodeShadow);
    window.addEventListener("load", syncCodeShadow);
    requestFrame(syncCodeShadow);
  });

  /* ---------- 图片灯箱 ---------- */

  const zoomableImages = Array.prototype.filter.call(
    document.querySelectorAll(".prose img"),
    function (image) {
      return !image.closest("a") && Boolean(image.getAttribute("src"));
    }
  );

  const dialogTest = document.createElement("dialog");
  const supportsDialog =
    typeof dialogTest.showModal === "function" &&
    typeof dialogTest.close === "function";

  if (zoomableImages.length && supportsDialog) {
    const lightbox = document.createElement("dialog");
    lightbox.className = "image-lightbox";
    lightbox.setAttribute("aria-label", "图片预览");

    const lightboxClose = document.createElement("button");
    lightboxClose.type = "button";
    lightboxClose.className = "lightbox-close";
    lightboxClose.setAttribute("aria-label", "关闭图片预览");
    lightboxClose.textContent = "×";

    const lightboxFigure = document.createElement("figure");
    lightboxFigure.className = "lightbox-figure";

    const lightboxImage = document.createElement("img");
    lightboxImage.className = "lightbox-image";
    lightboxImage.alt = "";

    const lightboxCaption = document.createElement("figcaption");
    lightboxCaption.className = "lightbox-caption";

    lightboxFigure.appendChild(lightboxImage);
    lightboxFigure.appendChild(lightboxCaption);
    lightbox.appendChild(lightboxClose);
    lightbox.appendChild(lightboxFigure);
    document.body.appendChild(lightbox);

    let lastImageTrigger = null;

    const closeLightbox = function () {
      if (lightbox.open) {
        lightbox.close();
      }
    };

    const openLightbox = function (image) {
      lastImageTrigger = image;
      lightboxImage.src = image.currentSrc || image.src;
      lightboxImage.alt = image.getAttribute("alt") || "";
      lightboxCaption.textContent = image.getAttribute("alt") || "";
      lightboxCaption.hidden = !image.getAttribute("alt");
      document.body.classList.add("lightbox-open");
      if (!lightbox.open) {
        lightbox.showModal();
      }
      lightboxClose.focus({ preventScroll: true });
    };

    lightbox.addEventListener("click", function (event) {
      /* 点击 dialog 自身即为点击图片外的遮罩区域。 */
      if (event.target === lightbox) {
        closeLightbox();
      }
    });
    lightboxClose.addEventListener("click", closeLightbox);
    lightbox.addEventListener("close", function () {
      document.body.classList.remove("lightbox-open");
      if (lastImageTrigger && document.contains(lastImageTrigger)) {
        lastImageTrigger.focus({ preventScroll: true });
      }
      lastImageTrigger = null;
    });

    zoomableImages.forEach(function (image) {
      image.classList.add("is-zoomable");
      image.setAttribute("tabindex", "0");
      image.setAttribute("role", "button");
      image.setAttribute(
        "aria-label",
        "查看大图：" + (image.getAttribute("alt") || "文章图片")
      );
      image.addEventListener("click", function () {
        openLightbox(image);
      });
      image.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
          event.preventDefault();
          openLightbox(image);
        }
      });
    });
  }

  /* ---------- 复制文章链接 ---------- */

  const shareButtons = document.querySelectorAll("[data-share-copy]");

  Array.prototype.forEach.call(shareButtons, function (button) {
    const originalLabel = button.textContent;
    button.setAttribute("aria-live", "polite");
    let shareResetTimer = null;

    const showShareState = function (ok) {
      button.textContent = ok ? "已复制链接" : "复制失败";
      button.classList.toggle("is-copied", ok);
      button.classList.toggle("is-failed", !ok);
      if (shareResetTimer) {
        window.clearTimeout(shareResetTimer);
      }
      shareResetTimer = window.setTimeout(function () {
        button.textContent = originalLabel;
        button.classList.remove("is-copied", "is-failed");
      }, 1800);
    };

    button.addEventListener("click", function () {
      /* 复制规范的分享链接：去掉 #锚点，避免分享到文章中间位置。 */
      const shareUrl = window.location.href.split("#")[0];
      copyToClipboard(shareUrl).then(
        function () {
          showShareState(true);
        },
        function () {
          showShareState(false);
        }
      );
    });
  });

  /* ---------- 即时搜索 ---------- */

  const searchForm = document.querySelector("form[data-instant-search]");
  const searchInput = document.getElementById("search-q");
  const searchResults = document.getElementById("search-results");
  const searchStatus = document.getElementById("search-status");
  const searchEmpty = document.getElementById("search-empty");

  if (searchForm && searchInput && searchResults) {
    /* 服务端已渲染的结果快照：清空输入时原样恢复（内容来自服务端安全 HTML）。 */
    const initialSearchHTML = searchResults.innerHTML;
    const initialSearchStatus = searchStatus ? searchStatus.textContent : "";
    const initialSearchEmptyHidden = searchEmpty ? searchEmpty.hidden : true;

    let searchTimer = null;
    let searchController = null;

    const abortPendingSearch = function () {
      if (searchController) {
        searchController.abort();
        searchController = null;
      }
    };

    const setSearchStatus = function (text) {
      if (searchStatus) {
        searchStatus.textContent = text;
      }
    };

    const setSearchEmpty = function (visible) {
      if (searchEmpty) {
        searchEmpty.hidden = !visible;
      }
    };

    const restoreInitialResults = function () {
      abortPendingSearch();
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = null;
      }
      searchResults.innerHTML = initialSearchHTML;
      setSearchStatus(initialSearchStatus);
      setSearchEmpty(!initialSearchEmptyHidden);
    };

    const formatSearchDate = function (value) {
      if (!value) {
        return "";
      }
      const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (!match) {
        return String(value);
      }
      return match[1] + "年" + match[2] + "月" + match[3] + "日";
    };

    const splitSearchTags = function (raw) {
      if (!raw) {
        return [];
      }
      return String(raw)
        .split(",")
        .map(function (tag) {
          return tag.trim();
        })
        .filter(Boolean);
    };

    /* 把文本安全地写入容器，并把查询词包成 <mark>（全部使用 textContent）。 */
    const appendHighlighted = function (container, text, query) {
      const source = String(text || "");
      if (!query) {
        container.textContent = source;
        return;
      }
      const lowerSource = source.toLowerCase();
      const lowerQuery = query.toLowerCase();
      let from = 0;
      let index = lowerSource.indexOf(lowerQuery);
      while (index !== -1) {
        if (index > from) {
          container.appendChild(document.createTextNode(source.slice(from, index)));
        }
        const mark = document.createElement("mark");
        mark.textContent = source.slice(index, index + query.length);
        container.appendChild(mark);
        from = index + query.length;
        index = lowerSource.indexOf(lowerQuery, from);
      }
      if (from < source.length) {
        container.appendChild(document.createTextNode(source.slice(from)));
      }
    };

    const buildSearchCard = function (post, query) {
      const article = document.createElement("article");
      const slug = post && post.slug ? String(post.slug) : "";
      const href = "/post/" + encodeURIComponent(slug);
      const cover = post && post.cover_url ? String(post.cover_url) : "";
      article.className = "post-card" + (cover ? " post-card--with-cover" : "");

      if (cover) {
        const coverLink = document.createElement("a");
        coverLink.className = "post-card-cover";
        coverLink.href = href;
        coverLink.setAttribute("tabindex", "-1");
        coverLink.setAttribute("aria-hidden", "true");
        const image = document.createElement("img");
        image.src = cover;
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        coverLink.appendChild(image);
        article.appendChild(coverLink);
      }

      const meta = document.createElement("p");
      meta.className = "post-meta";
      const time = document.createElement("time");
      time.setAttribute("datetime", post && post.published_at ? post.published_at : "");
      time.textContent = formatSearchDate(post && post.published_at);
      meta.appendChild(time);
      const separator = document.createElement("span");
      separator.className = "meta-sep";
      separator.setAttribute("aria-hidden", "true");
      separator.textContent = "·";
      meta.appendChild(separator);
      const reading = document.createElement("span");
      reading.textContent = "约 " + (post && post.reading_time ? post.reading_time : 1) + " 分钟";
      meta.appendChild(reading);
      article.appendChild(meta);

      const heading = document.createElement("h2");
      heading.className = "post-card-title";
      const titleLink = document.createElement("a");
      titleLink.href = href;
      appendHighlighted(titleLink, post && post.title ? post.title : "无标题", query);
      heading.appendChild(titleLink);
      article.appendChild(heading);

      if (post && post.summary) {
        const summary = document.createElement("p");
        summary.className = "post-card-summary";
        appendHighlighted(summary, post.summary, query);
        article.appendChild(summary);
      }

      const foot = document.createElement("div");
      foot.className = "post-card-foot";
      const tags = splitSearchTags(post && post.tags);
      if (tags.length) {
        const tagList = document.createElement("ul");
        tagList.className = "tag-list";
        tagList.setAttribute("aria-label", "文章标签");
        tags.forEach(function (tag) {
          const item = document.createElement("li");
          const tagLink = document.createElement("a");
          tagLink.className = "tag";
          tagLink.href = "/tag/" + encodeURIComponent(tag);
          tagLink.textContent = tag;
          item.appendChild(tagLink);
          tagList.appendChild(item);
        });
        foot.appendChild(tagList);
      } else {
        const noTag = document.createElement("span");
        noTag.className = "post-views";
        noTag.textContent = "未设标签";
        foot.appendChild(noTag);
      }
      article.appendChild(foot);
      return article;
    };

    const renderSearchResults = function (query, payload) {
      const posts = payload && Array.isArray(payload.results) ? payload.results : [];
      const total =
        payload && typeof payload.total === "number" ? payload.total : posts.length;
      searchResults.replaceChildren();
      if (posts.length) {
        const list = document.createElement("div");
        list.className = "post-list";
        posts.forEach(function (post) {
          list.appendChild(buildSearchCard(post, query));
        });
        searchResults.appendChild(list);
      }
      setSearchEmpty(posts.length === 0);
      setSearchStatus(
        posts.length
          ? "找到 " + total + " 篇与「" + query + "」相关的文章。"
          : "没有找到与「" + query + "」相关的文章。"
      );
    };

    const runSearch = function (query) {
      abortPendingSearch();
      let controller = null;
      if (typeof AbortController === "function") {
        controller = new AbortController();
      }
      searchController = controller;
      setSearchStatus("正在搜索…");
      const options = { headers: { Accept: "application/json" } };
      if (controller) {
        options.signal = controller.signal;
      }
      fetch("/api/search?q=" + encodeURIComponent(query), options)
        .then(function (response) {
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          return response.json();
        })
        .then(function (payload) {
          if (controller && controller.signal.aborted) {
            return;
          }
          searchController = null;
          renderSearchResults(query, payload);
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          searchController = null;
          setSearchEmpty(false);
          setSearchStatus("搜索失败，请重试。");
        });
    };

    const handleSearchInput = function () {
      const query = searchInput.value.trim();
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = null;
      }
      if (!query) {
        restoreInitialResults();
        return;
      }
      abortPendingSearch();
      setSearchStatus("正在搜索…");
      searchTimer = window.setTimeout(function () {
        searchTimer = null;
        runSearch(query);
      }, 200);
    };

    searchInput.addEventListener("input", handleSearchInput);
    searchInput.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }
      if (searchInput.value) {
        searchInput.value = "";
        restoreInitialResults();
      } else {
        searchInput.blur();
      }
    });

    /* 若从首页按 / 跳转过来，落地后自动聚焦搜索框。 */
    try {
      if (window.sessionStorage.getItem("search:focus") === "1") {
        window.sessionStorage.removeItem("search:focus");
        searchInput.focus();
        searchInput.select();
      }
    } catch (error) {
      /* 隐私模式下 sessionStorage 不可用，忽略即可。 */
    }
  }

  /* `/` 快捷键：任意页面聚焦搜索 / 跳转到搜索页。 */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    const target = event.target;
    if (target) {
      const tagName = target.tagName ? target.tagName.toLowerCase() : "";
      if (
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        target.isContentEditable
      ) {
        return;
      }
    }
    event.preventDefault();
    const input = document.getElementById("search-q");
    if (input) {
      input.focus();
      input.select();
      if (typeof input.scrollIntoView === "function") {
        input.scrollIntoView({
          block: "center",
          behavior: prefersReducedMotion() ? "auto" : "smooth",
        });
      }
      return;
    }
    try {
      window.sessionStorage.setItem("search:focus", "1");
    } catch (error) {
      /* 忽略存储失败。 */
    }
    window.location.assign("/search");
  });

})();
