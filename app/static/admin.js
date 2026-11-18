/* ============================================================
   纸上 · 管理后台脚本（原生 JS，无依赖）
   功能：主题切换、移动端导航折叠、删除二次确认、
         Markdown 实时预览、字数统计、Ctrl/⌘+S 保存、
         Markdown 导入（拖拽 / 文件列表 / 大小校验 / 防重复提交）
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

  /* ---------- Markdown 导入：拖拽 / 文件列表 / 校验 / 防重复提交 ---------- */
  const importForm = document.getElementById("import-form");
  if (importForm) {
    const IMPORT_MAX_FILES = 50;
    const IMPORT_MAX_SIZE = 5 * 1024 * 1024; // 5 MB
    const IMPORT_ACCEPT_RE = /\.(md|markdown|txt)$/i;

    const fileInput = document.getElementById("import-files");
    const dropZone = document.getElementById("import-drop");
    const filesPanel = document.getElementById("import-files-panel");
    const fileList = document.getElementById("import-file-list");
    const filesCount = document.getElementById("import-files-count");
    const clearButton = document.getElementById("import-clear");
    const filesError = document.getElementById("import-files-error");
    const submitButton = document.getElementById("import-submit");
    const submitHint = document.getElementById("import-submit-hint");

    let selectedFiles = [];
    let submitting = false;

    // 能否用 DataTransfer 回写 input.files（用于合并/移除已选文件）
    const canRebuildSelection = (() => {
      try {
        return typeof window.DataTransfer === "function";
      } catch (err) {
        return false;
      }
    })();

    const fileKey = (file) =>
      [file.name, file.size, file.lastModified || 0].join("\u0000");

    const formatSize = (bytes) => {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / 1024 / 1024).toFixed(2) + " MB";
    };

    const setFileError = (messages) => {
      if (!filesError) return;
      const text = (messages || []).join(" ");
      filesError.textContent = text;
      filesError.hidden = !text;
    };

    const syncUi = () => {
      const count = selectedFiles.length;
      const hasFiles = count > 0;
      if (filesCount) filesCount.textContent = String(count);
      if (filesPanel) filesPanel.hidden = !hasFiles;
      if (submitButton) submitButton.disabled = submitting || !hasFiles;
      if (submitHint) {
        if (submitting) {
          submitHint.textContent = "正在解析并写入文章，请稍候…";
        } else if (hasFiles) {
          submitHint.textContent = "已选择 " + count + " 个文件，导入时会逐篇解析。";
        } else {
          submitHint.textContent = "导入时会逐篇解析文件，处理结果会显示在下方。";
        }
      }
    };

    const rebuildSelection = () => {
      if (!canRebuildSelection || !fileInput) return;
      const transfer = new window.DataTransfer();
      selectedFiles.forEach((file) => transfer.items.add(file));
      fileInput.files = transfer.files;
    };

    const renderFileList = () => {
      if (!fileList) return;
      fileList.textContent = "";
      selectedFiles.forEach((file, index) => {
        const item = document.createElement("li");
        item.className = "import-file";

        const info = document.createElement("span");
        info.className = "import-file__info";

        const name = document.createElement("span");
        name.className = "import-file__name";
        name.textContent = file.name;

        const meta = document.createElement("span");
        meta.className = "import-file__meta";
        meta.textContent = formatSize(file.size);

        info.appendChild(name);
        info.appendChild(meta);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "import-file__remove";
        remove.setAttribute("aria-label", "移除文件 " + file.name);
        remove.textContent = "移除";
        remove.addEventListener("click", () => {
          selectedFiles.splice(index, 1);
          rebuildSelection();
          renderFileList();
          syncUi();
          setFileError([]);
        });

        item.appendChild(info);
        item.appendChild(remove);
        fileList.appendChild(item);
      });
    };

    const addFiles = (incoming) => {
      const problems = [];
      const seen = new Set(selectedFiles.map(fileKey));
      let limitReported = false;

      Array.from(incoming).forEach((file) => {
        if (!IMPORT_ACCEPT_RE.test(file.name || "")) {
          problems.push("「" + file.name + "」不是支持的格式（仅 .md / .markdown / .txt）。");
          return;
        }
        if (file.size > IMPORT_MAX_SIZE) {
          problems.push("「" + file.name + "」超过 5 MB 上限，已忽略。");
          return;
        }
        const key = fileKey(file);
        if (seen.has(key)) return; // 重复选择同一个文件，忽略
        if (selectedFiles.length >= IMPORT_MAX_FILES) {
          if (!limitReported) {
            problems.push("一次最多导入 " + IMPORT_MAX_FILES + " 个文件，多出的文件已忽略。");
            limitReported = true;
          }
          return;
        }
        seen.add(key);
        selectedFiles.push(file);
      });

      rebuildSelection();
      renderFileList();
      syncUi();
      setFileError(problems);
    };

    if (fileInput) {
      fileInput.addEventListener("change", () => {
        const files = fileInput.files;
        if (!files || !files.length) return;
        // 无法回写 input.files 的旧浏览器：以本次选择为准，避免列表与实际提交不一致
        if (!canRebuildSelection) selectedFiles = [];
        addFiles(files);
      });
    }

    if (clearButton) {
      clearButton.addEventListener("click", () => {
        selectedFiles = [];
        rebuildSelection();
        renderFileList();
        syncUi();
        setFileError([]);
      });
    }

    const eventHasFiles = (event) => {
      const transfer = event.dataTransfer;
      if (!transfer || !transfer.types) return false;
      return Array.prototype.indexOf.call(transfer.types, "Files") !== -1;
    };

    if (dropZone) {
      let dragDepth = 0;
      const setDragState = (active) => dropZone.classList.toggle("is-dragover", active);

      dropZone.addEventListener("dragenter", (event) => {
        if (!eventHasFiles(event)) return;
        event.preventDefault();
        dragDepth += 1;
        setDragState(true);
      });

      dropZone.addEventListener("dragover", (event) => {
        if (!eventHasFiles(event)) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      });

      dropZone.addEventListener("dragleave", () => {
        // dragleave 的 dataTransfer.types 可能为空，这里无条件递减以可靠复位高亮
        dragDepth = Math.max(0, dragDepth - 1);
        if (dragDepth === 0) setDragState(false);
      });

      dropZone.addEventListener("drop", (event) => {
        if (!eventHasFiles(event)) return;
        event.preventDefault();
        dragDepth = 0;
        setDragState(false);
        const transfer = event.dataTransfer;
        const files = transfer ? transfer.files : null;
        if (!files || !files.length) return;
        if (!canRebuildSelection) {
          setFileError(["当前浏览器不支持拖拽上传，请点击选择文件。"]);
          return;
        }
        addFiles(files);
      });
    }

    // 避免文件被拖到页面空白处时浏览器直接打开文件（离开拖拽区后仅拦截，不处理）
    const guardFileDrop = (event) => {
      if (!eventHasFiles(event)) return;
      if (dropZone && dropZone.contains(event.target)) return;
      event.preventDefault();
    };
    document.addEventListener("dragover", guardFileDrop);
    document.addEventListener("drop", guardFileDrop);

    importForm.addEventListener("submit", (event) => {
      if (submitting) {
        event.preventDefault();
        return;
      }
      if (!selectedFiles.length) {
        event.preventDefault();
        setFileError(["请先选择要导入的 Markdown 文件。"]);
        if (fileInput) fileInput.focus();
        return;
      }
      submitting = true;
      importForm.setAttribute("aria-busy", "true");
      if (submitButton) submitButton.textContent = "正在导入…";
      syncUi();
    });

    // 从往返缓存（bfcache）返回时恢复按钮可用状态
    window.addEventListener("pageshow", () => {
      submitting = false;
      importForm.removeAttribute("aria-busy");
      if (submitButton) submitButton.textContent = "开始导入";
      syncUi();
    });

    syncUi();
  }
})();
