/**
 * Chat_Room — app.js
 * =================
 * Handles all client-side logic:
 *   - Session (username entry)
 *   - REST API calls  (rooms CRUD, history)
 *   - WebSocket connection lifecycle & auto-reconnect
 *   - Message rendering (optimistic + server-confirmed)
 *   - UI helpers (toast, shake, modal, room list)
 */

// ── Config ──────────────────────────────────────────────────────────────────
// For deployment: replace PROD_API_URL with your actual Render URL later.
const PROD_API_URL = "https://chat-app-room-3coz.onrender.com"; // <-- UPDATE ME

// Simple host check to allow running locally without breaking production
const isDev = location.hostname === "localhost" || location.hostname === "127.0.0.1";

const API_BASE = isDev 
  ? `${location.protocol}//${location.host}` 
  : PROD_API_URL;

const WS_BASE  = isDev 
  ? (location.protocol === 'https:' ? `wss://${location.host}` : `ws://${location.host}`) 
  : PROD_API_URL.replace("http", "ws"); // Covers http->ws and https->wss

// ── State ────────────────────────────────────────────────────────────────────
let currentUser    = '';
let currentRoom    = null;
let socket         = null;       // active WebSocket
let reconnectTimer = null;
let reconnectDelay = 1000;
let pendingMsgIds  = new Set();  // tracks optimistically-rendered own messages

// ── REST Helpers ─────────────────────────────────────────────────────────────

/**
 * Thin fetch wrapper. Throws on non-2xx responses.
 * @param {string} path
 * @param {string} method
 * @param {object|null} body
 */
async function apiFetch(path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  const res  = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 204) return null;

  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ── Session ───────────────────────────────────────────────────────────────────

/** Called when the user submits the login card. */
function startSession() {
  const val = document.getElementById('usernameInput').value.trim();
  if (!val) { shake('usernameInput'); return; }

  currentUser = val.charAt(0).toUpperCase() + val.slice(1);
  document.getElementById('userNameEl').textContent = currentUser;
  document.getElementById('avatarEl').textContent   = currentUser[0].toUpperCase();
  document.getElementById('usernameScreen').style.display = 'none';

  loadRooms();
}

document.getElementById('usernameInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') startSession();
});

// ── Rooms ─────────────────────────────────────────────────────────────────────

/** Fetches room list from the API and re-renders the sidebar list. */
async function loadRooms() {
  const list = document.getElementById('roomsList');
  list.innerHTML = '<div class="loader"><div class="spinner"></div> Loading rooms…</div>';

  try {
    const rooms = await apiFetch('/api/rooms');
    renderRooms(rooms);
  } catch (e) {
    list.innerHTML = `<div style="padding:12px 10px;color:var(--red);font-size:12px;font-family:var(--mono);">⚠ ${escHtml(e.message)}</div>`;
  }
}

/**
 * Renders the sidebar room list.
 * @param {string[]} names
 */
function renderRooms(names) {
  const list = document.getElementById('roomsList');

  if (!names.length) {
    list.innerHTML = `
      <div style="padding:16px 10px;color:var(--muted);font-size:12.5px;text-align:center;line-height:1.7;">
        No rooms yet.<br/>
        <span style="color:var(--accent);cursor:pointer;" onclick="openNewRoom()">Create one now →</span>
      </div>`;
    return;
  }

  list.innerHTML = names.map(n => `
    <div
      class="room-item ${currentRoom === n ? 'active' : ''}"
      id="room-${n}"
      onclick="joinRoom('${escAttr(n)}')"
      role="button"
      tabindex="0"
      aria-label="Join room ${n.toLowerCase()}"
    >
      <span class="room-hash">#</span>
      <span class="room-label">${escHtml(n.toLowerCase())}</span>
      <button class="room-delete" onclick="deleteRoom(event,'${escAttr(n)}')" title="Delete room" aria-label="Delete ${n}">✕</button>
    </div>
  `).join('');

  // keyboard navigation for room items
  list.querySelectorAll('.room-item').forEach(el => {
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') el.click();
    });
  });
}

/** Creates a new room via the API. */
async function createRoom() {
  const val = document.getElementById('newRoomInput').value.trim().toUpperCase();
  if (!val) { shake('newRoomInput'); return; }

  try {
    await apiFetch('/api/rooms', 'POST', { name: val });
    closeModal('newRoomOverlay');
    document.getElementById('newRoomInput').value = '';
    toast(`Room #${val.toLowerCase()} created`, 'success');
    await loadRooms();
    joinRoom(val);
  } catch (e) {
    toast(e.message.toLowerCase().includes('already') ? 'Room already exists' : e.message, 'error');
  }
}

/**
 * Deletes a room and all its messages.
 * @param {MouseEvent} e
 * @param {string} name
 */
async function deleteRoom(e, name) {
  e.stopPropagation();
  if (!confirm(`Delete room #${name.toLowerCase()}?\nAll messages will be permanently lost.`)) return;

  try {
    await apiFetch(`/api/rooms/${encodeURIComponent(name)}`, 'DELETE');
    toast(`Room #${name.toLowerCase()} deleted`, 'success');

    if (currentRoom === name) {
      currentRoom = null;
      closeSocket();
      showWelcome();
    }

    await loadRooms();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ── Chat — Room Joining ───────────────────────────────────────────────────────

/** Leaves the current room and goes back to the mobile sidebar */
function leaveRoom() {
  currentRoom = null;
  closeSocket();
  document.body.classList.remove('room-active');
  setActiveRoom(null);
  showWelcome();
}

/**
 * Switches to the given room: renders UI, loads history, opens WebSocket.
 * @param {string} name  Room name (uppercase)
 */
function joinRoom(name) {
  if (currentRoom === name) return;

  document.body.classList.add('room-active');

  currentRoom = name;
  closeSocket();
  pendingMsgIds.clear();

  renderChatUI(name);
  loadHistory(name);
  connectWS(name);
  setActiveRoom(name);
}

/** Marks only the given room as active in the sidebar. */
function setActiveRoom(name) {
  document.querySelectorAll('.room-item').forEach(el => {
    el.classList.toggle('active', el.id === `room-${name}`);
  });
}

/** Restores the welcome (idle) screen in the main area. */
function showWelcome() {
  document.getElementById('mainArea').innerHTML = `
    <div class="welcome" id="welcomeScreen">
      <div class="welcome-icon">💬</div>
      <h2>Select a room to start</h2>
      <p>Choose a channel from the sidebar or create a new one to begin messaging.</p>
      <div class="welcome-hint">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <line x1="6" y1="1" x2="6" y2="11"/><line x1="1" y1="6" x2="11" y2="6"/>
        </svg>
        Click + to create a room
      </div>
    </div>`;
}

/**
 * Renders the full chat UI (header + messages area + input) for a room.
 * @param {string} name
 */
function renderChatUI(name) {
  document.getElementById('mainArea').innerHTML = `
    <div class="chat-header">
      <button class="mobile-back-btn" onclick="leaveRoom()" aria-label="Back to rooms">
        <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>
      <div class="chat-header-left">
        <div class="chat-header-title">
          <span class="hash">#</span>${escHtml(name.toLowerCase())}
        </div>
        <div class="chat-header-meta">Corporate channel · All members</div>
      </div>
      <div class="header-badges">
        <div class="msg-count-badge" id="msgCount">— msgs</div>
        <div class="ws-status connecting" id="wsStatus">
          <div class="ws-dot"></div> Connecting
        </div>
      </div>
    </div>

    <div class="messages-area" id="messagesArea">
      <div class="loader"><div class="spinner"></div> Loading history…</div>
    </div>

    <div class="input-area">
      <div class="input-row">
        <textarea
          class="msg-input"
          id="msgInput"
          placeholder="Message #${escHtml(name.toLowerCase())}…"
          rows="1"
          aria-label="Message input"
        ></textarea>
        <button class="send-btn" onclick="sendMessage()" aria-label="Send message">
          <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
        </button>
      </div>
      <div class="input-hint">
        <span class="kbd">Enter</span> send &nbsp;·&nbsp; <span class="kbd">Shift+Enter</span> new line
      </div>
    </div>
  `;

  const input = document.getElementById('msgInput');

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
}

// ── Chat — History ────────────────────────────────────────────────────────────

/**
 * Loads and renders the message history for a room.
 * @param {string} room
 */
async function loadHistory(room) {
  try {
    const msgs = await apiFetch(`/api/rooms/${encodeURIComponent(room)}/history`);
    const area = document.getElementById('messagesArea');
    if (!area) return;

    if (!msgs || !msgs.length) {
      area.innerHTML = `
        <div class="empty-room">
          <span class="empty-icon">👋</span>
          <p>No messages yet.<br/>Be the first to say hello!</p>
        </div>`;
      return;
    }

    area.innerHTML = '';
    updateMsgCount(msgs.length);
    renderMessages(msgs, area, true);
  } catch (e) {
    toast('Failed to load history: ' + e.message, 'error');
  }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

/**
 * Opens a WebSocket connection to the server for the given room.
 * Handles auto-reconnect with exponential backoff.
 * @param {string} room
 */
function connectWS(room) {
  if (!currentUser) return;
  clearTimeout(reconnectTimer);

  const url = `${WS_BASE}/ws/${encodeURIComponent(room)}/${encodeURIComponent(currentUser)}`;
  socket = new WebSocket(url);

  setWsStatus('connecting');

  socket.addEventListener('open', () => {
    reconnectDelay = 1000;
    setWsStatus('connected');
  });

  socket.addEventListener('message', ev => {
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }

    if (data.type !== 'message') return;

    const area = document.getElementById('messagesArea');
    if (!area || data.room !== currentRoom) return;

    // clear empty-room placeholder
    const empty = area.querySelector('.empty-room');
    if (empty) area.innerHTML = '';

    const isOwn  = data.username.toLowerCase() === currentUser.toLowerCase();
    const msgKey = `${data.username}|${data.text}|${data.room}`;

    // suppress echo for messages we already showed optimistically
    if (isOwn && pendingMsgIds.has(msgKey)) {
      pendingMsgIds.delete(msgKey);
      return;
    }

    renderMessages([data], area, false);
    bumpMsgCount(1);
  });

  socket.addEventListener('close', () => {
    setWsStatus('disconnected');
    if (currentRoom === room) {
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
        connectWS(room);
      }, reconnectDelay);
    }
  });

  socket.addEventListener('error', () => {
    setWsStatus('disconnected');
  });
}

/** Closes the active WebSocket without triggering auto-reconnect. */
function closeSocket() {
  clearTimeout(reconnectTimer);
  if (socket) {
    socket.onclose = null; // prevent reconnect loop
    socket.close();
    socket = null;
  }
}

/**
 * Updates the WebSocket status badge in the chat header.
 * @param {'connected'|'connecting'|'disconnected'} state
 */
function setWsStatus(state) {
  const el = document.getElementById('wsStatus');
  if (!el) return;
  el.className = `ws-status ${state}`;
  const labels = { connected: 'Live', connecting: 'Connecting…', disconnected: 'Reconnecting…' };
  el.innerHTML = `<div class="ws-dot"></div> ${labels[state] || state}`;
}

// ── Chat — Send Message ───────────────────────────────────────────────────────

/** Reads the input, renders optimistically, and sends via WebSocket. */
function sendMessage() {
  const input = document.getElementById('msgInput');
  if (!input) return;

  const text = input.value.trim();
  if (!text || !currentRoom || !socket || socket.readyState !== WebSocket.OPEN) return;

  input.value = '';
  input.style.height = 'auto';

  // Optimistic render — show message immediately
  const now    = new Date().toISOString();
  const msgKey = `${currentUser}|${text}|${currentRoom}`;
  pendingMsgIds.add(msgKey);
  setTimeout(() => pendingMsgIds.delete(msgKey), 5000); // safety TTL

  const area = document.getElementById('messagesArea');
  if (area) {
    const empty = area.querySelector('.empty-room');
    if (empty) area.innerHTML = '';
    renderMessages([{ username: currentUser, text, timestamp: now }], area, false);
    bumpMsgCount(1);
  }

  socket.send(JSON.stringify({ type: 'message', text }));
  input.focus();
}

// ── Chat — Render ─────────────────────────────────────────────────────────────

/** Generate a deterministic color from a username */
const SENDER_COLORS = ['#f87171', '#fbbf24', '#34d399', '#38bdf8', '#c084fc', '#f472b6'];
function getColorForName(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return SENDER_COLORS[Math.abs(hash) % SENDER_COLORS.length];
}

/**
 * Appends an array of messages to the messages container.
 * Groups messages by date with day-divider headers.
 *
 * @param {object[]} msgs         Array of {username, text, timestamp}
 * @param {HTMLElement} area      The messages container element
 * @param {boolean} scrollToBottom  Whether to force-scroll to the bottom
 */
function renderMessages(msgs, area, scrollToBottom) {
  const frag   = document.createDocumentFragment();
  let lastDate = area.dataset.lastDate || null;

  msgs.forEach(m => {
    const d       = new Date(m.timestamp);
    const dateStr = d.toLocaleDateString('en-AU', { weekday: 'long', month: 'long', day: 'numeric' });

    if (dateStr !== lastDate) {
      lastDate = dateStr;
      const divider = document.createElement('div');
      divider.className   = 'day-divider';
      divider.textContent = dateStr;
      frag.appendChild(divider);
    }

    const isOwn   = m.username.toLowerCase() === currentUser.toLowerCase();
    const timeStr = d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' });
    const colorStyle = isOwn ? '' : `style="color: ${getColorForName(m.username)}"`;

    const wrapper = document.createElement('div');
    wrapper.className = isOwn ? 'msg-own-row' : 'msg-group';
    wrapper.innerHTML = `
      <div class="msg-header">
        <span class="msg-sender" ${colorStyle}>${escHtml(m.username)}</span>
        <span class="msg-time">${timeStr}</span>
      </div>
      <div class="msg-bubble ${isOwn ? 'own' : ''}">${escHtml(m.text)}</div>
    `;
    frag.appendChild(wrapper);
  });

  area.dataset.lastDate = lastDate;
  area.appendChild(frag);

  if (scrollToBottom) {
    area.scrollTop = area.scrollHeight;
  } else {
    const nearBottom = area.scrollHeight - area.scrollTop - area.clientHeight < 140;
    if (nearBottom) area.scrollTop = area.scrollHeight;
  }
}

// ── Message Count ─────────────────────────────────────────────────────────────

/** Sets the message count badge to an absolute value. */
function updateMsgCount(n) {
  const el = document.getElementById('msgCount');
  if (el) el.textContent = `${n} msg${n !== 1 ? 's' : ''}`;
}

/** Increments the message count badge by `by`. */
function bumpMsgCount(by) {
  const el = document.getElementById('msgCount');
  if (!el) return;
  const cur = parseInt(el.textContent) || 0;
  updateMsgCount(cur + by);
}

// ── Modal Helpers ─────────────────────────────────────────────────────────────

/** Opens the "Create new room" modal and focuses the input. */
function openNewRoom() {
  document.getElementById('newRoomOverlay').classList.add('open');
  setTimeout(() => document.getElementById('newRoomInput').focus(), 120);
}

/** Closes a modal by removing the 'open' class. */
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// Modal keyboard & backdrop events
document.getElementById('newRoomInput').addEventListener('keydown', e => {
  if (e.key === 'Enter')  createRoom();
  if (e.key === 'Escape') closeModal('newRoomOverlay');
});

document.getElementById('newRoomOverlay').addEventListener('click', e => {
  if (e.target === document.getElementById('newRoomOverlay')) closeModal('newRoomOverlay');
});

// ── Toast Notifications ───────────────────────────────────────────────────────

/**
 * Shows a temporary toast notification.
 * @param {string} msg
 * @param {'success'|'error'} type
 */
function toast(msg, type = 'success') {
  const area = document.getElementById('toastArea');
  const el   = document.createElement('div');
  el.className = `toast ${type}`;

  const icon = type === 'success' ? '✓' : '⚠';
  el.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-msg">${escHtml(msg)}</span>`;
  area.appendChild(el);

  setTimeout(() => {
    el.style.opacity    = '0';
    el.style.transition = 'opacity .3s';
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

// ── DOM Utilities ─────────────────────────────────────────────────────────────

/**
 * Briefly highlights an input in red and plays a shake animation.
 * @param {string} id  Element ID
 */
function shake(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('shake');
  el.style.borderColor = 'var(--red)';
  void el.offsetWidth; // force reflow to restart animation
  el.classList.add('shake');
  setTimeout(() => {
    el.classList.remove('shake');
    el.style.borderColor = '';
  }, 500);
}

/**
 * Escapes special HTML characters to prevent XSS.
 * @param {string} s
 * @returns {string}
 */
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Escapes single quotes for use inside HTML attribute values.
 * @param {string} s
 * @returns {string}
 */
function escAttr(s) {
  return String(s).replace(/'/g, "\\'");
}
