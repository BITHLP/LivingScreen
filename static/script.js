/**
 * scripts.js
 * 短视频交互逻辑
 */

/* ------------------------------------------------------------------
 * 模块级状态
 * ------------------------------------------------------------------ */

let currentVideoId = null;
let isDragging = false;
let startY = 0;
let startScrollTop = 0;
let dragTarget = null;
let dragDistance = 0;   // 用于区分"点击"和"拖拽"
let isDraggingProgress = false;

/* ------------------------------------------------------------------
 * 工具函数
 * ------------------------------------------------------------------ */

/** HTML 文本转义 — 避免把后端/视频元数据里的字符当成 HTML 标签。 */
function escapeHtml(str) {
    return String(str == null ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/** mm:ss。秒数非数字时回退 "00:00"，避免 NaN 展示。 */
function formatTime(seconds) {
    if (typeof seconds !== "number" || isNaN(seconds)) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

/** 向上追溯最近一个带 data-video-id 的父元素。 */
function getVideoIdFromElement(el) {
    while (el && !el.dataset.videoId) el = el.parentElement;
    return el ? el.dataset.videoId : null;
}

/** 重新渲染 lucide 图标（在动态插入/修改图标属性后调用）。 */
function refreshIcons() {
    if (typeof lucide !== "undefined") lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", refreshIcons);

/* ------------------------------------------------------------------
 * 点赞 / 收藏
 * ------------------------------------------------------------------ */

async function toggleLike(el) {
    const vid = getVideoIdFromElement(el);
    const res = await fetch(`/api/video/${vid}/like`, { method: "POST" });
    const data = await res.json();
    if (data.status !== "success") return;

    const span = el.querySelector("span");
    const svg = el.querySelector("svg");
    span.innerText = data.likes;

    if (data.is_liked) {
        svg.setAttribute("fill", "#FE2C55");
        svg.setAttribute("stroke", "#FE2C55");
        svg.style.color = "#FE2C55";
        el.style.transform = "scale(1.4)";
        setTimeout(() => { el.style.transform = "scale(1)"; }, 150);
    } else {
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.style.color = "white";
    }
    refreshIcons();
}

async function toggleCollect(el) {
    const vid = getVideoIdFromElement(el);
    const res = await fetch(`/api/video/${vid}/collect`, { method: "POST" });
    const data = await res.json();
    if (data.status !== "success") return;

    const span = el.querySelector('[data-testid="collect-count-badge"]');
    const svg = el.querySelector("svg");
    span.innerText = data.collects;

    if (data.is_collected) {
        svg.setAttribute("fill", "#FEEF00");
        svg.setAttribute("stroke", "#FEEF00");
        svg.style.color = "#FEEF00";
        el.style.transform = "scale(1.4)";
        setTimeout(() => { el.style.transform = "scale(1)"; }, 150);
    } else {
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.style.color = "white";
    }
    refreshIcons();
}

/* ------------------------------------------------------------------
 * 评论抽屉
 * ------------------------------------------------------------------ */

async function openComments(vid) {
    currentVideoId = vid;
    document.getElementById("comment-drawer").classList.add("active");
    const res = await fetch(`/api/video/${vid}/comments`);
    const data = await res.json();
    renderComments(data.comments, vid);
}

function renderComments(comments, vid) {
    const container = document.getElementById("comment-list-container");
    let totalCount = comments.length;
    comments.forEach(c => {
        if (c.replies) totalCount += c.replies.length;
    });

    document.getElementById("comment-count-title").innerText = `评论 (${totalCount})`;

    const badge = document.querySelector(
        `.video-item[data-video-id="${vid}"] [data-testid="comment-count-badge"]`
    );
    if (badge) badge.innerText = totalCount;

    // 用户文本用 escapeHtml，避免后端/视频元数据里含特殊字符被当作 HTML
    container.innerHTML = comments.map(c => {
        const repliesHtml = (c.replies && c.replies.length > 0) ? `
            <div class="expand-replies-btn" onclick="toggleReplies(${c.id}, this)">
                <div style="width:20px; height:1px; background:#eee;"></div>
                展开${c.replies.length}条回复
            </div>
            <div id="replies-${c.id}" class="replies-list hidden">
                ${c.replies.map(r => `
                    <div class="reply-item">
                        <img class="reply-avatar"
                             src="https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(r.user)}">
                        <div class="comment-content">
                            <div class="comment-user">${escapeHtml(r.user)}</div>
                            <div class="comment-text">${escapeHtml(r.text)}</div>
                        </div>
                    </div>
                `).join("")}
            </div>
        ` : "";

        return `
            <div class="comment-item">
                <div class="comment-main">
                    <img class="comment-avatar"
                         src="https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(c.user)}">
                    <div class="comment-content">
                        <div class="comment-user">${escapeHtml(c.user)}</div>
                        <div class="comment-text">${escapeHtml(c.text)}</div>
                        ${repliesHtml}
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

function toggleReplies(cid, btn) {
    const list = document.getElementById(`replies-${cid}`);
    const isHidden = list.classList.toggle("hidden");
    btn.innerHTML = isHidden
        ? `<div style="width:20px; height:1px; background:#eee;"></div>展开${list.children.length}条回复`
        : `<div style="width:20px; height:1px; background:#eee;"></div>收起回复`;
}

async function postComment() {
    const input = document.getElementById("comment-input");
    if (!input.value) return;

    const res = await fetch(`/api/video/${currentVideoId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input.value }),
    });
    const data = await res.json();
    renderComments(data.comments, currentVideoId);
    input.value = "";
}

/* ------------------------------------------------------------------
 * 举报
 * ------------------------------------------------------------------ */

function openReport(vid) {
    currentVideoId = vid;
    document.getElementById("report-modal").style.display = "flex";
}

async function submitReport() {
    const cat = document.querySelector('input[name="report-cat"]:checked')?.value;
    const reason = document.getElementById("report-reason").value;
    if (!cat) {
        alert("请选择类别");
        return;
    }
    await fetch(`/api/video/${currentVideoId}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: cat, reason: reason }),
    });
    closeDrawer("report-modal");
}

function closeDrawer(id) {
    const el = document.getElementById(id);
    if (id === "report-modal") {
        el.style.display = "none";
    } else {
        el.classList.remove("active");
    }
}

/* ------------------------------------------------------------------
 * 全局拖拽：区分翻页（drag）与点击（click）
 *
 * 注意：dragDistance 在 mouseup 里不重置，保留给紧随其后的 click 事件
 *（togglePlayPause）做判断；判断完成后由 togglePlayPause 自己清。
 * ------------------------------------------------------------------ */

document.addEventListener("mousedown", (e) => {
    const commentList = e.target.closest(".comment-list");
    const videoFeed = e.target.closest(".video-feed");
    const sidebar = e.target.closest(".side-bar, .comment-input-area, .drawer-header");

    if (sidebar) return;

    if (commentList) {
        dragTarget = commentList;
    } else if (videoFeed) {
        dragTarget = videoFeed;
        videoFeed.style.scrollSnapType = "none";
    } else {
        return;
    }

    isDragging = true;
    startY = e.pageY;
    dragDistance = 0;       // 按下时重置位移，给本轮判断用
    startScrollTop = dragTarget.scrollTop;
    dragTarget.style.cursor = "grabbing";

    if (dragTarget === videoFeed) e.preventDefault();
});

window.addEventListener("mousemove", (e) => {
    if (!isDragging || !dragTarget) return;

    const deltaX = Math.abs(e.pageX - startY); // x 方向位移仅用于区分 click vs drag
    const deltaY = Math.abs(e.pageY - startY);
    dragDistance = Math.max(deltaX, deltaY);

    const walk = (e.pageY - startY) * 1.2;
    dragTarget.scrollTop = startScrollTop - walk;

    if (dragTarget.classList.contains("video-feed")) {
        e.preventDefault();
    }
});

window.addEventListener("mouseup", () => {
    if (!isDragging || !dragTarget) return;

    if (dragTarget.classList.contains("video-feed")) {
        const totalDelta = dragTarget.scrollTop - startScrollTop;
        const videoHeight = dragTarget.clientHeight;

        dragTarget.style.scrollSnapType = "y mandatory";

        if (Math.abs(totalDelta) > videoHeight * 0.3) {
            if (totalDelta > 0) {
                dragTarget.scrollTo({ top: startScrollTop + videoHeight, behavior: "smooth" });
            } else {
                dragTarget.scrollTo({ top: startScrollTop - videoHeight, behavior: "smooth" });
            }
        } else {
            dragTarget.scrollTo({ top: startScrollTop, behavior: "smooth" });
        }
    }

    dragTarget.style.cursor = "default";
    isDragging = false;
    dragTarget = null;
    // 注：dragDistance 不在此处重置，留给紧随的 click 事件（togglePlayPause）判断
});

/* ------------------------------------------------------------------
 * 播放/暂停 + 进度条
 * ------------------------------------------------------------------ */

/** 切换播放/暂停。位移>5px 视为翻页拖拽，不切换。 */
function togglePlayPause(container) {
    if (dragDistance > 5) {
        dragDistance = 0;
        return;
    }

    const video = container.querySelector("video");
    const item = container.closest(".video-item");

    if (video.paused) {
        video.play();
        item.classList.remove("paused");
    } else {
        video.pause();
        item.classList.add("paused");
    }
}

/* 每个 <video> 元数据加载后，绑定 time/duration 展示。 */
document.querySelectorAll(".main-video").forEach(video => {
    const item = video.closest(".video-item");

    video.addEventListener("loadedmetadata", () => {
        const totalTimeEl = item.querySelector(".total-time");
        if (totalTimeEl) totalTimeEl.innerText = formatTime(video.duration);
    });

    video.addEventListener("timeupdate", () => {
        if (isDraggingProgress) return;
        const progress = (video.currentTime / video.duration) * 100;
        const filled = item.querySelector(".progress-filled");
        const currentText = item.querySelector(".current-time");
        if (filled) filled.style.width = `${progress}%`;
        if (currentText) currentText.innerText = formatTime(video.currentTime);
    });
});

/* 进度条拖拽 seek。 */
function startSeek(e, container) {
    e.stopPropagation();
    isDraggingProgress = true;
    updateSeek(e, container);

    const onMouseMove = (event) => {
        if (isDraggingProgress) updateSeek(event, container);
    };

    const onMouseUp = () => {
        isDraggingProgress = false;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
}

function updateSeek(e, container) {
    const rect = container.getBoundingClientRect();
    let pos = (e.clientX - rect.left) / rect.width;
    pos = Math.max(0, Math.min(1, pos));

    const videoItem = container.closest(".video-item");
    const video = videoItem.querySelector("video");

    if (!isNaN(video.duration)) {
        video.currentTime = pos * video.duration;
        const filled = container.querySelector(".progress-filled");
        const currentTimeEl = videoItem.querySelector(".current-time");
        if (filled) filled.style.width = `${pos * 100}%`;
        if (currentTimeEl) currentTimeEl.innerText = formatTime(video.currentTime);
    }
}

/* ------------------------------------------------------------------
 * 自动播放：滚动到可视区的视频播放，离开的暂停
 * ------------------------------------------------------------------ */

const videoObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        const item = entry.target;
        const video = item.querySelector("video");

        if (entry.isIntersecting) {
            video.play().then(() => {
                item.classList.remove("paused");
            }).catch(() => {
                // 浏览器自动播放策略可能阻止有声音播放，静音后再试
                video.muted = true;
                video.play();
                item.classList.remove("paused");
            });
        } else {
            video.pause();
            video.currentTime = 0;
            item.classList.remove("paused");
        }
    });
}, {
    root: document.querySelector(".video-feed"),
    threshold: 0.8,
});

document.querySelectorAll(".video-item").forEach(item => {
    videoObserver.observe(item);
});
