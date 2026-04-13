/**
 * app.js — LocalChat frontend (vanilla JS, no deps)
 * Connects to the Flask API for 100% offline AI document Q&A.
 * Uses fetch + ReadableStream for streaming SSE answers.
 */
'use strict';

const API           = '/api';
const TOAST_TTL     = 4500;
const OLLAMA_POLL   = 15000;   // re-check Ollama status every 15 s

// ── State ──────────────────────────────────────────────────────
const state = {
  documentId:   null,
  documentName: null,
  fileType:     null,   // "pdf" | "image"
  chunks:       null,
  isUploading:  false,
  isAsking:     false,
  selectedFile: null,
  abortCtrl:    null,   // AbortController for in-flight fetch
  history:      [],     // multi-turn conversation history
  activeProvider: null, // { provider, name, model }
};

// ── DOM ────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const dom = {
  // Header
  providerBadge: $('providerBadge'),
  noProviderBar: $('noProviderBar'),
  ollamaBadge:  $('ollamaBadge'),
  ollamaDot:    $('ollamaDot'),
  ollamaText:   $('ollamaText'),
  hintProvider: $('hintProvider'),

  // Upload
  dropZone:     $('dropZone'),
  fileInput:    $('fileInput'),
  filePreview:  $('filePreview'),
  fileTypeBadge:$('fileTypeBadge'),
  previewName:  $('previewName'),
  previewSize:  $('previewSize'),
  removeFileBtn:$('removeFileBtn'),
  uploadBtn:    $('uploadBtn'),
  uploadBtnText:$('uploadBtnText'),
  progressWrap: $('progressWrap'),
  progressBar:  $('progressBar'),
  progressLabel:$('progressLabel'),

  // Active doc
  activeDocPanel: $('activeDocPanel'),
  activeDocTypeIcon: $('activeDocTypeIcon'),
  activeDocName:  $('activeDocName'),
  activeDocMeta:  $('activeDocMeta'),
  newDocBtn:      $('newDocBtn'),

  // Doc list
  docList:      $('docList'),
  refreshBtn:   $('refreshBtn'),

  // Ollama info panel
  ollamaRunning: $('ollamaRunning'),
  ollamaLlm:     $('ollamaLlm'),
  ollamaEmbed:   $('ollamaEmbed'),
  ollamaError:   $('ollamaError'),

  // Chat
  chatEmpty:    $('chatEmpty'),
  chatMessages: $('chatMessages'),
  chatBar:      $('chatBar'),
  questionInput:$('questionInput'),
  sendBtn:      $('sendBtn'),
  stopBtn:      $('stopBtn'),

  toastContainer: $('toastContainer'),
};

// ── Active provider ────────────────────────────────────────────

async function fetchActiveProvider() {
  try {
    const res  = await fetch(`${API}/active-provider`, { signal: AbortSignal.timeout(4000) });
    const data = await res.json();
    state.activeProvider = data.provider ? data : null;
    updateProviderBadge();
  } catch { /* ignore */ }
}

function updateProviderBadge() {
  const p = state.activeProvider;
  if (!p || !p.provider) {
    dom.providerBadge?.classList.add('hidden');
    dom.noProviderBar?.classList.remove('hidden');
    if (dom.hintProvider) dom.hintProvider.textContent = 'AI';
    return;
  }
  dom.noProviderBar?.classList.add('hidden');
  if (dom.providerBadge) {
    dom.providerBadge.textContent = `${p.name} · ${p.model}`;
    dom.providerBadge.classList.remove('hidden');
  }
  if (dom.hintProvider) dom.hintProvider.textContent = p.name;
}

// ── Utility ────────────────────────────────────────────────────
const fmtSize = b => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(2)} MB`;
const nowStr  = () => new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
const shortId = id => id ? id.slice(0,8)+'...' : '-';
const esc     = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const nl2br   = s => esc(s).replace(/\n/g,'<br>');
const sleep   = ms => new Promise(r => setTimeout(r, ms));

// ── Toast ──────────────────────────────────────────────────────
const ICONS = {success:'✅', error:'❌', info:'💡', warn:'⚠️'};

function toast(msg, type = 'info', ttl = TOAST_TTL) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${ICONS[type]||'💬'}</span><span class="toast-msg">${esc(msg)}</span>`;
  dom.toastContainer.appendChild(el);
  const rm = () => { el.classList.add('removing'); setTimeout(() => el.remove(), 240); };
  const tid = setTimeout(rm, ttl);
  el.addEventListener('click', () => { clearTimeout(tid); rm(); });
}

// ── Ollama status ──────────────────────────────────────────────

async function checkOllama() {
  try {
    const res  = await fetch(`${API}/ollama-status`, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();

    const ready = data.ollama_running && data.llm_model && data.embed_model;
    const partial = data.ollama_running && (!data.llm_model || !data.embed_model);

    dom.ollamaBadge.className = `ollama-badge ${ready ? 'ready' : partial ? 'warn' : 'error'}`;
    dom.ollamaText.textContent = ready ? 'Ollama ready' : partial ? 'Model missing' : 'Ollama offline';

    // Info panel
    dom.ollamaRunning.textContent = data.ollama_running ? 'Running' : 'Not running';
    dom.ollamaRunning.className   = `ollama-val ${data.ollama_running ? 'ok' : 'err'}`;
    dom.ollamaLlm.textContent     = data.llm_model ? data.llm_model_name : `${data.llm_model_name} (missing)`;
    dom.ollamaLlm.className       = `ollama-val ${data.llm_model ? 'ok' : 'err'}`;
    dom.ollamaEmbed.textContent   = data.embed_model ? data.embed_model_name : `${data.embed_model_name} (missing)`;
    dom.ollamaEmbed.className     = `ollama-val ${data.embed_model ? 'ok' : 'err'}`;

    if (data.errors && data.errors.length) {
      dom.ollamaError.innerHTML = data.errors.map(e => `<div>${esc(e)}</div>`).join('');
      dom.ollamaError.classList.remove('hidden');
    } else {
      dom.ollamaError.classList.add('hidden');
    }
  } catch {
    dom.ollamaBadge.className   = 'ollama-badge error';
    dom.ollamaText.textContent  = 'Ollama offline';
    dom.ollamaRunning.textContent = 'Not running';
    dom.ollamaRunning.className   = 'ollama-val err';
  }
}

// ── File handling ──────────────────────────────────────────────

const IMAGE_EXTS = new Set(['png','jpg','jpeg','tiff','tif','bmp','webp']);

function getFileType(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return IMAGE_EXTS.has(ext) ? 'image' : 'pdf';
}

function handleFileSelect(file) {
  if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  const allowed = new Set(['pdf','png','jpg','jpeg','tiff','tif','bmp','webp']);
  if (!allowed.has(ext)) {
    toast(`File type .${ext} is not supported.`, 'error');
    return;
  }
  state.selectedFile = file;
  const ft = getFileType(file.name);
  dom.fileTypeBadge.textContent = ft.toUpperCase();
  dom.previewName.textContent   = file.name;
  dom.previewSize.textContent   = fmtSize(file.size);
  dom.filePreview.classList.remove('hidden');
  dom.uploadBtn.disabled = false;
}

function clearFile() {
  state.selectedFile = null;
  dom.fileInput.value = '';
  dom.filePreview.classList.add('hidden');
  dom.uploadBtn.disabled = true;
}

dom.dropZone.addEventListener('click', () => dom.fileInput.click());
dom.dropZone.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); dom.fileInput.click(); }
});
dom.fileInput.addEventListener('change', e => handleFileSelect(e.target.files[0]));
dom.removeFileBtn.addEventListener('click', e => { e.stopPropagation(); clearFile(); });

dom.dropZone.addEventListener('dragover',  e => { e.preventDefault(); dom.dropZone.classList.add('over'); });
dom.dropZone.addEventListener('dragleave', () => dom.dropZone.classList.remove('over'));
dom.dropZone.addEventListener('drop', e => {
  e.preventDefault(); dom.dropZone.classList.remove('over');
  handleFileSelect(e.dataTransfer.files[0]);
});

// ── Upload ─────────────────────────────────────────────────────

function setProgress(pct, label) {
  dom.progressBar.style.width  = pct + '%';
  dom.progressLabel.textContent = label;
}

async function uploadDocument() {
  if (!state.selectedFile || state.isUploading) return;
  state.isUploading       = true;
  dom.uploadBtn.disabled  = true;
  dom.uploadBtnText.textContent = 'Uploading...';
  dom.progressWrap.classList.remove('hidden');
  setProgress(10, 'Uploading...');

  const form = new FormData();
  form.append('file', state.selectedFile);

  try {
    setProgress(30, 'Sending to server...');
    const res  = await fetch(`${API}/upload`, { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    setProgress(80, 'Embedding with nomic-embed-text...');
    await sleep(200);
    setProgress(100, 'Done!');
    await sleep(400);

    state.documentId   = data.document_id;
    state.documentName = state.selectedFile.name;
    state.fileType     = data.file_type;
    state.chunks       = data.chunks;

    onDocumentReady();
    toast(`"${data.filename}" indexed — ${data.chunks} chunks`, 'success');
    await fetchDocList();

  } catch (err) {
    toast(err.message, 'error', 7000);
    setProgress(0, '');
    dom.progressWrap.classList.add('hidden');
  } finally {
    state.isUploading = false;
    dom.uploadBtn.disabled  = !state.selectedFile;
    dom.uploadBtnText.textContent = 'Upload & Process';
  }
}

dom.uploadBtn.addEventListener('click', uploadDocument);

function onDocumentReady() {
  const icon = state.fileType === 'image' ? '🖼️' : '📄';
  dom.activeDocTypeIcon.textContent = icon;
  dom.activeDocName.textContent     = state.documentName;
  dom.activeDocMeta.textContent     = `${shortId(state.documentId)} · ${state.chunks} chunks · ${state.fileType}`;
  dom.activeDocPanel.classList.remove('hidden');

  dom.questionInput.placeholder = `Ask about "${state.documentName}", or ask anything...`;

  dom.chatEmpty.style.display    = 'none';
  dom.chatMessages.style.display = 'flex';

  state.history = [];
  addSystemMsg(`Document ready (${state.chunks} chunks). Ask anything!`);
  dom.questionInput.focus();
  clearFile();
  dom.progressWrap.classList.add('hidden');
  dom.progressBar.style.width = '0%';
}

dom.newDocBtn.addEventListener('click', () => {
  state.documentId   = null;
  state.documentName = null;
  dom.activeDocPanel.classList.add('hidden');
  dom.questionInput.placeholder = 'Ask anything, or upload a document first...';
  dom.chatEmpty.style.display    = 'flex';
  dom.chatMessages.style.display = 'none';
  clearMessages();
  dom.fileInput.click();
});

// ── Document list ──────────────────────────────────────────────

async function fetchDocList() {
  dom.refreshBtn.classList.add('spinning');
  try {
    const res  = await fetch(`${API}/documents`);
    const data = await res.json();
    renderDocList(data.documents || []);
  } catch { /* ignore */ }
  finally { dom.refreshBtn.classList.remove('spinning'); }
}

function renderDocList(docs) {
  if (!docs.length) {
    dom.docList.innerHTML = '<div class="doc-list-empty">No documents yet.</div>';
    return;
  }
  dom.docList.innerHTML = [...docs].reverse().map(id => `
    <div class="doc-item ${id===state.documentId?'selected':''}" data-id="${esc(id)}" title="${esc(id)}">
      <span class="doc-item-icon">📄</span>
      <span class="doc-item-id">${esc(shortId(id))}</span>
    </div>`
  ).join('');
  dom.docList.querySelectorAll('.doc-item').forEach(el =>
    el.addEventListener('click', () => switchDoc(el.dataset.id))
  );
}

function switchDoc(id) {
  if (id === state.documentId) return;
  state.documentId   = id;
  state.documentName = shortId(id);
  state.fileType     = 'pdf';
  state.chunks       = '?';
  dom.activeDocTypeIcon.textContent = '📄';
  dom.activeDocName.textContent     = shortId(id);
  dom.activeDocMeta.textContent     = 'Switched to existing document';
  dom.activeDocPanel.classList.remove('hidden');
  dom.questionInput.disabled = false;
  dom.sendBtn.disabled       = false;
  dom.chatEmpty.style.display    = 'none';
  dom.chatMessages.style.display = 'flex';
  clearMessages();
  addSystemMsg(`Switched to document ${shortId(id)}`);
  renderDocList(
    Array.from(dom.docList.querySelectorAll('.doc-item')).map(e => e.dataset.id)
  );
  toast(`Switched to ${shortId(id)}`, 'info', 2000);
}

dom.refreshBtn.addEventListener('click', fetchDocList);

// ── Chat messages ──────────────────────────────────────────────

function scrollToBottom() { dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight; }
function clearMessages()   { dom.chatMessages.innerHTML = ''; }

function addSystemMsg(text) {
  const wrap   = document.createElement('div');
  const bubble = document.createElement('div');
  wrap.className   = 'msg msg-system';
  bubble.className = 'msg-bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);
  dom.chatMessages.appendChild(wrap);
  scrollToBottom();
}

function addUserMsg(text) {
  const wrap   = document.createElement('div');
  const avatar = document.createElement('div');
  const body   = document.createElement('div');
  const bubble = document.createElement('div');
  const time   = document.createElement('div');

  wrap.className   = 'msg msg-user';
  avatar.className = 'msg-avatar';
  avatar.textContent = '👤';
  bubble.className = 'msg-bubble';
  bubble.innerHTML = nl2br(text);
  time.className   = 'msg-time';
  time.textContent = nowStr();

  body.appendChild(bubble);
  body.appendChild(time);
  wrap.appendChild(body);
  wrap.appendChild(avatar);
  dom.chatMessages.appendChild(wrap);
  scrollToBottom();
}

/**
 * Create an AI bubble with a typing indicator.
 * Returns a controller object with .appendToken(t), .finalise(providerInfo), .markError(msg).
 */
function createAIBubble() {
  const wrap        = document.createElement('div');
  const avatar      = document.createElement('div');
  const body        = document.createElement('div');
  const bubble      = document.createElement('div');
  const time        = document.createElement('div');
  const providerTag = document.createElement('div');

  wrap.className        = 'msg msg-ai';
  avatar.className      = 'msg-avatar';
  avatar.textContent    = '🤖';
  bubble.className      = 'msg-bubble';
  bubble.innerHTML      = `<div class="typing-dot"><span></span><span></span><span></span></div>`;
  time.className        = 'msg-time';
  time.textContent      = nowStr();
  providerTag.className = 'msg-provider-tag';

  body.appendChild(bubble);
  body.appendChild(providerTag);
  body.appendChild(time);
  wrap.appendChild(avatar);
  wrap.appendChild(body);
  dom.chatMessages.appendChild(wrap);
  scrollToBottom();

  let accumulated = '';
  let started     = false;
  let cursor      = null;

  return {
    appendToken(token) {
      if (!started) {
        bubble.innerHTML = '';
        cursor = document.createElement('span');
        cursor.className = 'cursor';
        started = true;
      }
      accumulated += token;
      bubble.textContent = accumulated;
      bubble.appendChild(cursor);
      scrollToBottom();
    },
    finalise(providerInfo) {
      if (cursor) cursor.remove();
      if (!started) bubble.innerHTML = '<em style="color:var(--text-faint)">No response.</em>';
      if (providerInfo) {
        providerTag.textContent = `${providerInfo.name} · ${providerInfo.model}`;
        providerTag.style.display = 'block';
      }
      return accumulated;
    },
    markError(msg) {
      wrap.classList.add('msg-error');
      bubble.textContent = msg;
      if (cursor) cursor.remove();
    },
  };
}

// ── Streaming ask ──────────────────────────────────────────────

async function sendQuestion() {
  const q = dom.questionInput.value.trim();
  if (!q || state.isAsking) return;

  state.isAsking = true;
  dom.questionInput.value = '';
  resizeTextarea();
  dom.sendBtn.classList.add('hidden');
  dom.stopBtn.classList.remove('hidden');

  // Hide empty state on first message
  dom.chatEmpty.style.display    = 'none';
  dom.chatMessages.style.display = 'flex';

  addUserMsg(q);
  const aiBubble = createAIBubble();

  state.abortCtrl = new AbortController();
  let providerInfo = null;

  try {
    const res = await fetch(`${API}/ask`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({
        document_id: state.documentId,
        question:    q,
        history:     state.history.slice(-6),
      }),
      signal:  state.abortCtrl.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = err.error || `HTTP ${res.status}`;
      if (res.status === 503) {
        throw new Error('Provider unreachable. Check your API key in Settings.');
      }
      throw new Error(msg);
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, {stream: true});

      // Parse SSE lines
      const parts = buffer.split('\n\n');
      buffer = parts.pop();            // keep incomplete chunk

      for (const part of parts) {
        for (const line of part.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          let payload;
          try { payload = JSON.parse(line.slice(6)); } catch { continue; }

          if (payload.error) {
            aiBubble.markError(payload.error);
            toast(payload.error, 'error', 7000);
            return;
          }
          if (payload.token) aiBubble.appendToken(payload.token);
          if (payload.done) {
            providerInfo = { name: payload.name || payload.provider, model: payload.model };
            break;
          }
        }
      }
    }

    const answer = aiBubble.finalise(providerInfo);

    // Store in history for multi-turn
    state.history.push({ role: 'user', content: q });
    state.history.push({ role: 'assistant', content: answer || '' });
    if (state.history.length > 20) state.history = state.history.slice(-20);

  } catch (err) {
    if (err.name === 'AbortError') {
      aiBubble.finalise(null);
      addSystemMsg('Generation stopped.');
    } else {
      aiBubble.markError(err.message);
      toast(err.message, 'error', 7000);
    }
  } finally {
    state.isAsking    = false;
    state.abortCtrl   = null;
    dom.stopBtn.classList.add('hidden');
    dom.sendBtn.classList.remove('hidden');
    dom.questionInput.focus();
  }
}

dom.sendBtn.addEventListener('click', sendQuestion);

dom.stopBtn.addEventListener('click', () => {
  if (state.abortCtrl) state.abortCtrl.abort();
});

dom.questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); }
});

// ── Auto-resize textarea ───────────────────────────────────────

function resizeTextarea() {
  const el = dom.questionInput;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}
dom.questionInput.addEventListener('input', resizeTextarea);

// ── Boot ───────────────────────────────────────────────────────

(async function boot() {
  dom.chatMessages.style.display = 'none';

  // Input is enabled immediately — no upload required
  dom.questionInput.disabled = false;
  dom.sendBtn.disabled       = false;

  await Promise.all([checkOllama(), fetchActiveProvider(), fetchDocList()]);

  setInterval(checkOllama,         OLLAMA_POLL);
  setInterval(fetchActiveProvider, OLLAMA_POLL);
})();
