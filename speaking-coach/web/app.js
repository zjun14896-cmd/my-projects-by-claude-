'use strict';
/* 口语精听校对 —— 前端（纯原生 JS，无需构建） */

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const app = $('#app');
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const UNDERSTAND_CHUNK = 12;
const IMPROVE_CHUNK = 6;
const CONCURRENCY = 3;

let settings = null;   // 公开设置（不含明文密钥）
let S = null;          // 当前打开的练习记录
let pendingAutoTranscribe = null;

// ---------------------------------------------------------------------------
// 通用
// ---------------------------------------------------------------------------

async function api(method, url, opt = {}) {
  const init = { method, headers: Object.assign({ 'X-App': '1' }, opt.headers || {}) };
  if (opt.json !== undefined) {
    init.body = JSON.stringify(opt.json);
    init.headers['Content-Type'] = 'application/json';
  } else if (opt.raw !== undefined) {
    init.body = opt.raw;
    init.headers['Content-Type'] = opt.type || 'application/octet-stream';
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new Error('连不上本地程序：请确认启动时弹出的黑色窗口还开着');
  }
  let data = {};
  try { data = await res.json(); } catch (e) { /* 非 JSON */ }
  if (!res.ok) throw new Error(data.error || ('请求失败 HTTP ' + res.status));
  return data;
}

let toastTimer = null;
function toast(msg, isErr) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, isErr ? 6000 : 2600);
}

function fmtTime(sec) {
  if (sec == null || isNaN(sec)) return '';
  sec = Math.max(0, sec);
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return m + ':' + String(s).padStart(2, '0');
}

function fmtDuration(sec) {
  if (!sec) return '';
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m ? `${m} 分 ${s} 秒` : `${s} 秒`;
}

const newId = () => 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const chunk = (arr, n) => { const out = []; for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n)); return out; };
const hasText = (r) => !!(r.en && r.en.trim());

async function loadSettings() {
  settings = await api('GET', '/api/settings');
  return settings;
}

// ---------------------------------------------------------------------------
// 路由
// ---------------------------------------------------------------------------

async function route() {
  await flushSave();
  stopPlayback();
  const m = location.hash.match(/^#\/s\/([\w-]+)/);
  try {
    if (m) await openSession(m[1]);
    else await showHome();
  } catch (e) {
    app.innerHTML = `<div class="home"><div class="card empty">出错了：${esc(e.message)}<br><br><a href="#/">回到首页</a></div></div>`;
  }
}
window.addEventListener('hashchange', route);

// ---------------------------------------------------------------------------
// 首页：上传 + 历史记录
// ---------------------------------------------------------------------------

async function showHome() {
  S = null;
  document.title = '口语精听校对';
  app.innerHTML = `
  <div class="home">
    <div class="card">
      <h1>新的一段练习</h1>
      <div class="muted">上传手机录音 → 转写成英文 → 逐句精听校对 → 对照 AI 的理解 → 生成更地道的说法</div>
      <label class="drop" id="drop">
        <strong>把录音拖到这里，或点击选择文件</strong>
        <span class="muted small">m4a / mp3 / wav / mp4 / aac / ogg … 手机录音机的文件直接用</span>
        <input type="file" id="file" accept="audio/*,video/mp4,.m4a,.mp4,.aac,.mp3,.wav,.ogg,.opus,.webm,.flac" hidden>
      </label>
      <div class="home-row">
        <input id="new-title" placeholder="标题（可以不填，默认用文件名），例如：Day 2 聊周末">
      </div>
      <div class="status-line" id="status-line"></div>
    </div>
    <div class="sess-list">
      <h2>练习记录</h2>
      <div id="sess-list"><div class="empty">加载中…</div></div>
    </div>
  </div>`;

  const drop = $('#drop'), file = $('#file');
  file.addEventListener('change', () => file.files[0] && uploadFile(file.files[0]));
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('over');
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
  });

  const [{ sessions }] = await Promise.all([api('GET', '/api/sessions'), loadSettings()]);
  renderStatusLine();
  const list = $('#sess-list');
  if (!sessions.length) {
    list.innerHTML = '<div class="empty card">还没有练习记录。上传第一段录音开始吧。</div>';
    return;
  }
  list.innerHTML = sessions.map((s) => `
    <div class="sess-item" data-id="${esc(s.id)}">
      <div>
        <div class="t">${esc(s.title || s.id)}</div>
        <div class="meta">${esc(s.created)}${s.duration ? ' · ' + fmtDuration(s.duration) : ''}</div>
      </div>
      <div class="progress">
        <span class="${s.n_rows ? 'done' : ''}">${s.n_rows ? s.n_rows + ' 句' : '未转写'}</span>
        <span class="${s.n_rows && s.n_checked >= s.n_rows ? 'done' : ''}">校对 ${s.n_checked}/${s.n_rows}</span>
        <span class="${s.n_rows && s.n_natural >= s.n_rows ? 'done' : ''}">地道 ${s.n_natural}/${s.n_rows}</span>
      </div>
      <button class="btn ghost small danger" data-del="${esc(s.id)}" title="删除这条记录">删除</button>
    </div>`).join('');
  list.addEventListener('click', async (e) => {
    const del = e.target.closest('[data-del]');
    if (del) {
      e.stopPropagation();
      const item = del.closest('.sess-item');
      if (!confirm(`确定删除「${$('.t', item).textContent}」吗？录音和校对内容都会删掉，无法恢复。`)) return;
      try {
        await api('DELETE', '/api/sessions/' + del.dataset.del);
        item.remove();
        toast('已删除');
      } catch (err) { toast(err.message, true); }
      return;
    }
    const item = e.target.closest('.sess-item');
    if (item) location.hash = '#/s/' + item.dataset.id;
  });
}

function renderStatusLine() {
  const el = $('#status-line');
  if (!el || !settings) return;
  el.innerHTML = `
    <span class="pill ${settings.asr_ready ? 'on' : 'off'}">豆包转写：${settings.asr_ready ? '已配置' : '未配置（可以先按停顿切段、自己听写）'}</span>
    <span class="pill ${settings.llm_ready ? 'on' : 'off'}">DeepSeek：${settings.llm_ready ? '已配置' : '未配置'}</span>
    ${settings.asr_ready && settings.llm_ready ? '' : '<a href="javascript:void 0" data-open-settings>去设置</a>'}`;
}

async function uploadFile(file) {
  const title = ($('#new-title').value || '').trim() || file.name.replace(/\.[^.]+$/, '');
  const drop = $('#drop');
  drop.innerHTML = '<strong><span class="spin"></span> 正在上传…</strong>';
  try {
    const { session } = await api('POST', '/api/sessions', {
      raw: file,
      type: file.type || 'application/octet-stream',
      headers: { 'X-Filename': encodeURIComponent(file.name), 'X-Title': encodeURIComponent(title) },
    });
    pendingAutoTranscribe = session.id;
    location.hash = '#/s/' + session.id;
  } catch (e) {
    toast(e.message, true);
    showHome();
  }
}

// ---------------------------------------------------------------------------
// 练习页
// ---------------------------------------------------------------------------

let player = null;

async function openSession(id) {
  const [{ session }] = await Promise.all([api('GET', '/api/sessions/' + id), loadSettings()]);
  S = session;
  S.rows = S.rows || [];
  document.title = S.title + ' · 口语精听校对';
  renderSessionShell();
  renderRows();
  autoGrowAll();
  if (pendingAutoTranscribe === id) {
    pendingAutoTranscribe = null;
    if (!S.rows.length && settings.asr_ready) transcribeDoubao();
  }
  understandMissing();
}

/** 有英文、但还没有（或已过时的）AI 理解的句子，自动补上 */
function understandMissing() {
  if (!S || !settings.llm_ready) return;
  const ids = S.rows.filter((r) => hasText(r) && r.zh_src !== r.en && !r._zhBusy).map((r) => r.id);
  if (ids.length) understandRows(ids);
}

function renderSessionShell() {
  app.innerHTML = `
  <section class="sess">
    <div class="sess-head">
      <div class="sh-top">
        <a href="#/" class="back">← 全部记录</a>
        <input class="title-input" id="title-input" value="${esc(S.title)}" title="点击修改标题">
        <span class="save-status" id="save-status"></span>
      </div>
      <div class="sh-player">
        <audio id="player" controls preload="auto" src="/api/sessions/${esc(S.id)}/audio"></audio>
        <label>速度
          <select id="speed">
            <option value="0.6">0.6×</option><option value="0.75">0.75×</option><option value="0.9">0.9×</option>
            <option value="1" selected>1×</option><option value="1.25">1.25×</option>
          </select>
        </label>
      </div>
      <div class="sh-bar">
        <div class="steps">
          <span class="step-info" id="info"></span>
          <button class="btn primary" id="btn-improve" type="button">③ 生成更地道的说法</button>
        </div>
        <div class="sh-more">
          <button class="btn ghost small" id="btn-understand-all" type="button" title="把所有句子重新交给 AI 理解一遍">重新生成全部 AI 理解</button>
          <button class="btn ghost small" id="btn-export" type="button">导出 Markdown</button>
          <button class="btn ghost small" id="btn-retranscribe" type="button">重新转写</button>
        </div>
      </div>
      <div class="busy" id="busy" hidden></div>
      <div class="colhead grid" id="colhead">
        <div>#</div>
        <div>① 我实际说的英文<small>逐字校对，说错了也照原样写</small></div>
        <div>② AI 理解的中文<small>是不是你想表达的意思？</small></div>
        <div>③ 更地道的说法</div>
      </div>
    </div>
    <div id="rows"></div>
    <div class="foot-hint" id="foot-hint">在英文框里按 <kbd>Esc</kbd> 播放 / 暂停这一句，<kbd>Tab</kbd> 跳到下一句。改完一句，光标离开后 AI 会自动重新理解。</div>
  </section>`;

  player = $('#player');
  player.addEventListener('loadedmetadata', () => {
    if (S && !S.duration && isFinite(player.duration)) { S.duration = player.duration; markDirty(); }
  });
  player.addEventListener('timeupdate', onTimeUpdate);
  player.addEventListener('pause', () => { segEnd = null; setPlayingRow(null); });
  player.addEventListener('play', () => { if (!segmentMode) segEnd = null; segmentMode = false; });
  $('#speed').addEventListener('change', (e) => { player.playbackRate = parseFloat(e.target.value); });

  $('#title-input').addEventListener('input', (e) => { S.title = e.target.value; markDirty(); });
  $('#btn-improve').addEventListener('click', () => improveAll());
  $('#btn-understand-all').addEventListener('click', () => {
    if (!requireLLM()) return;
    const rows = S.rows.filter(hasText);
    if (rows.length && confirm(`把全部 ${rows.length} 句重新交给 AI 理解？（你已标记的 ✓/✗ 会被清空）`)) understandRows(rows.map((r) => r.id), { force: true });
  });
  $('#btn-export').addEventListener('click', exportMarkdown);
  $('#btn-retranscribe').addEventListener('click', () => {
    if (S.rows.length && !confirm('重新转写会清空当前所有句子和你的修改，确定吗？')) return;
    S.rows = [];
    S.source = null;
    markDirty();
    renderRows();
  });

  const rowsEl = $('#rows');
  rowsEl.addEventListener('mousedown', (e) => {
    // 点按钮时不要让英文框失去焦点（继续打字、Esc 仍然有效）
    if (e.target.closest('button') && e.target.closest('.row')) e.preventDefault();
  });
  rowsEl.addEventListener('click', onRowsClick);
  rowsEl.addEventListener('input', onRowsInput);
  rowsEl.addEventListener('focusout', onRowsFocusOut);
}

function updateHeader() {
  if (!S || !$('#info')) return;
  const rows = S.rows.filter(hasText);
  const ok = rows.filter((r) => r.match === true).length;
  const bad = rows.filter((r) => r.match === false).length;
  const nat = rows.filter((r) => r.natural).length;
  const has = S.rows.length > 0;
  $('#info').innerHTML = has
    ? `共 <b>${S.rows.length}</b> 句 · 意思对 <b>${ok}</b> · 不对 <b>${bad}</b> · 未标记 <b>${rows.length - ok - bad}</b> · 已生成地道说法 <b>${nat}</b>`
    : '还没有转写';
  $('#btn-improve').disabled = !rows.length;
  $('#btn-improve').hidden = !has;
  $('#btn-understand-all').hidden = !rows.length;
  $('#btn-retranscribe').hidden = !has;
  $('#btn-export').hidden = !has;
  $('#colhead').hidden = !has;
  $('#foot-hint').hidden = !has;
}

// ---------- 行渲染 ----------

function rowById(id) { return S && S.rows.find((r) => r.id === id); }
function rowEl(id) { return $(`.row[data-id="${CSS.escape(id)}"]`); }

function renderRows() {
  const box = $('#rows');
  if (!box) return;
  updateHeader();
  if (!S.rows.length) {
    box.className = '';
    box.innerHTML = chooserHTML();
    bindChooser();
    return;
  }
  box.className = 'rows';
  box.innerHTML = S.rows.map((r, i) => rowHTML(r, i)).join('');
}

function rowHTML(r, i) {
  const hasTime = r.start != null;
  return `
  <div class="row grid" data-id="${esc(r.id)}" data-match="${r.match === true ? 'ok' : r.match === false ? 'bad' : ''}">
    <div class="c-idx">
      <button class="play" type="button" tabindex="-1" data-act="play" ${hasTime ? '' : 'disabled'} title="${hasTime ? '只播这一句（Esc）' : '这一句没有时间信息'}">▶</button>
      <div class="meta">
        <span class="idx">${i + 1}</span>
        <span class="time" data-act="seek" title="从这里开始往下播放整段">${hasTime ? fmtTime(r.start) : ''}</span>
      </div>
    </div>
    <div class="c-en">
      <textarea class="en" rows="1" spellcheck="false" placeholder="${S.source === 'silence' ? '听一下这一段，把你说的英文照原样写在这里…' : '（空）'}">${esc(r.en)}</textarea>
      <div class="en-tools">${enToolsHTML(r)}</div>
    </div>
    <div class="c-zh">
      <div class="zh-body">${zhBodyHTML(r)}</div>
      <textarea class="intended" rows="1" placeholder="我其实想说……（用中文写下你本来想表达的意思）" ${r.match === false ? '' : 'hidden'}>${esc(r.intended || '')}</textarea>
    </div>
    <div class="c-nat">${natHTML(r)}</div>
  </div>`;
}

function enToolsHTML(r) {
  const changed = r.asr != null && r.asr !== r.en;
  return `${changed ? `<span class="badge" title="识别原文：${esc(r.asr)}">已改动</span>` : ''}
    <button class="btn ghost" type="button" tabindex="-1" data-act="split" title="在光标处把这一句拆成两句">✂ 拆分</button>
    <button class="btn ghost" type="button" tabindex="-1" data-act="merge" title="和下一句合并">⤓ 合并下一句</button>
    <button class="btn ghost danger" type="button" tabindex="-1" data-act="delete">删除</button>`;
}

function zhBodyHTML(r) {
  if (!hasText(r)) return '<span class="muted small">—</span>';
  if (r._zhBusy) return '<span class="muted small"><span class="spin"></span> AI 理解中…</span>';
  let html = '';
  if (r._zhErr) html += `<div class="err-text">${esc(r._zhErr)} <button class="btn ghost small" type="button" tabindex="-1" data-act="understand">重试</button></div>`;
  if (r.zh) {
    const text = esc(r.zh).replace(/【(.*?)】/g, '<mark>【$1】</mark>');
    html += `<div class="zh-text">${text}</div>`;
    if (r.zh_src !== r.en) html += `<div class="stale">英文改过了，光标离开后会自动重新理解 <button class="btn ghost small" type="button" tabindex="-1" data-act="understand">现在更新</button></div>`;
    html += `<div class="judge">
      <button type="button" tabindex="-1" class="ok ${r.match === true ? 'on' : ''}" data-act="ok">✓ 意思对</button>
      <button type="button" tabindex="-1" class="bad ${r.match === false ? 'on' : ''}" data-act="bad">✗ 不是这个意思</button>
    </div>`;
  } else if (!r._zhErr) {
    html += settings && settings.llm_ready
      ? '<button class="btn small" type="button" tabindex="-1" data-act="understand">让 AI 理解这一句</button>'
      : '<span class="muted small">配置 DeepSeek 后自动生成（右上角「设置」）</span>';
  }
  return html;
}

function natSig(r) { return [r.en, r.match === false ? 'x:' + (r.intended || '') : 'ok'].join('\u0001'); }

function natHTML(r) {
  if (!hasText(r)) return '';
  if (r._natBusy) return '<span class="muted small"><span class="spin"></span> 正在生成…</span>';
  let html = '';
  if (r._natErr) html += `<div class="err-text">${esc(r._natErr)}</div>`;
  if (r.natural) {
    html += `<div class="nat-text">${esc(r.natural)}</div>
      <div class="nat-actions">
        <button class="icon-btn" type="button" tabindex="-1" data-act="speak" title="用电脑的英文语音朗读这句">🔊 朗读</button>
        <button class="icon-btn" type="button" tabindex="-1" data-act="copy">复制</button>
        <button class="icon-btn" type="button" tabindex="-1" data-act="improve" title="重新生成这一句">↻ 重新生成</button>
      </div>`;
    const issues = r.issues || [];
    if (issues.length) {
      html += '<ul class="issues">' + issues.map((x) => `<li>
        ${x.said ? `<span class="said">${esc(x.said)}</span><span class="arrow">→</span>` : ''}<span class="better">${esc(x.better)}</span>
        ${x.why ? `<div class="why">${esc(x.why)}</div>` : ''}</li>`).join('') + '</ul>';
    } else {
      html += '<span class="good">✓ 这句说得挺自然</span>';
    }
    if (r.nat_sig && r.nat_sig !== natSig(r)) {
      html += '<div class="stale">英文或「想表达的意思」改过了 <button class="btn ghost small" type="button" tabindex="-1" data-act="improve">按新内容重新生成</button></div>';
    }
  } else if (!r._natErr) {
    html += `<span class="muted small">校对完成后点上方「③ 生成」</span>
      <button class="btn ghost small" type="button" tabindex="-1" data-act="improve">只生成这一句</button>`;
  } else {
    html += '<button class="btn ghost small" type="button" tabindex="-1" data-act="improve">重试</button>';
  }
  return html;
}

function refreshRow(id) {
  const r = rowById(id), el = rowEl(id);
  if (!r || !el) return;
  el.dataset.match = r.match === true ? 'ok' : r.match === false ? 'bad' : '';
  $('.en-tools', el).innerHTML = enToolsHTML(r);
  $('.zh-body', el).innerHTML = zhBodyHTML(r);
  $('.intended', el).hidden = r.match !== false;
  $('.c-nat', el).innerHTML = natHTML(r);
  updateHeader();
}

// ---------- 行事件 ----------

function onRowsInput(e) {
  const el = e.target.closest('.row');
  if (!el) return;
  const r = rowById(el.dataset.id);
  if (!r) return;
  autoGrow(e.target);
  if (e.target.classList.contains('en')) {
    const wasStale = r.zh && r.zh_src !== r.en;
    r.en = e.target.value;
    const nowStale = r.zh && r.zh_src !== r.en;
    if (wasStale !== nowStale || (r.natural && r.nat_sig)) {
      $('.zh-body', el).innerHTML = zhBodyHTML(r);
      $('.c-nat', el).innerHTML = natHTML(r);
    }
    $('.en-tools', el).innerHTML = enToolsHTML(r);
  } else if (e.target.classList.contains('intended')) {
    r.intended = e.target.value;
    if (r.natural) $('.c-nat', el).innerHTML = natHTML(r);
  }
  markDirty();
}

function onRowsFocusOut(e) {
  if (!e.target.classList.contains('en')) return;
  const el = e.target.closest('.row');
  const r = el && rowById(el.dataset.id);
  if (!r || !hasText(r) || !settings.llm_ready || r._zhBusy) return;
  if (r.zh_src !== r.en) understandRows([r.id]);
}

function onRowsClick(e) {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const el = btn.closest('.row');
  const r = el && rowById(el.dataset.id);
  if (!r) return;
  const act = btn.dataset.act;
  if (act === 'play') playRow(r);
  else if (act === 'seek') seekTo(r);
  else if (act === 'understand') { if (requireLLM()) understandRows([r.id]); }
  else if (act === 'ok') { r.match = r.match === true ? null : true; markDirty(); refreshRow(r.id); }
  else if (act === 'bad') {
    r.match = r.match === false ? null : false;
    markDirty();
    refreshRow(r.id);
    if (r.match === false) { const t = $('.intended', el); autoGrow(t); t.focus(); }
  }
  else if (act === 'improve') { if (requireLLM()) improveRows([r]); }
  else if (act === 'speak') speak(r.natural);
  else if (act === 'copy') { navigator.clipboard.writeText(r.natural).then(() => toast('已复制'), () => toast('复制失败', true)); }
  else if (act === 'split') splitRow(r, el);
  else if (act === 'merge') mergeRow(r);
  else if (act === 'delete') deleteRow(r);
}

function clearAI(r) {
  r.zh = ''; r.zh_src = null; r.match = null;
  r.natural = ''; r.issues = []; r.nat_sig = null;
}

function splitRow(r, el) {
  const ta = $('.en', el);
  const pos = ta.selectionStart;
  const a = r.en.slice(0, pos).trim(), b = r.en.slice(pos).trim();
  if (!a || !b) { toast('先把光标放到英文框里要拆开的位置，再点「拆分」'); ta.focus(); return; }
  const idx = S.rows.indexOf(r);
  const r2 = { id: newId(), en: b, asr: null, start: null, end: null, intended: '' };
  if (r.start != null && r.end != null) {
    const cut = r.start + (r.end - r.start) * (pos / Math.max(1, r.en.length));
    r2.start = cut; r2.end = r.end; r.end = cut;
  }
  r.en = a; r.asr = null;
  clearAI(r); clearAI(r2);
  S.rows.splice(idx + 1, 0, r2);
  markDirty();
  renderRows();
  if (settings.llm_ready) understandRows([r.id, r2.id]);
}

function mergeRow(r) {
  const idx = S.rows.indexOf(r), next = S.rows[idx + 1];
  if (!next) { toast('已经是最后一句了'); return; }
  r.en = [r.en, next.en].filter((x) => x && x.trim()).join(' ');
  r.asr = null;
  r.intended = [r.intended, next.intended].filter(Boolean).join(' ');
  if (next.end != null) r.end = next.end;
  if (r.start == null) r.start = next.start;
  clearAI(r);
  S.rows.splice(idx + 1, 1);
  markDirty();
  renderRows();
  if (settings.llm_ready && hasText(r)) understandRows([r.id]);
}

function deleteRow(r) {
  if (hasText(r) && !confirm('删除这一句？')) return;
  S.rows.splice(S.rows.indexOf(r), 1);
  markDirty();
  renderRows();
}

function autoGrow(t) {
  if (!t || t.tagName !== 'TEXTAREA') return;
  if (CSS.supports && CSS.supports('field-sizing', 'content')) return;
  t.style.height = 'auto';
  t.style.height = t.scrollHeight + 2 + 'px';
}
function autoGrowAll() { $$('#rows textarea').forEach(autoGrow); }

// ---------- 播放 ----------

let segEnd = null, segmentMode = false, playingRowId = null, rafId = null;

function playRow(r) {
  if (!player || r.start == null) return;
  if (playingRowId === r.id && !player.paused) { player.pause(); return; }
  segmentMode = true;
  segEnd = (r.end != null ? r.end : r.start + 8) + 0.15;
  player.currentTime = Math.max(0, r.start - 0.1);
  setPlayingRow(r.id);
  player.play().catch(() => {});
  cancelAnimationFrame(rafId);
  const tick = () => {
    if (segEnd == null || player.paused) return;
    if (player.currentTime >= segEnd) { player.pause(); return; }
    rafId = requestAnimationFrame(tick);
  };
  rafId = requestAnimationFrame(tick);
}

function seekTo(r) {
  if (!player || r.start == null) return;
  segEnd = null;
  player.currentTime = Math.max(0, r.start - 0.1);
  player.play().catch(() => {});
}

function stopPlayback() {
  if (player) { try { player.pause(); } catch (e) { /* ignore */ } }
  if (window.speechSynthesis) speechSynthesis.cancel();
  player = null;
}

function setPlayingRow(id) {
  if (playingRowId) { const el = rowEl(playingRowId); if (el) el.classList.remove('playing'); }
  playingRowId = id;
  if (id) { const el = rowEl(id); if (el) el.classList.add('playing'); }
}

let currentRowId = null;
function onTimeUpdate() {
  if (!S) return;
  const t = player.currentTime;
  const r = S.rows.find((x) => x.start != null && x.end != null && t >= x.start - 0.05 && t < x.end + 0.1);
  const id = r ? r.id : null;
  if (id === currentRowId) return;
  if (currentRowId) { const el = rowEl(currentRowId); if (el) el.classList.remove('current'); }
  currentRowId = id;
  if (id) { const el = rowEl(id); if (el) el.classList.add('current'); }
}

function speak(text) {
  if (!window.speechSynthesis) { toast('这个浏览器不支持朗读', true); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-US';
  const voices = speechSynthesis.getVoices().filter((v) => /^en[-_]US/i.test(v.lang));
  const best = voices.find((v) => /natural|online/i.test(v.name)) || voices[0];
  if (best) u.voice = best;
  u.rate = 0.95;
  speechSynthesis.speak(u);
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || $('dialog[open]')) return;
  const el = document.activeElement && document.activeElement.closest && document.activeElement.closest('.row');
  if (!el) return;
  const r = rowById(el.dataset.id);
  if (r && r.start != null) { e.preventDefault(); playRow(r); }
});

// ---------------------------------------------------------------------------
// 自动保存
// ---------------------------------------------------------------------------

let saveTimer = null, saving = null, dirty = false;

function setSaveStatus(text, isErr) {
  const el = $('#save-status');
  if (el) { el.textContent = text; el.classList.toggle('err', !!isErr); }
}

function markDirty() {
  dirty = true;
  setSaveStatus('有修改…');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 700);
}

function serialize(sess) {
  return {
    title: sess.title,
    duration: sess.duration,
    source: sess.source,
    rows: sess.rows.map((r) => {
      const o = {};
      for (const k in r) if (k[0] !== '_') o[k] = r[k];
      return o;
    }),
  };
}

async function saveNow() {
  clearTimeout(saveTimer);
  if (saving) { await saving; }
  if (!dirty || !S) return;
  dirty = false;
  const sid = S.id, payload = serialize(S);
  setSaveStatus('保存中…');
  saving = api('PUT', '/api/sessions/' + sid, { json: payload })
    .then(() => { if (S && S.id === sid && !dirty) setSaveStatus('已自动保存 ✓'); })
    .catch((e) => { dirty = true; setSaveStatus('保存失败：' + e.message, true); })
    .finally(() => { saving = null; });
  await saving;
}

async function flushSave() { if (dirty || saving) await saveNow(); }

window.addEventListener('beforeunload', (e) => {
  if (dirty || saving) { saveNow(); e.preventDefault(); e.returnValue = ''; }
});

// ---------------------------------------------------------------------------
// 转写：豆包 / 按停顿切段 / 粘贴文本
// ---------------------------------------------------------------------------

function chooserHTML() {
  const asr = settings && settings.asr_ready;
  return `
  <div class="card chooser">
    <h3>第一步：把录音变成逐句的英文</h3>
    <div class="choice ${asr ? 'rec' : ''}">
      <div><b>豆包自动转写</b>（推荐）<div class="d">自动识别英文并按句切好，每句带时间，可以单独播放。${asr ? '' : '<br>还没有配置豆包密钥 —— 点右上角「设置」。'}</div></div>
      <button class="btn ${asr ? 'primary' : ''}" type="button" id="ch-doubao" ${asr ? '' : 'disabled'}>开始转写</button>
    </div>
    <div class="choice ${asr ? '' : 'rec'}">
      <div><b>按停顿自动切段，自己听写</b><div class="d">不用任何密钥。程序按你说话的停顿把录音切成小段，每段都能单独播放，你边听边把英文写进去。</div></div>
      <button class="btn ${asr ? '' : 'primary'}" type="button" id="ch-silence">切段</button>
    </div>
    <div class="choice">
      <div><b>粘贴已有的英文文本</b><div class="d">已经用别的工具转写好了？粘贴进来，按句号自动分句（这种方式没有单句时间，不能单句播放）。</div></div>
      <button class="btn" type="button" id="ch-paste">粘贴</button>
    </div>
    <div class="paste-box" id="paste-box" hidden>
      <textarea id="paste-text" placeholder="把英文文本粘贴到这里…"></textarea>
      <div><button class="btn primary" type="button" id="paste-ok">按句子拆开</button></div>
    </div>
  </div>`;
}

function bindChooser() {
  $('#ch-doubao').addEventListener('click', transcribeDoubao);
  $('#ch-silence').addEventListener('click', transcribeSilence);
  $('#ch-paste').addEventListener('click', () => { $('#paste-box').hidden = false; $('#paste-text').focus(); });
  $('#paste-ok').addEventListener('click', () => {
    const sentences = splitSentences($('#paste-text').value);
    if (!sentences.length) { toast('没有可用的文本'); return; }
    setRows(sentences.map((t) => ({ text: t, start: null, end: null })), 'paste');
  });
}

function setRows(segs, source) {
  S.source = source;
  S.rows = segs.map((g) => ({
    id: newId(), start: g.start, end: g.end, en: g.text || '', asr: source === 'doubao' ? g.text : null,
    zh: '', zh_src: null, match: null, intended: '', natural: '', issues: [], nat_sig: null,
  }));
  markDirty();
  renderRows();
  autoGrowAll();
  const ids = S.rows.filter(hasText).map((r) => r.id);
  if (ids.length && settings.llm_ready) understandRows(ids);
  else if (source === 'silence') { const t = $('#rows .en'); if (t) t.focus(); }
}

function splitSentences(text) {
  const out = [];
  for (const line of String(text || '').split(/\n+/)) {
    const clean = line.replace(/\s+/g, ' ').trim();
    if (!clean) continue;
    clean.split(/(?<=[.!?。！？])\s+/).forEach((s) => { if (s.trim()) out.push(s.trim()); });
  }
  return out;
}

function showBusy(text) {
  const b = $('#busy');
  if (!b) return;
  b.hidden = false;
  b.innerHTML = `<span class="spin"></span><span>${esc(text)}</span>`;
}
function hideBusy() { const b = $('#busy'); if (b) b.hidden = true; }

async function decodeAudio16k() {
  const buf = await (await fetch(`/api/sessions/${S.id}/audio`)).arrayBuffer();
  const AC = window.AudioContext || window.webkitAudioContext;
  const ac = new AC();
  let decoded;
  try {
    decoded = await ac.decodeAudioData(buf);
  } catch (e) {
    throw new Error('浏览器无法解码这个音频格式。请用 Chrome 或 Edge 打开，或者把录音转成 mp3 / wav 再上传。');
  } finally {
    if (ac.close) ac.close();
  }
  const sr = 16000;
  const off = new OfflineAudioContext(1, Math.ceil(decoded.duration * sr), sr);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  const rendered = await off.startRendering();
  return { pcm: rendered.getChannelData(0), sr, duration: decoded.duration };
}

function encodeWav(pcm, sr) {
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE');
  w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, 'data'); v.setUint32(40, pcm.length * 2, true);
  for (let i = 0, o = 44; i < pcm.length; i++, o += 2) {
    const x = Math.max(-1, Math.min(1, pcm[i]));
    v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

let transcribing = false;

async function transcribeDoubao() {
  if (transcribing) return;
  transcribing = true;
  const sess = S;
  try {
    showBusy('正在读取音频…');
    const { pcm, sr, duration } = await decodeAudio16k();
    sess.duration = duration;
    showBusy(`正在交给豆包识别（${fmtDuration(duration)}的录音，通常要几十秒）…`);
    const { segments } = await api('POST', `/api/sessions/${sess.id}/transcribe`, { raw: encodeWav(pcm, sr), type: 'audio/wav' });
    if (S !== sess) return;
    hideBusy();
    if (!segments.length) { toast('没有识别到说话内容（可能是静音）', true); return; }
    setRows(segments, 'doubao');
    toast(`转写完成，共 ${segments.length} 句`);
  } catch (e) {
    hideBusy();
    toast(e.message, true);
  } finally {
    transcribing = false;
  }
}

async function transcribeSilence() {
  if (transcribing) return;
  transcribing = true;
  const sess = S;
  try {
    showBusy('正在分析录音里的停顿…');
    const { pcm, sr, duration } = await decodeAudio16k();
    sess.duration = duration;
    const segs = segmentBySilence(pcm, sr);
    if (S !== sess) return;
    hideBusy();
    if (!segs.length) { toast('没找到说话的部分（录音可能是静音）', true); return; }
    setRows(segs.map((g) => ({ start: g.start, end: g.end, text: '' })), 'silence');
    toast(`切成了 ${segs.length} 段，点 ▶ 听，然后把英文写进去`);
  } catch (e) {
    hideBusy();
    toast(e.message, true);
  } finally {
    transcribing = false;
  }
}

/** 按停顿把音频切段：返回 [{start, end}]（秒） */
function segmentBySilence(pcm, sr) {
  const hopSec = 0.02, hop = Math.round(sr * hopSec);
  const nf = Math.floor(pcm.length / hop);
  if (!nf) return [];
  const db = new Float32Array(nf);
  for (let i = 0; i < nf; i++) {
    let s = 0;
    for (let j = i * hop, e = j + hop; j < e; j++) s += pcm[j] * pcm[j];
    db[i] = 10 * Math.log10(s / hop + 1e-10);
  }
  const sorted = Array.from(db).sort((a, b) => a - b);
  const noise = sorted[Math.floor(nf * 0.1)], loud = sorted[Math.floor(nf * 0.95)];
  const thr = noise + Math.max(6, (loud - noise) * 0.3);
  const minGap = Math.round(0.55 / hopSec);

  let segs = [], start = -1, last = -1;
  for (let i = 0; i < nf; i++) {
    if (db[i] > thr) {
      if (start < 0) start = i;
      last = i;
    } else if (start >= 0 && i - last >= minGap) {
      segs.push([start, last + 1]);
      start = -1;
    }
  }
  if (start >= 0) segs.push([start, last + 1]);
  segs = segs.filter(([a, b]) => (b - a) * hopSec >= 0.25);

  // 太短的段并到下一段
  const merged = [];
  for (const s of segs) {
    const prev = merged[merged.length - 1];
    if (prev && ((prev[1] - prev[0]) * hopSec < 1.0 || (s[1] - s[0]) * hopSec < 0.6) && (s[0] - prev[1]) * hopSec < 1.2) prev[1] = s[1];
    else merged.push(s.slice());
  }

  // 太长的段（>15 秒）在中间最安静的地方切开
  const maxLen = Math.round(15 / hopSec), margin = Math.round(4 / hopSec), win = 10;
  const out = [];
  const splitLong = ([a, b]) => {
    if (b - a <= maxLen) { out.push([a, b]); return; }
    let best = -1, bestVal = Infinity;
    for (let i = a + margin; i < b - margin - win; i++) {
      let s = 0;
      for (let k = 0; k < win; k++) s += db[i + k];
      if (s < bestVal) { bestVal = s; best = i + win / 2; }
    }
    if (best < 0) { out.push([a, b]); return; }
    splitLong([a, best]);
    splitLong([best, b]);
  };
  merged.forEach(splitLong);

  const dur = pcm.length / sr;
  return out.map(([a, b]) => ({
    start: Math.max(0, +(a * hopSec - 0.15).toFixed(2)),
    end: Math.min(dur, +(b * hopSec + 0.15).toFixed(2)),
  }));
}

// ---------------------------------------------------------------------------
// AI：理解 / 更地道
// ---------------------------------------------------------------------------

function requireLLM() {
  if (settings && settings.llm_ready) return true;
  toast('还没有配置 DeepSeek 密钥，点右上角「设置」', true);
  return false;
}

async function runChunks(chunks, worker, label) {
  let done = 0, idx = 0;
  const errors = [];
  const show = () => label && showBusy(`${label} ${done}/${chunks.length} 批…`);
  show();
  const next = async () => {
    while (idx < chunks.length) {
      const c = chunks[idx++];
      try { await worker(c); } catch (e) { errors.push(e.message); }
      done++;
      show();
    }
  };
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, chunks.length) }, next));
  if (label) hideBusy();
  if (errors.length) toast(errors[0], true);
}

async function understandRows(ids, opts = {}) {
  if (!settings.llm_ready) return;
  const sess = S;
  const rows = ids.map(rowById).filter((r) => r && hasText(r) && !r._zhBusy);
  if (!rows.length) return;
  rows.forEach((r) => { r._zhBusy = true; r._zhErr = null; refreshRow(r.id); });
  const label = rows.length > 2 ? 'AI 正在理解你说的英文' : '';
  await runChunks(chunk(rows, UNDERSTAND_CHUNK), async (c) => {
    const pos = c.map((r) => sess.rows.indexOf(r)).filter((i) => i >= 0);
    const lo = Math.max(0, Math.min(...pos) - 5), hi = Math.min(sess.rows.length, Math.max(...pos) + 6);
    // 发给 AI 的编号用句子序号（短，AI 不容易抄错）
    const aid = (r) => String(sess.rows.indexOf(r) + 1);
    const context = sess.rows.slice(lo, hi).filter(hasText).map((r) => ({ id: aid(r), en: r.en }));
    const sent = new Map(c.map((r) => [aid(r), r.en]));
    const sentIds = c.map(aid);
    try {
      const { items } = await api('POST', '/api/ai/understand', { json: { context, ids: sentIds } });
      const got = new Map(items.map((x) => [x.id, x.zh]));
      for (let k = 0; k < c.length; k++) {
        const r = c[k], id = sentIds[k];
        r._zhBusy = false;
        if (got.get(id)) {
          if (opts.force || r.zh !== got.get(id)) r.match = null; // 理解变了，需要重新确认
          r.zh = got.get(id);
          r.zh_src = sent.get(id);
        } else {
          r._zhErr = 'AI 没有返回这一句';
        }
      }
    } catch (e) {
      c.forEach((r) => { r._zhBusy = false; r._zhErr = e.message; });
      throw e;
    } finally {
      if (S === sess) {
        c.forEach((r) => refreshRow(r.id));
        markDirty();
      }
    }
    // 请求期间又改过、且已经不在编辑的句子，再理解一次
    const editing = document.activeElement && document.activeElement.closest && document.activeElement.closest('.row');
    const again = c.filter((r) => S === sess && sess.rows.includes(r) && hasText(r) && r.zh_src !== r.en && !(editing && editing.dataset.id === r.id));
    if (again.length) understandRows(again.map((r) => r.id));
  }, label);
}

async function improveAll() {
  if (!requireLLM()) return;
  const rows = S.rows.filter(hasText);
  if (!rows.length) return;
  const noZh = rows.filter((r) => !r.zh || r.zh_src !== r.en).length;
  if (noZh && !confirm(`还有 ${noZh} 句 AI 理解没有生成或已过时。仍然继续生成地道说法吗？`)) return;
  const unmarked = rows.filter((r) => r.match == null).length;
  if (unmarked && !confirm(`还有 ${unmarked} 句没有标记 ✓ / ✗，会按「AI 理解正确」来处理。继续吗？`)) return;
  let todo = rows.filter((r) => !r.natural || r.nat_sig !== natSig(r));
  if (!todo.length) {
    if (!confirm('所有句子都已经生成过了。要全部重新生成吗？')) return;
    todo = rows;
  }
  await improveRows(todo, '正在生成更地道的说法');
}

async function improveRows(rows, label) {
  const sess = S;
  rows = rows.filter((r) => hasText(r) && !r._natBusy);
  if (!rows.length) return;
  rows.forEach((r) => { r._natBusy = true; r._natErr = null; refreshRow(r.id); });
  await runChunks(chunk(rows, IMPROVE_CHUNK), async (c) => {
    const sigs = new Map(c.map((r) => [r.id, natSig(r)]));
    const aids = c.map((r) => String(sess.rows.indexOf(r) + 1));
    const items = c.map((r, k) => ({
      id: aids[k],
      en: r.en,
      ai_zh: r.zh || '',
      ai_understood: r.match === true ? true : r.match === false ? false : null,
      intended: r.match === false ? (r.intended || '') : '',
    }));
    try {
      const res = await api('POST', '/api/ai/improve', { json: { items } });
      const got = new Map(res.items.map((x) => [x.id, x]));
      for (let k = 0; k < c.length; k++) {
        const r = c[k];
        r._natBusy = false;
        const x = got.get(aids[k]);
        if (x && x.natural) {
          r.natural = x.natural;
          r.issues = x.issues || [];
          r.nat_sig = sigs.get(r.id);
        } else {
          r._natErr = 'AI 没有返回这一句';
        }
      }
    } catch (e) {
      c.forEach((r) => { r._natBusy = false; r._natErr = e.message; });
      throw e;
    } finally {
      if (S === sess) {
        c.forEach((r) => refreshRow(r.id));
        markDirty();
      }
    }
  }, label || '');
}

// ---------------------------------------------------------------------------
// 导出
// ---------------------------------------------------------------------------

function exportMarkdown() {
  const lines = [`# ${S.title}`, '', `录音：${S.audio_name || ''}　时长：${fmtDuration(S.duration)}　创建：${S.created}`, ''];
  S.rows.forEach((r, i) => {
    if (!hasText(r)) return;
    lines.push(`## ${i + 1}.${r.start != null ? ` [${fmtTime(r.start)}]` : ''}`, '');
    lines.push(`- **我说的**：${r.en}`);
    if (r.asr && r.asr !== r.en) lines.push(`- 识别原文：${r.asr}`);
    if (r.zh) lines.push(`- **AI 理解**：${r.zh}${r.match === true ? '　✓' : r.match === false ? '　✗' : ''}`);
    if (r.match === false && r.intended) lines.push(`- **我想说**：${r.intended}`);
    if (r.natural) {
      lines.push(`- **更地道**：${r.natural}`);
      (r.issues || []).forEach((x) => lines.push(`  - ${x.said ? `~~${x.said}~~ → ` : ''}**${x.better}**：${x.why}`));
    }
    lines.push('');
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (S.title || S.id).replace(/[\\/:*?"<>|]/g, '_') + '.md';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ---------------------------------------------------------------------------
// 设置
// ---------------------------------------------------------------------------

const dlg = $('#settings-dialog');
const form = $('#settings-form');
const SECRET = ['deepseek_api_key', 'doubao_api_key', 'doubao_access_token'];

function fillSettingsForm() {
  for (const el of form.elements) {
    if (!el.name) continue;
    if (SECRET.includes(el.name)) {
      const v = settings[el.name] || {};
      el.value = '';
      el.placeholder = v.set ? `已保存（${v.hint}），不改就留空` : (el.name === 'deepseek_api_key' ? 'sk-...' : '');
      const clr = $(`[data-clear="${el.name}"]`, form);
      if (clr) clr.hidden = !v.set;
    } else {
      el.value = settings[el.name] || '';
    }
  }
  $$('[data-ready]', form).forEach((t) => {
    const on = t.dataset.ready === 'llm' ? settings.llm_ready : settings.asr_ready;
    t.className = 'tag ' + (on ? 'on' : 'off');
    t.textContent = on ? '已配置' : '未配置';
  });
}

function formValues() {
  const body = {};
  for (const el of form.elements) if (el.name) body[el.name] = el.value.trim();
  return body;
}

async function saveSettings(extra) {
  const wasReady = settings && settings.llm_ready;
  settings = await api('POST', '/api/settings', { json: Object.assign(formValues(), extra || {}) });
  fillSettingsForm();
  renderStatusLine();
  if (S) {
    renderRowsKeepScroll();
    if (!wasReady && settings.llm_ready) understandMissing();
  }
}

function renderRowsKeepScroll() {
  const y = window.scrollY;
  renderRows();
  autoGrowAll();
  window.scrollTo(0, y);
}

document.addEventListener('click', async (e) => {
  if (e.target.closest('#btn-settings') || e.target.closest('[data-open-settings]')) {
    e.preventDefault();
    await loadSettings();
    fillSettingsForm();
    $$('.test-result', form).forEach((x) => { x.textContent = ''; x.className = 'test-result'; });
    dlg.showModal();
  }
});
$('#settings-close').addEventListener('click', () => dlg.close());
$('#settings-save').addEventListener('click', async () => {
  try { await saveSettings(); toast('设置已保存'); dlg.close(); } catch (e) { toast(e.message, true); }
});
form.addEventListener('click', async (e) => {
  const clr = e.target.closest('[data-clear]');
  if (clr) {
    if (!confirm('清除这个已保存的密钥？')) return;
    try { await saveSettings({ clear: [clr.dataset.clear] }); toast('已清除'); } catch (err) { toast(err.message, true); }
    return;
  }
  const test = e.target.closest('[data-test]');
  if (test) {
    const which = test.dataset.test;
    const out = $(`[data-result="${which}"]`, form);
    out.className = 'test-result';
    out.innerHTML = '<span class="spin"></span> 测试中…';
    try {
      await saveSettings();
      const r = await api('POST', '/api/settings/test', { json: { which } });
      out.className = 'test-result ok';
      out.textContent = '✓ ' + r.message;
    } catch (err) {
      out.className = 'test-result err';
      out.textContent = '✗ ' + err.message;
    }
  }
});

// ---------------------------------------------------------------------------

route();
