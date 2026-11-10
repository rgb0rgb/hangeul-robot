/* 새 판 알림과 허락받은 업데이트 — 콘솔(updater.py)이 확인·검증·적용한다.
 * 사람이 [지금 업데이트]를 누르고 확인하기 전에는 아무것도 받지 않는다.
 * 순서 실행·반복 작업 중에는 막는다(화면 쪽 실행은 콘솔이 모르므로 여기서 알려 준다). */
(function () {
  var banner = document.getElementById('s-update-banner');
  if (!banner) return;
  var shown = null;      // 지금 띄운 판

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function screenRunning() {
    return !!(window.state && window.state.running);
  }

  function ask(message, title) {
    if (window.styledConfirm) return window.styledConfirm(message, title, true);
    return Promise.resolve(window.confirm(message));
  }

  function tell(message) {
    if (window.alertOrStyled) return window.alertOrStyled(message);
    window.alert(message);
  }

  function render(s) {
    if (!s || !s.available || s.dismissed || !s.latest) {
      banner.hidden = true;
      shown = null;
      return;
    }
    if (shown === s.latest.version && !banner.hidden) return;
    shown = s.latest.version;
    banner.innerHTML = '';
    banner.appendChild(el('span', 's-update-text',
      '새 판 ' + s.latest.version + '이 있습니다 (지금 ' + s.current + ')'));
    if (s.latest.safety_change) {
      banner.appendChild(el('span', 's-update-safety', '안전 동작이 바뀌는 판 — 바뀐 것을 꼭 읽으세요'));
    }
    var notes = el('pre', 's-update-notes', (s.latest.notes_ko ? s.latest.notes_ko + '\n\n' : '') +
      (s.latest.notes_en || ''));
    notes.hidden = true;
    var more = el('button', 's-btn s-btn-ghost s-update-btn', '바뀐 것 보기');
    more.onclick = function () { notes.hidden = !notes.hidden; };
    banner.appendChild(more);
    if (s.can_apply) {
      var go = el('button', 's-btn s-btn-primary s-update-btn', '지금 업데이트');
      go.onclick = function () { apply(s, go); };
      banner.appendChild(go);
    } else {
      banner.appendChild(el('span', 's-update-hint', '이 사본은 git으로 받은 것입니다 — git pull로 받으세요'));
    }
    var later = el('button', 's-btn s-btn-ghost s-update-btn', '나중에');
    later.onclick = function () {
      fetch('/api/update/dismiss', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: s.latest.version }) }).then(function () { banner.hidden = true; });
    };
    banner.appendChild(later);
    banner.appendChild(notes);
    banner.hidden = false;
  }

  function apply(s, button) {
    if (screenRunning()) {
      tell('순서를 실행하는 중입니다. 끝나거나 멈춘 뒤에 업데이트하세요.');
      return;
    }
    if (s.busy_reasons && s.busy_reasons.length) {
      tell('로봇이 일하는 중이라 업데이트하지 않습니다: ' + s.busy_reasons.join(', '));
      return;
    }
    var lines = ['한글 로봇을 ' + s.current + '에서 ' + s.latest.version + '(으)로 업데이트합니다.', '',
      '· 로봇 프로그램이 잠시 꺼졌다가 1~2분 안에 다시 켜집니다.',
      '· 등록한 로봇·가르친 자세·안전 범위는 그대로 남습니다.',
      '· 로봇이 멈춰 있고 주변에 사람이 없는지 확인하세요.'];
    if (s.latest.safety_change) {
      lines.push('', '이 판은 안전 동작이 바뀝니다. [바뀐 것 보기]를 먼저 읽으세요.');
    }
    ask(lines.join('\n'), '업데이트').then(function (ok) {
      if (!ok) return;
      button.disabled = true;
      fetch('/api/update/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true, operator: 'screen', screen_running: screenRunning() }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.success) {
            button.disabled = false;
            tell(d.error || '업데이트하지 못했습니다');
            return;
          }
          follow(s.latest.version, d.message);
        })
        .catch(function () { button.disabled = false; tell('업데이트 요청을 보내지 못했습니다'); });
    });
  }

  // 받기 → 설치(콘솔이 꺼진다) → 다시 켜짐. 새 판으로 답하면 화면을 새로 연다.
  function follow(version, message) {
    banner.innerHTML = '';
    var line = el('span', 's-update-text', message);
    banner.appendChild(line);
    banner.hidden = false;
    var started = Date.now();
    var timer = setInterval(function () {
      fetch('/api/update/status').then(function (r) { return r.json(); }).then(function (s) {
        if (s.current === version) {
          clearInterval(timer);
          line.textContent = '업데이트를 마쳤습니다 — 화면을 새로 엽니다';
          setTimeout(function () { window.location.reload(); }, 1500);
        } else if (s.phase === 'idle' && s.reason && Date.now() - started > 5000) {
          clearInterval(timer);
          line.textContent = '업데이트하지 못했습니다: ' + s.reason;
        } else if (s.phase === 'downloading') {
          line.textContent = '새 판을 받고 검증하는 중입니다…';
        }
      }).catch(function () {
        line.textContent = '설치하는 중입니다. 다시 켜지면 화면이 저절로 새로 열립니다…';
        if (Date.now() - started > 10 * 60 * 1000) {
          clearInterval(timer);
          line.textContent = '10분이 지나도 다시 켜지지 않았습니다. 바탕화면의 [한글 로봇]을 눌러 주세요.';
        }
      });
    }, 3000);
  }

  function load() {
    fetch('/api/update/status').then(function (r) { return r.json(); }).then(render).catch(function () {});
  }
  load();
  setInterval(load, 30 * 60 * 1000);   // 콘솔은 하루 한 번 확인한다 — 화면은 가끔 물어보기만 한다
})();
