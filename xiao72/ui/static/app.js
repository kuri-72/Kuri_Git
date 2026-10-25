/* 小72 监控窗口：SSE 接事件，负责渲染。 */
(() => {
  const $ = (id) => document.getElementById(id);
  const orb = $('orb'), hint = $('hint'), turns = $('turns');
  const wave = $('wave'), ctx = wave.getContext('2d');
  const meterFill = $('meterFill'), led = $('led'), ledText = $('ledText');

  let levels = new Array(48).fill(0);
  let rafId = null;
  let typing = null;              // {finish()}
  let state = 'idle';

  // ---------------- 波形 ----------------
  function draw() {
    const w = wave.width, h = wave.height, n = levels.length;
    const bw = w / n;
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < n; i++) {
      const v = Math.max(0.04, levels[i]);
      const bh = Math.min(h - 8, v * h * 1.5);
      const x = i * bw + bw * 0.2;
      const y = (h - bh) / 2;
      ctx.fillStyle = state === 'recording' ? '#248A3D' : '#C7C7CC';
      ctx.beginPath();
      const r = Math.min(bw * 0.3, 2);
      roundRect(ctx, x, y, bw * 0.6, bh, r);
      ctx.fill();
    }
  }
  function roundRect(c, x, y, w, h, r) {
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  function pushLevel(v) {
    levels.push(v); levels.shift();
    if (!rafId) rafId = requestAnimationFrame(() => { rafId = null; draw(); });
  }
  // 静音时也让波形轻微呼吸，避免看起来像死了
  setInterval(() => {
    if (state === 'recording' || state === 'waiting') {
      levels = levels.map((v) => v * 0.92);
      pushLevel(0.02 + Math.random() * 0.02);
    }
  }, 90);
  draw();

  // ---------------- 状态 ----------------
  const HINTS = {
    idle: '', waiting: '按住空格说话', recording: '正在录音…',
    thinking: '识别中…', speaking: '播报中 · 按空格打断', cancelled: '已取消',
  };
  function setState(v) {
    state = v;
    orb.className = 'orb ' + v;
    hint.textContent = HINTS[v] || '';
    hint.classList.toggle('active', v === 'recording');
    if (v === 'idle' && typing) typing.finish();
    if (v === 'thinking') { levels = levels.map(() => 0); draw(); }
  }

  // ---------------- 文本 ----------------
  function addTurn(who, text, cls) {
    const el = document.createElement('div');
    el.className = 'turn ' + (cls || '');
    const w = document.createElement('div'); w.className = 'who'; w.textContent = who;
    const t = document.createElement('div'); t.className = 'text';
    el.append(w, t);
    turns.prepend(el);
    while (turns.children.length > 8) turns.lastChild.remove();
    return t;
  }

  function typewrite(el, text) {
    let i = 0, timer = null;
    el.textContent = '';
    const finish = () => {
      if (timer) clearInterval(timer);
      timer = null; el.textContent = text; typing = null;
    };
    typing = { finish };
    timer = setInterval(() => {
      i += 2;
      if (i >= text.length) { finish(); return; }
      el.textContent = text.slice(0, i);
      el.scrollIntoView({ block: 'nearest' });
    }, 45);
  }

  function setInstant(el, text) { el.textContent = text; }

  // ---------------- 指标 ----------------
  function setLed(brightness, period) {
    const n = Math.round(brightness / 10);
    [...led.children].forEach((s, i) => s.classList.toggle('on', i < n));
    ledText.textContent = brightness + '%' + (period ? ' · 呼吸 ' + (period / 1000) + 's' : '');
  }

  // ---------------- SSE ----------------
  let lastReplyEl = null;
  function connect() {
    const es = new EventSource('/events');
    es.onmessage = (m) => {
      let e; try { e = JSON.parse(m.data); } catch { return; }
      switch (e.t) {
        case 'state': setState(e.v); break;
        case 'level':
          pushLevel(e.v);
          meterFill.style.width = Math.min(100, e.v * 160) + '%';
          break;
        case 'asr':
          if (e.text) typewrite(addTurn('你说', '', 'me'), e.text);
          $('mAsr').textContent = e.secs + 's';
          $('mAudio').textContent = e.audio_s + 's';
          break;
        case 'reply': {
          const cls = e.cmd === 'unknown' ? 'err' : '';
          lastReplyEl = addTurn('小72', '', cls);
          if (e.text) typewrite(lastReplyEl, e.text); else setInstant(lastReplyEl, '(未发送)');
          break;
        }
        case 'metrics':
          $('mIntent').textContent = e.intent + 's';
          $('mTotal').textContent = e.total + 's';
          $('mTts').textContent = Math.max(0, e.total - e.intent - e.asr).toFixed(1) + 's';
          break;
        case 'led': setLed(e.brightness, e.period); break;
        case 'serial': $('mPort').textContent = e.port || '未连接'; break;
        case 'stats': $('mTurns').textContent = e.turns + ' 轮'; break;
        case 'toast': toast(e.text); break;
      }
    };
    es.onerror = () => { es.close(); setTimeout(connect, 1200); };
  }
  connect();

  function toast(text) {
    const t = $('toast');
    t.textContent = text; t.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove('show'), 1800);
  }

  // ---------------- 空格：处理中抖动 ----------------
  document.addEventListener('keydown', (ev) => {
    if (ev.code !== 'Space') return;
    const tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;   // 输入框里不劫持
    ev.preventDefault();
    if (state === 'thinking' || state === 'speaking' && false) {
      orb.classList.remove('shake');
      void orb.offsetWidth;
      orb.classList.add('shake');
    }
  }, { passive: false });

  // ---------------- 设置抽屉 ----------------
  const drawer = $('drawer'), scrim = $('scrim');
  function openDrawer() {
    fetch('/api/settings').then(r => r.json()).then((d) => {
      $('rate').value = d.rate;
      $('vol').value = d.volume;
      $('rateVal').textContent = (d.rate >= 0 ? '+' : '') + d.rate + '%';
      $('volVal').textContent = (d.volume >= 0 ? '+' : '') + d.volume + '%';
      const sel = $('voice'); sel.innerHTML = '';
      d.voices.forEach((v) => {
        const o = document.createElement('option');
        o.value = v.id; o.textContent = v.name;
        if (v.id === d.settings.tts_voice) o.selected = true;
        sel.appendChild(o);
      });
    });
    drawer.classList.add('open'); scrim.classList.add('show');
  }
  function closeDrawer() { drawer.classList.remove('open'); scrim.classList.remove('show'); }

  $('gear').onclick = openDrawer;
  $('closeDrawer').onclick = closeDrawer;
  scrim.onclick = closeDrawer;

  $('rate').oninput = (e) => {
    const v = Number(e.target.value);
    $('rateVal').textContent = (v >= 0 ? '+' : '') + v + '%';
  };
  $('vol').oninput = (e) => {
    const v = Number(e.target.value);
    $('volVal').textContent = (v >= 0 ? '+' : '') + v + '%';
  };

  $('save').onclick = () => {
    const body = {
      tts_rate: (Number($('rate').value) >= 0 ? '+' : '') + $('rate').value + '%',
      tts_volume: (Number($('vol').value) >= 0 ? '+' : '') + $('vol').value + '%',
      tts_voice: $('voice').value,
    };
    fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(r => r.json()).then(() => closeDrawer());
  };

  setState('waiting');
})();
