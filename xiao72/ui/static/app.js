/* 小72 监控窗口：SSE 接事件，负责渲染。 */
(() => {
  const $ = (id) => document.getElementById(id);
  const orb = $('orb'), hint = $('hint'), turns = $('turns');
  const wave = $('wave'), ctx = wave.getContext('2d');
  const meterFill = $('meterFill'), led = $('led'), ledText = $('ledText');

  let level = 0;                  // 0..1 平滑音量：只决定「多高」，不决定「往哪走」
  let rafId = null;
  let typing = null;              // {finish()}
  let state = 'idle';
  let W = 0, H = 0;               // 画布逻辑尺寸（由 CSS 决定，JS 只读取）

  // 画布的像素尺寸跟着 CSS 走：改 --orb-w/--orb-h 不用动这里
  // 注意：必须用 clientWidth（布局尺寸），不能用 getBoundingClientRect
  //       ——后者会把 transform 缩放算进去，画布跟着环缩放时会二次缩放
  function fitCanvas() {
    const dpr = window.devicePixelRatio || 1;
    W = Math.max(40, wave.clientWidth || wave.offsetWidth);
    H = Math.max(20, wave.clientHeight || wave.offsetHeight);
    wave.width = Math.round(W * dpr);
    wave.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  window.addEventListener('resize', fitCanvas);

  // 三层：主线红，左灰，右绿；各自独立，不叠加成一条
  // 颜色全部来自 theme.css，这里只取 RGB 分量（canvas 需要 rgba）
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // 数组顺序 = 绘制顺序：先画的在底层，后画的在顶层
  //   → 绿（底）→ 灰（中）→ 红（顶）
  // delay 是各层相位错开量：0 / 2.1 / 4.2 ≈ 均分一个周期
  const PEAKS = [
    { c: 0.75, k: 0.30, rgb: cssVar('--c-green-rgb'),  fill: 0.08, line: 0.85, delay: 0.0 },  // 绿（最底层）
    { c: 0.25, k: 0.30, rgb: cssVar('--c-gray-rgb'),   fill: 0.10, line: 0.80, delay: 2.1 },  // 灰（中层）
    { c: 0.50, k: 1.00, rgb: cssVar('--c-accent-rgb'), fill: 0.12, line: 0.95, delay: 4.2 },  // 红（最顶层）
  ];
  const SIGMA = 0.11;             // 峰的胖瘦（相对画布宽）
  const PAD_X = 0, PAD_Y = 14;    // 横向不留白：波形宽度 = 胶囊宽度
  let phase = 0;                  // 涌动相位

  // 涌动：一条长周期正弦，横向缓慢推进。
  // 峰值 = SURGE_AMP × amp × 该层波峰系数 p.k
  const SURGE_AMP = 0.16;         // 涌动幅度（相对 amp）
  const SURGE_WAVE = 1.30;        // 波长（相对画布宽，>1 表示一个屏里不足一个完整波）
  const SURGE_SPEED = 0.022;      // 每帧相位增量（80ms/帧 → 约 22 秒走完一圈）

  function draw() {
    const w = W, h = H;
    if (!w || !h) return;
    const mid = h * 0.5;
    const amp = Math.min(h * 0.34, (h * 0.5 - PAD_Y) / (1 + SURGE_AMP));
    const innerW = Math.max(1, w - PAD_X * 2);
    ctx.clearRect(0, 0, w, h);

    const base = Math.pow(Math.max(0, Math.min(1, level)), 0.55);   // 感知压缩

    const N = 96;
    const path = (pts, reverse) => {
      const p = reverse ? pts.slice().reverse() : pts;
      ctx.moveTo(p[0][0], p[0][1]);
      for (let i = 1; i < p.length - 1; i++) {
        const xc = (p[i][0] + p[i + 1][0]) / 2;
        const yc = (p[i][1] + p[i + 1][1]) / 2;
        ctx.quadraticCurveTo(p[i][0], p[i][1], xc, yc);
      }
      ctx.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
    };

    // 逐个峰独立绘制：先填带子，再描上下两条边
    for (const p of PEAKS) {
      const s = base;

      const top = [], bot = [];
      for (let i = 0; i <= N; i++) {
        const xn = i / N;
        const d = xn - p.c;

        // ① 自己的形状（高斯带，随音量升降）
        const body = p.k * Math.exp(-(d * d) / (2 * SIGMA * SIGMA)) * s * amp;

        // ② 叠一条非匀速的涌波：相位和波长都在缓慢漂移，所以周期不固定
        const t = phase * SURGE_SPEED;
        const ph = t + p.delay + 0.55 * Math.sin(t * 0.11 + p.delay * 0.6);
        const lam = SURGE_WAVE * (1 + 0.22 * Math.sin(t * 0.07 + p.delay));
        const swell = Math.sin(xn / lam * Math.PI * 2 - ph) * SURGE_AMP * amp * p.k;

        const x = PAD_X + xn * innerW;
        top.push([x, mid - body - swell]);
        bot.push([x, mid + body * 0.42 - swell]);   // 下沿短，整体随 swell 平移
      }

      ctx.beginPath();
      path(top, false);
      path(bot, true);
      ctx.closePath();
      ctx.fillStyle = `rgba(${p.rgb},${p.fill})`;
      ctx.fill();

      ctx.lineWidth = 2;                      // 三层线宽统一
      ctx.lineCap = 'round';
      ctx.strokeStyle = `rgba(${p.rgb},${p.line})`;
      ctx.beginPath(); path(top, false); ctx.stroke();
      ctx.beginPath(); path(bot, false); ctx.stroke();
    }
  }

  function pushLevel(v) {
    level = Math.max(v, level * 0.86);        // 起得快，落得慢
  }
  // 常驻重绘：涌动需要连续帧；没有新电平时 level 自然回落
  setInterval(() => {
    phase += 1;
    if (level > 0.002) level *= 0.90;
    draw();
  }, 80);
  fitCanvas();

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
    if (v === 'thinking') { level = 0; draw(); }
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
