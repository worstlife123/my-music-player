#!/usr/bin/env python3
"""Interactive Web Preview Server for Aurora Music Player (Port 3000)."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PLAYER_FILE = ROOT_DIR / "player_aurora_smart_beautiful_fixed_ui_repaint.py"

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aurora Music Player — Interactive UI Preview</title>
  <meta name="description" content="Aurora — умный десктопный музыкальный плеер на PyQt6 с компактным анимированным окном обложки" />
  <meta property="og:title" content="Aurora Music Player — Interactive UI Preview" />
  <meta property="og:description" content="Aurora — умный десктопный музыкальный плеер на PyQt6 с компактным анимированным окном обложки" />
  <style>
    :root {
      --bg-window: #07070b;
      --bg-sidebar: #050508;
      --bg-panel: rgba(255, 255, 255, 0.032);
      --bg-card: #12121a;
      --bg-card-hover: #1b1b27;
      --bg-input: #14141d;
      --bg-bottom: #0c0c12;
      --bg-popup: rgba(20, 20, 29, 0.97);
      --border-subtle: rgba(255, 255, 255, 0.07);
      --border-popup: rgba(255, 255, 255, 0.13);
      --text-main: #f8fafc;
      --text-sub: #a1a1aa;
      --text-muted: #71717a;
      --accent: #7c3aed;
      --accent-hover: #8b5cf6;
      --accent-glow: rgba(124, 58, 237, 0.28);
    }

    body.light-theme {
      --bg-window: #f4f5f8;
      --bg-sidebar: #eceef4;
      --bg-panel: rgba(255, 255, 255, 0.78);
      --bg-card: #ffffff;
      --bg-card-hover: #f1f5f9;
      --bg-input: #ffffff;
      --bg-bottom: rgba(255, 255, 255, 0.95);
      --bg-popup: rgba(255, 255, 255, 0.98);
      --border-subtle: rgba(15, 23, 42, 0.08);
      --border-popup: rgba(15, 23, 42, 0.12);
      --text-main: #0f172a;
      --text-sub: #475569;
      --text-muted: #64748b;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      user-select: none;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    body {
      background: var(--bg-window);
      color: var(--text-main);
      height: 100vh;
      width: 100vw;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: background 0.25s ease, color 0.25s ease;
    }

    /* Main Layout */
    .app-workspace {
      flex: 1;
      display: flex;
      min-height: 0;
      position: relative;
    }

    /* Sidebar */
    .sidebar {
      width: 248px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-subtle);
      padding: 22px 14px 18px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      z-index: 2;
    }

    .brand-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 10px 16px;
    }

    .brand-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 21px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }

    .brand-dot {
      width: 28px;
      height: 28px;
      border-radius: 9px;
      background: linear-gradient(135deg, #8b5cf6, #ec4899);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 14px;
      box-shadow: 0 6px 16px rgba(139, 92, 246, 0.35);
    }

    .nav-btn {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 11px 14px;
      border-radius: 12px;
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-sub);
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s ease;
      text-align: left;
      position: relative;
    }

    .nav-btn:hover {
      background: rgba(124, 58, 237, 0.08);
      color: var(--text-main);
    }

    .nav-btn.active {
      background: rgba(124, 58, 237, 0.15);
      border-color: rgba(139, 92, 246, 0.28);
      color: var(--text-main);
    }

    .nav-btn.active::before {
      content: "";
      position: absolute;
      left: 0;
      top: 9px;
      bottom: 9px;
      width: 3.5px;
      border-radius: 4px;
      background: #8b5cf6;
    }

    .sidebar-section-label {
      margin-top: 16px;
      padding: 0 12px 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
    }

    .sidebar-footer {
      margin-top: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid var(--border-subtle);
    }

    .hint-badge {
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(124, 58, 237, 0.12);
      border: 1px solid rgba(139, 92, 246, 0.25);
      font-size: 12px;
      line-height: 1.45;
      color: var(--text-main);
    }

    .hint-badge strong {
      color: #a78bfa;
    }

    /* Main Content Stack */
    .main-stack {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      position: relative;
      overflow: hidden;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 18px 28px 12px;
      gap: 16px;
    }

    .search-box {
      flex: 1;
      max-width: 440px;
      background: var(--bg-input);
      border: 1px solid var(--border-subtle);
      border-radius: 13px;
      padding: 10px 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--text-main);
    }

    .search-box input {
      background: transparent;
      border: none;
      outline: none;
      color: var(--text-main);
      font-size: 14px;
      width: 100%;
    }

    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .pill-btn {
      padding: 9px 14px;
      border-radius: 11px;
      border: 1px solid var(--border-subtle);
      background: var(--bg-card);
      color: var(--text-main);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s ease;
    }

    .pill-btn:hover {
      border-color: #8b5cf6;
      background: var(--bg-card-hover);
    }

    .content-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 8px 28px 28px;
    }

    .hero-banner {
      border-radius: 20px;
      padding: 24px 26px;
      background: linear-gradient(135deg, rgba(124, 58, 237, 0.28), rgba(236, 72, 153, 0.14), rgba(18, 18, 26, 0.85));
      border: 1px solid rgba(255, 255, 255, 0.09);
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
    }

    .hero-banner h1 {
      font-size: 24px;
      font-weight: 800;
      margin-bottom: 6px;
    }

    .hero-banner p {
      font-size: 13.5px;
      color: var(--text-sub);
    }

    .section-title {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
      gap: 16px;
      margin-bottom: 26px;
    }

    .playlist-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 13px;
      cursor: pointer;
      transition: transform 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
      position: relative;
    }

    .playlist-card:hover {
      transform: translateY(-4px);
      background: var(--bg-card-hover);
      border-color: rgba(139, 92, 246, 0.35);
      box-shadow: 0 12px 26px rgba(0, 0, 0, 0.32);
    }

    .card-art {
      width: 100%;
      aspect-ratio: 1 / 1;
      border-radius: 12px;
      margin-bottom: 11px;
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: flex-end;
      padding: 12px;
      color: #fff;
      font-weight: 800;
      font-size: 17px;
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28);
    }

    .card-play-fab {
      position: absolute;
      right: 10px;
      bottom: 10px;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: #7c3aed;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      box-shadow: 0 6px 16px rgba(124, 58, 237, 0.5);
      opacity: 0;
      transform: translateY(6px);
      transition: all 0.2s ease;
    }

    .playlist-card:hover .card-play-fab {
      opacity: 1;
      transform: translateY(0);
    }

    .card-name {
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 3px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .card-sub {
      font-size: 12px;
      color: var(--text-sub);
    }

    /* Track List */
    .track-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .track-row {
      display: grid;
      grid-template-columns: 36px 46px 1fr 180px 56px 42px;
      align-items: center;
      gap: 12px;
      padding: 8px 14px;
      border-radius: 12px;
      background: var(--bg-panel);
      border: 1px solid transparent;
      cursor: pointer;
      transition: all 0.16s ease;
    }

    .track-row:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-subtle);
    }

    .track-row.playing {
      background: rgba(124, 58, 237, 0.14);
      border-color: rgba(139, 92, 246, 0.36);
    }

    .track-num {
      font-size: 13px;
      color: var(--text-muted);
      text-align: center;
      font-weight: 600;
    }

    .track-row.playing .track-num {
      color: #a78bfa;
    }

    .track-thumb {
      width: 42px;
      height: 42px;
      border-radius: 9px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 800;
      font-size: 14px;
    }

    .track-meta {
      min-width: 0;
    }

    .track-title {
      font-size: 14px;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .track-artist {
      font-size: 12.5px;
      color: var(--text-sub);
      margin-top: 2px;
    }

    .track-album {
      font-size: 12.5px;
      color: var(--text-muted);
    }

    .track-dur {
      font-size: 12.5px;
      color: var(--text-sub);
      text-align: right;
    }

    .like-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 16px;
      cursor: pointer;
      transition: transform 0.15s ease, color 0.15s ease;
    }

    .like-btn.liked {
      color: #ec4899;
    }

    .like-btn:hover {
      transform: scale(1.18);
    }

    /* ======================================================================
       DIRECT BOTTOM-LEFT EXPANDING COVER PHOTO (#expandedCover)
       No modal window, no card frame, no backdrop dimming or white glow
       ====================================================================== */
    .expanded-artwork {
      position: fixed;
      left: 22px;
      bottom: 100px;
      width: 248px;
      height: 248px;
      border-radius: 12px;
      z-index: 60;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.55);
      border: 1px solid rgba(0, 0, 0, 0.35);
      cursor: pointer;
      transform-origin: bottom left;
      transform: translate(0, 82px) scale(0.24);
      opacity: 0;
      pointer-events: none;
      transition: transform 0.21s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.16s ease;
    }

    .expanded-artwork.open {
      transform: translate(0, 0) scale(1);
      opacity: 1;
      pointer-events: auto;
    }

    .expanded-artwork-badge {
      font-size: 46px;
      font-weight: 900;
      letter-spacing: -0.04em;
      text-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
    }

    .expanded-artwork-sub {
      margin-top: 8px;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(0, 0, 0, 0.28);
    }

    /* Bottom PlayerBar */
    .player-bar {
      height: 92px;
      background: var(--bg-bottom);
      border-top: 1px solid var(--border-subtle);
      padding: 0 22px;
      display: grid;
      grid-template-columns: 300px 1fr 260px;
      align-items: center;
      gap: 16px;
      z-index: 40;
      position: relative;
    }

    .bottom-left {
      display: flex;
      align-items: center;
      gap: 13px;
      min-width: 0;
    }

    .bottom-cover {
      width: 60px;
      height: 60px;
      border-radius: 12px;
      flex-shrink: 0;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 800;
      font-size: 18px;
      position: relative;
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.16);
      transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.18s ease;
    }

    .bottom-cover:hover {
      transform: scale(1.06);
      box-shadow: 0 8px 22px rgba(124, 58, 237, 0.45);
    }

    .bottom-cover-zoom-badge {
      position: absolute;
      inset: 0;
      border-radius: 12px;
      background: rgba(0, 0, 0, 0.42);
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: opacity 0.16s ease;
      font-size: 18px;
    }

    .bottom-cover:hover .bottom-cover-zoom-badge {
      opacity: 1;
    }

    .bottom-track-info {
      min-width: 0;
    }

    .bottom-title {
      font-size: 14px;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .bottom-artist {
      font-size: 12.5px;
      color: var(--text-sub);
      cursor: pointer;
      margin-top: 3px;
      display: inline-block;
    }

    .bottom-artist:hover {
      color: #a78bfa;
      text-decoration: underline;
    }

    .bottom-center {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      max-width: 560px;
      width: 100%;
      justify-self: center;
    }

    .transport-row {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .icon-btn {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      border: none;
      background: transparent;
      color: var(--text-sub);
      font-size: 15px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s ease;
    }

    .icon-btn:hover {
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.06);
    }

    .play-main-btn {
      width: 42px;
      height: 42px;
      border-radius: 21px;
      border: none;
      background: #7c3aed;
      color: #fff;
      font-size: 16px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 6px 18px rgba(124, 58, 237, 0.45);
      transition: transform 0.15s ease, background 0.15s ease;
    }

    .play-main-btn:hover {
      background: #8b5cf6;
      transform: scale(1.06);
    }

    .progress-row {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 11.5px;
      color: var(--text-muted);
      font-variant-numeric: tabular-nums;
    }

    input[type="range"] {
      -webkit-appearance: none;
      appearance: none;
      height: 5px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.14);
      outline: none;
      cursor: pointer;
      flex: 1;
    }

    body.light-theme input[type="range"] {
      background: rgba(15, 23, 42, 0.15);
    }

    input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 13px;
      height: 13px;
      border-radius: 50%;
      background: #8b5cf6;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
      cursor: pointer;
    }

    .bottom-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
    }
  </style>
</head>
<body>
  <div class="app-workspace">
    <!-- Left Sidebar -->
    <aside class="sidebar">
      <div class="brand-row">
        <div class="brand-title">
          <div class="brand-dot">✦</div>
          <span>Aurora</span>
        </div>
      </div>

      <button class="nav-btn active" onclick="switchTab('home', this)">
        <span>🏠</span>
        <span>Главная</span>
      </button>
      <button class="nav-btn" onclick="switchTab('likes', this)">
        <span>💜</span>
        <span>Любимые треки</span>
      </button>
      <button class="nav-btn" onclick="switchTab('playlists', this)">
        <span>💿</span>
        <span>Медиатека</span>
      </button>

      <div class="sidebar-section-label">Плейлисты</div>
      <button class="nav-btn" onclick="filterPlaylist('Ночной драйв')">
        <span>🌌</span>
        <span>Ночной драйв</span>
      </button>
      <button class="nav-btn" onclick="filterPlaylist('Synthwave 2084')">
        <span>⚡</span>
        <span>Synthwave 2084</span>
      </button>
      <button class="nav-btn" onclick="filterPlaylist('Lo-Fi Focus')">
        <span>☕</span>
        <span>Lo-Fi Focus</span>
      </button>

      <div class="sidebar-footer">
        <div class="hint-badge">
          💡 <strong>Раскрытие обложки:</strong> нажмите на фото трека в левом нижнем углу — фото плавно расширится прямо внизу без новых окон и без свечения.
        </div>
      </div>
    </aside>

    <!-- Main View Stack -->
    <main class="main-stack">
      <header class="topbar">
        <div class="search-box">
          <span>🔍</span>
          <input type="text" id="searchInput" placeholder="Поиск треков, артистов, альбомов..." oninput="renderTracks()" />
        </div>
        <div class="topbar-actions">
          <button class="pill-btn" onclick="toggleCoverPopup()">🖼️ Окно обложки</button>
          <button class="pill-btn" onclick="toggleTheme()" id="themeBtn">🌙 Тёмная тема</button>
        </div>
      </header>

      <div class="content-scroll">
        <div class="hero-banner" id="heroBanner">
          <div>
            <h1 id="pageHeading">Главная</h1>
            <p id="pageSubheading">Нажмите на миниатюру обложки на нижней панели плеера для плавного открытия окна</p>
          </div>
          <button class="pill-btn" onclick="toggleCoverPopup()" style="background:#7c3aed;color:#fff;border:none;padding:11px 18px;">
            Показать обложку ↗
          </button>
        </div>

        <div class="section-title">
          <span>Быстрый выбор</span>
        </div>
        <div class="cards-grid" id="cardsGrid"></div>

        <div class="section-title">
          <span id="tracksTitle">Треки</span>
        </div>
        <div class="track-list" id="trackList"></div>
      </div>

      <!-- DIRECT BOTTOM-LEFT EXPANDING COVER PHOTO (#expandedCover) -->
      <div class="expanded-artwork" id="expandedCover" onclick="closeCoverPopup()" title="Свернуть обложку (Esc)">
        <div class="expanded-artwork-badge" id="expandedBadge">AU</div>
        <div class="expanded-artwork-sub">Нажмите, чтобы свернуть</div>
      </div>
    </main>
  </div>

  <!-- Bottom PlayerBar -->
  <footer class="player-bar">
    <div class="bottom-left">
      <div class="bottom-cover" id="bottomCover" onclick="toggleCoverPopup()" title="Нажмите, чтобы открыть компактное окно обложки">
        <span id="bottomCoverInitials">MC</span>
        <div class="bottom-cover-zoom-badge">⤢</div>
      </div>
      <div class="bottom-track-info">
        <div class="bottom-title" id="bottomTitle">Midnight City Lights</div>
        <div class="bottom-artist" id="bottomArtist" onclick="openArtistFromPopup()">Aurora Synth</div>
      </div>
    </div>

    <div class="bottom-center">
      <div class="transport-row">
        <button class="icon-btn" onclick="prevTrack()" title="Предыдущий">⏮</button>
        <button class="play-main-btn" id="playBtn" onclick="togglePlay()" title="Воспроизвести / Пауза">▶</button>
        <button class="icon-btn" onclick="nextTrack()" title="Следующий">⏭</button>
      </div>
      <div class="progress-row">
        <span id="curTime">01:14</span>
        <input type="range" id="seekSlider" min="0" max="100" value="38" oninput="updateSeek(this.value)" />
        <span id="totalTime">03:42</span>
      </div>
    </div>

    <div class="bottom-right">
      <span style="font-size:14px;color:var(--text-sub);">🔊</span>
      <input type="range" min="0" max="100" value="80" style="max-width:110px;" />
    </div>
  </footer>

  <script>
    const TRACKS = [
      {
        id: 1,
        title: "Midnight City Lights",
        artist: "Aurora Synth",
        album: "Ночной драйв",
        duration: "03:42",
        initials: "MC",
        gradient: "linear-gradient(135deg, #7c3aed, #ec4899)",
        glow: "rgba(124, 58, 237, 0.42)",
        liked: true
      },
      {
        id: 2,
        title: "velvet horizon (slowed)",
        artist: "Kaito & Nori",
        album: "Lo-Fi Focus",
        duration: "02:58",
        initials: "VH",
        gradient: "linear-gradient(135deg, #0ea5e9, #6366f1)",
        glow: "rgba(14, 165, 233, 0.40)",
        liked: true
      },
      {
        id: 3,
        title: "Cyberpunk Raindrops",
        artist: "N3ON PULSE",
        album: "Synthwave 2084",
        duration: "04:15",
        initials: "CR",
        gradient: "linear-gradient(135deg, #f43f5e, #fb923c)",
        glow: "rgba(244, 63, 94, 0.40)",
        liked: false
      },
      {
        id: 4,
        title: "Northern Starlight",
        artist: "Elysian Fields",
        album: "Ночной драйв",
        duration: "03:19",
        initials: "NS",
        gradient: "linear-gradient(135deg, #10b981, #059669)",
        glow: "rgba(16, 185, 129, 0.38)",
        liked: true
      },
      {
        id: 5,
        title: "Deep Space Echoes",
        artist: "Solaris Project",
        album: "Synthwave 2084",
        duration: "05:04",
        initials: "DS",
        gradient: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
        glow: "rgba(139, 92, 246, 0.42)",
        liked: false
      }
    ];

    let currentTrackIndex = 0;
    let isPlaying = false;
    let currentTab = "home";
    let activeFilter = null;

    function renderCards() {
      const grid = document.getElementById("cardsGrid");
      grid.innerHTML = TRACKS.slice(0, 4).map((t, idx) => `
        <div class="playlist-card" onclick="selectTrack(${idx})">
          <div class="card-art" style="background: ${t.gradient}">
            <span>${t.initials}</span>
            <div class="card-play-fab">▶</div>
          </div>
          <div class="card-name">${t.title}</div>
          <div class="card-sub">${t.artist}</div>
        </div>
      `).join("");
    }

    function renderTracks() {
      const q = document.getElementById("searchInput").value.trim().toLowerCase();
      const list = document.getElementById("trackList");
      const filtered = TRACKS.filter(t => {
        if (currentTab === "likes" && !t.liked) return false;
        if (activeFilter && t.album !== activeFilter) return false;
        if (q && !(t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q) || t.album.toLowerCase().includes(q))) {
          return false;
        }
        return true;
      });

      list.innerHTML = filtered.map((t, i) => {
        const realIdx = TRACKS.findIndex(x => x.id === t.id);
        const playingClass = realIdx === currentTrackIndex ? "playing" : "";
        return `
          <div class="track-row ${playingClass}" onclick="selectTrack(${realIdx})">
            <div class="track-num">${realIdx === currentTrackIndex && isPlaying ? "▶" : i + 1}</div>
            <div class="track-thumb" style="background:${t.gradient}">${t.initials}</div>
            <div class="track-meta">
              <div class="track-title">${t.title}</div>
              <div class="track-artist">${t.artist}</div>
            </div>
            <div class="track-album">${t.album}</div>
            <div class="track-dur">${t.duration}</div>
            <button class="like-btn ${t.liked ? 'liked' : ''}" onclick="toggleLike(event, ${realIdx})">♥</button>
          </div>
        `;
      }).join("");
    }

    function syncPlayerUI() {
      const t = TRACKS[currentTrackIndex];
      const bottomCover = document.getElementById("bottomCover");
      bottomCover.style.background = t.gradient;
      document.getElementById("bottomCoverInitials").textContent = t.initials;
      document.getElementById("bottomTitle").textContent = t.title;
      document.getElementById("bottomArtist").textContent = t.artist;
      document.getElementById("totalTime").textContent = t.duration;

      // Sync bottom-left expanding cover photo
      const expCover = document.getElementById("expandedCover");
      expCover.style.background = t.gradient;
      document.getElementById("expandedBadge").textContent = t.initials;
      renderTracks();
    }

    function selectTrack(idx) {
      currentTrackIndex = idx;
      isPlaying = true;
      document.getElementById("playBtn").textContent = "⏸";
      syncPlayerUI();
    }

    function togglePlay() {
      isPlaying = !isPlaying;
      document.getElementById("playBtn").textContent = isPlaying ? "⏸" : "▶";
      renderTracks();
    }

    function prevTrack() {
      currentTrackIndex = (currentTrackIndex - 1 + TRACKS.length) % TRACKS.length;
      syncPlayerUI();
    }

    function nextTrack() {
      currentTrackIndex = (currentTrackIndex + 1) % TRACKS.length;
      syncPlayerUI();
    }

    function toggleLike(e, idx) {
      e.stopPropagation();
      TRACKS[idx].liked = !TRACKS[idx].liked;
      renderTracks();
    }

    function toggleCoverPopup() {
      const expCover = document.getElementById("expandedCover");
      expCover.classList.toggle("open");
    }

    function closeCoverPopup() {
      document.getElementById("expandedCover").classList.remove("open");
    }

    function openArtistFromPopup() {
      const t = TRACKS[currentTrackIndex];
      closeCoverPopup();
      document.getElementById("searchInput").value = t.artist;
      renderTracks();
    }

    function switchTab(tab, btn) {
      currentTab = tab;
      activeFilter = null;
      document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("pageHeading").textContent =
        tab === "likes" ? "Любимые треки" : tab === "playlists" ? "Медиатека" : "Главная";
      renderTracks();
    }

    function filterPlaylist(name) {
      activeFilter = name;
      document.getElementById("pageHeading").textContent = name;
      renderTracks();
    }

    function toggleTheme() {
      document.body.classList.toggle("light-theme");
      const isLight = document.body.classList.contains("light-theme");
      document.getElementById("themeBtn").textContent = isLight ? "☀️ Светлая тема" : "🌙 Тёмная тема";
    }

    function updateSeek(val) {
      const sec = Math.floor((val / 100) * 222);
      const m = String(Math.floor(sec / 60)).padStart(2, "0");
      const s = String(sec % 60).padStart(2, "0");
      document.getElementById("curTime").textContent = `${m}:${s}`;
    }

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeCoverPopup();
      }
    });

    renderCards();
    syncPlayerUI();
  </script>
</body>
</html>
"""


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps({
                "status": "ok",
                "player_file": PLAYER_FILE.name,
                "exists": PLAYER_FILE.exists(),
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = HTML_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 3000), PreviewHandler)
    print("Aurora interactive preview server running on http://0.0.0.0:3000", flush=True)
    server.serve_forever()
