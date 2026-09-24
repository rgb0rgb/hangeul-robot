(function () {
  'use strict';

  var uiLang = localStorage.getItem('dexterUiLang') === 'en' ? 'en' : 'ko';
  var selectedRobotId = null;
  var robotTypes = [];
  var robotTypeLabels = {};      // 부품 번호 → 사람이 읽는 이름
  // 로봇 추가의 모델 격자와 줄마다 있는 '로봇 선택'은 **같은 목록 하나**를 쓴다.
  // 두 곳이 따로 목록을 만들면 한쪽에만 있는 팔이 생긴다.
  var robotTypeCards = [];
  var gridBody = document.getElementById('hangeul-grid-body');
  var addBtn = document.getElementById('hangeul-add-robot');
  var removeBtn = document.getElementById('hangeul-remove-robot');

  if (!gridBody) return;

  var NONE_LABEL = uiLang === 'en' ? 'none' : '없음';
  var PLACEHOLDER_LABEL = uiLang === 'en' ? '-Select-' : '-선택하세요-';

  // ── 정적 텍스트 다국어 사전 (그리드/툴바 전용 — simple.js의 사전과 별개) ──
  var HANGEUL_STATIC_I18N = {
    ko: {
      panelTitle: '로봇 목록',
      emptyTitle: '아직 등록된 로봇이 없습니다',
      emptyBody: '위의 [추가] 를 눌러 부품을 골라 로봇 한 대를 만드세요.\n실물이 없어도 만들 수 있습니다 — 화면은 그대로 뜨고 실행만 막힙니다.',
      addModalTitle: '➕ 로봇 추가',
      addModalSubtitle: '이름을 적고, 어떤 팔인지 고르세요.',
      addNameLabel: '로봇 이름',
      addNamePlaceholder: '비우면 자동으로 이름을 붙입니다',
      addPickLabel: '어떤 팔인가요',
      addCancel: '취소',
      addConfirm: '만들기',
      addNoModels: '고를 수 있는 팔 기술서가 없습니다.',
      addBtn: '추가',
      removeBtn: '삭제',
      resetWidthsBtn: '열정리',
      addRobotTitle: '로봇 추가',
      removeRobotTitle: '체크한 로봇 삭제 (정확히 1대만 체크) — 또는 행 오른쪽 끝의 [삭제] 사용',
      resetWidthsTitle: '열 너비를 기본값으로 되돌립니다',
      execBtn: '▶ 실행 시작',
      execTitle: '체크한 로봇들의 저장된 실행 순서를 함께 실행합니다 (안전 확인 후)',
      cancelBtn: '⏹ 예약 취소',
      cancelTitle: '예약/진행 중인 다중 실행을 모두 취소합니다',
      resetBtn: '🔄 초기화',
      checkBtn: '🔧 상태점검',
      checkTitle: '체크한 로봇들을 한 대씩 조금 움직여 보고 부품마다 이상 여부를 알려 줍니다 (안전 확인 후)',
      checkNone: '점검할 로봇을 먼저 체크하세요.',
      resetTitle: '완료/실패/취소된 다중 실행 표시와 체크박스/예약 시각을 처음 상태로 되돌리고, 모든 로봇의 상태 표시를 대기로 되돌립니다',
      colName: '로봇', colStatus: '상태', colTime: '시간', colAttach: '로봇 선택', colClear: '로봇 순서', colDelete: '삭제',
      checkAllTitle: '전체 선택/해제',
      hint: '체크한 로봇을 함께 실행합니다. 시간(24시간제)을 지정하면 그 시각에 예약 실행되고, 비워 두면 즉시 실행됩니다. 로봇 이름을 더블클릭하면 이름을 바로 바꿀 수 있습니다.',
      assignModalTitle: '🗹 지정하기 — 대상 로봇 선택',
      assignModalSubtitle: '현재 담은 동작 순서를 어느 로봇의 실행 순서로 즉시 지정할지 고르세요. 이름은 남기지 않으며 1회성입니다.',
      assignCancel: '취소',
      assignConfirm: '이 로봇으로 지정',
      settingsHelpBtn: '도움말',
      settingsHelpTitle: '환경 설정 도움말',
      settingsHelpText:
        '화면 배경: 눈에 편한 색 테마를 고릅니다. 로봇 동작에는 영향을 주지 않습니다.\n\n' +
        '화면 크기: 작업 화면의 폭을 바꿉니다. 작은 화면에서는 좁게, 큰 모니터에서는 넓게 쓰면 됩니다.\n\n' +
        '부재 모드: 자리를 비우거나 졸릴 때 켭니다. 켜져 있는 동안 이동/실행 요청을 막는 안전 잠금입니다.\n\n' +
        '안전 범위 설정: 선택한 로봇의 관절 최소/최대 범위, 온도 정지 기준, 동작 속도를 정합니다. 처음에는 기본값을 유지하고, 실제 로봇 검증 후 조금씩 조정하세요.\n\n' +
        '자세와 운용: 자세는 관절 숫자 묶음입니다. 기본자세는 작업 시작 기준, Rest/Park는 작업 종료 후 세워두는 자세입니다. 물체를 집을 때는 물체 위 -> 잡기 위치 -> 들어올림처럼 안전한 중간 자세를 나눠 저장하세요.\n\n' +
        '서버 재시작: 화면이나 로봇 노드가 꼬였을 때 서버 프로세스를 다시 시작합니다. 실행 중인 동작이 없을 때 사용하세요.\n\n' +
        '보안 모니터링: 차단·정지 기록을 모아 봅니다. 안 시킨 차단이 쌓여 있으면 로봇을 멈추고 기록을 확인하세요.',
      saveNameGuide: '좋은 이름 예: 기본자세, 물체 위, 잡기 위치, 들어올림, 오른쪽 놓기. 숫자만 있는 이름은 나중에 순서를 확인하기 어렵습니다.',
      adminRangeGuide: '선택한 로봇의 관절별 측정 안전 범위와 단위로 제한합니다. MyCobot은 J1~J6 각도(도), J7 손 퍼센트이며 J4도 정상적으로 표시합니다.',
      statusLoadFail: '상태 로드 실패: ',
    },
    en: {
      panelTitle: 'Robot List',
      emptyTitle: 'No robot registered yet',
      emptyBody: 'Press [Add] above and pick the parts to build one.\nYou can do this without hardware — the screen still works, only motion is blocked.',
      addModalTitle: '➕ Add Robot',
      addModalSubtitle: 'Give it a name, then pick which arm it is.',
      addNameLabel: 'Robot name',
      addNamePlaceholder: 'Leave blank to name it automatically',
      addPickLabel: 'Which arm is it?',
      addCancel: 'Cancel',
      addConfirm: 'Create',
      addNoModels: 'No arm descriptor available to pick from.',
      addBtn: 'Add',
      removeBtn: 'Delete',
      resetWidthsBtn: 'Fit Columns',
      addRobotTitle: 'Add robot',
      removeRobotTitle: 'Delete checked robot (check exactly one) — or use [Delete] at the end of a row',
      resetWidthsTitle: 'Reset column widths to default',
      execBtn: '▶ Start',
      execTitle: 'Run the saved sequences of checked robots together (after safety confirmation)',
      cancelBtn: '⏹ Cancel Schedule',
      cancelTitle: 'Cancel all scheduled/in-progress multi-runs',
      resetBtn: '🔄 Reset',
      checkBtn: '🔧 Status check',
      checkTitle: 'Moves each checked robot a little, one at a time, and reports on every part (after safety confirmation)',
      checkNone: 'Check at least one robot first.',
      resetTitle: "Reset finished multi-run markers, checkboxes, scheduled times, and every robot's status back to idle",
      colName: 'Robot', colStatus: 'Status', colTime: 'Time', colAttach: 'Robot Type', colClear: 'Run Order', colDelete: 'Delete',
      checkAllTitle: 'Select/deselect all',
      hint: 'Runs checked robots together. Set a time (24h) to schedule, or leave blank to start immediately. Double-click a robot name to rename it.',
      assignModalTitle: '🗹 Assign — Choose Target Robot',
      assignModalSubtitle: 'Choose which robot should get the current queue as its run order right now. Unnamed, one-time only.',
      assignCancel: 'Cancel',
      assignConfirm: 'Assign to this robot',
      settingsHelpBtn: 'Help',
      settingsHelpTitle: 'Settings Help',
      settingsHelpText:
        'Theme: Changes the UI colors only. It does not affect robot motion.\n\n' +
        'Width: Changes the work area width. Use a narrower layout on small screens and a wider one on large monitors.\n\n' +
        'Away mode: Turn this on before leaving the station. Motion and run requests are blocked while it is on.\n\n' +
        'Safety limits: Sets joint ranges, temperature thresholds, and motion speed for the selected robot. Keep defaults first, then adjust only after hardware validation.\n\n' +
        'Pose and operation: A pose is a bundle of joint numbers. The default pose is the work-start reference, while Rest/Park is the after-work holding pose. For picking, save safe intermediate poses such as above object -> grasp point -> lift.\n\n' +
        'Server restart: Restarts the server process when the UI or robot node is stuck. Use it when no motion is running.\n\n' +
        'Security monitoring: Collects blocked and stop events. If blocks you did not cause pile up, stop the robot and read the log.',
      saveNameGuide: 'Good names: default pose, above object, grasp point, lift, place right. Number-only names make run orders hard to review later.',
      adminRangeGuide: 'Values are limited by the selected robot’s measured joint ranges and units. MyCobot uses degrees for J1–J6 and percent for J7; J4 remains displayed normally.',
      statusLoadFail: 'Failed to load status: ',
    }
  };

  function hi18n() {
    return HANGEUL_STATIC_I18N[uiLang] || HANGEUL_STATIC_I18N.ko;
  }

  function applyHangeulStaticI18n() {
    var d = hi18n();
    function setText(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }
    function setTitle(id, text) { var el = document.getElementById(id); if (el) el.title = text; }
    setText('hangeul-panel-title', d.panelTitle);
    setText('add-robot-title', d.addModalTitle);
    setText('add-robot-subtitle', d.addModalSubtitle);
    setText('lbl-add-robot-name', d.addNameLabel);
    setText('lbl-add-robot-pick', d.addPickLabel);
    setText('btn-add-robot-cancel', d.addCancel);
    setText('btn-add-robot-confirm', d.addConfirm);
    var addNameEl = document.getElementById('add-robot-name');
    if (addNameEl) addNameEl.placeholder = d.addNamePlaceholder;
    setText('hangeul-add-robot', d.addBtn);
    setTitle('hangeul-add-robot', d.addRobotTitle);
    setText('hangeul-remove-robot', d.removeBtn);
    setTitle('hangeul-remove-robot', d.removeRobotTitle);
    setText('hangeul-reset-col-widths', d.resetWidthsBtn);
    setTitle('hangeul-reset-col-widths', d.resetWidthsTitle);
    setText('hangeul-multi-execute', d.execBtn);
    setTitle('hangeul-multi-execute', d.execTitle);
    setText('hangeul-multi-cancel', d.cancelBtn);
    setTitle('hangeul-multi-cancel', d.cancelTitle);
    setText('hangeul-multi-reset', d.resetBtn);
    setTitle('hangeul-multi-reset', d.resetTitle);
    setText('hangeul-multi-check', d.checkBtn);
    setTitle('hangeul-multi-check', d.checkTitle);
    setText('hangeul-col-label-name', d.colName);
    setText('hangeul-col-label-status', d.colStatus);
    setText('hangeul-col-label-time', d.colTime);
    setText('hangeul-col-label-attach', d.colAttach);
    setText('hangeul-col-label-clear', d.colClear);
    setText('hangeul-col-label-delete', d.colDelete);
    setTitle('hangeul-check-all', d.checkAllTitle);
    setText('hangeul-multi-hint', d.hint);
    setText('btn-settings-help', d.settingsHelpBtn);
    setText('save-name-guide', d.saveNameGuide);
    setText('admin-range-guide', d.adminRangeGuide);
  }

  window.openHangeulSettingsHelp = function () {
    var d = hi18n();
    if (typeof styledAlert === 'function') {
      styledAlert(d.settingsHelpText, d.settingsHelpTitle);
    } else {
      alert(d.settingsHelpTitle + '\n\n' + d.settingsHelpText);
    }
  };

  // 2026-07-23: 범용 스타일 팝업(styledAlert/styledConfirm/styledPrompt)은
  // simple.js로 이전해 dexter_grid/hangeul 공용이 됐다 — 여기 있던 중복
  // 구현은 제거. simple.js가 먼저 로드되므로 전역 함수로 그대로 쓸 수 있다.

  function loadHangeulStatus() {
    fetch('/api/status')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        selectedRobotId = data.selected_robot_id || defaultRobotId(data.robots || []);
        renderRobotGrid(data.robots || []);
        updateProgressTicker(data.robots || []);
        anyMultiRunActive = (data.robots || []).some(function (robot) {
          return robot.multi_run && (robot.multi_run.state === 'running' || robot.multi_run.state === 'scheduled');
        });
        if (!anyMultiRunActive) multiPaused = false;   // 다 끝났으면 일시정지 표시도 정리
        if (typeof window.updatePauseBtn === 'function') window.updatePauseBtn();
        else updatePauseBtnForMulti();
      })
      .catch(function (error) {
        gridBody.textContent = hi18n().statusLoadFail + error.message;
      });
  }

  // ── '로봇 목록' 제목 옆 진행 상황 안내 ("로봇1이 실행 중입니다." →
  //    "로봇1 완료" → "로봇2가 실행 중입니다." 처럼 상태 전환을 문장으로 알림).
  //    3초 폴링 사이 짧은 실행은 '실행' 상태 자체를 놓칠 수 있으므로,
  //    '완료'로 바뀌는 전환은 직전 상태가 무엇이었든 항상 알린다.
  var progressTicker = document.getElementById('hangeul-progress-ticker');
  var previousSimpleStates = {};

  // 숫자로 끝나는 이름("로봇1", "로봇2"...)이 흔하므로, 마지막 글자를 실제
  // 한국어 발음의 받침 유무로 판정해 '이/가'를 자연스럽게 고른다.
  var DIGIT_HAS_BATCHIM = { '0': true, '1': true, '2': false, '3': true, '4': false,
    '5': false, '6': true, '7': true, '8': true, '9': false };

  function lastCharHasBatchim(text) {
    if (!text) return false;
    var ch = text.charAt(text.length - 1);
    if (DIGIT_HAS_BATCHIM.hasOwnProperty(ch)) return DIGIT_HAS_BATCHIM[ch];
    var code = text.charCodeAt(text.length - 1);
    if (code >= 0xAC00 && code <= 0xD7A3) return (code - 0xAC00) % 28 !== 0;
    return false;   // 영문 등 — 받침 없다고 가정
  }

  function withSubjectParticle(label) {
    return label + (lastCharHasBatchim(label) ? '이' : '가');
  }

  function updateProgressTicker(robots) {
    if (!progressTicker) return;
    var message = null;
    robots.forEach(function (robot) {
      var prev = previousSimpleStates[robot.robot_id];
      var cur = robot.simple_state;
      if (prev !== undefined && prev !== cur) {
        var label = uiLang === 'en' ? robot.robot_id : robot.display_name;
        if (cur === '실행') {
          message = uiLang === 'en' ? label + ' is running.' : withSubjectParticle(label) + ' 실행 중입니다.';
        } else if (cur === '완료') {
          message = uiLang === 'en' ? label + ' completed.' : label + ' 완료';
        } else if (prev === '실행' && cur === '대기') {
          message = uiLang === 'en' ? label + ' stopped.' : label + ' 정지됨';
        }
      }
      previousSimpleStates[robot.robot_id] = cur;
    });
    if (message) progressTicker.textContent = message;
  }

  function selectRobot(robotId) {
    if (!robotId || robotId === selectedRobotId) return;
    fetch('/api/robots/' + encodeURIComponent(robotId) + '/select', { method: 'POST' })
      .then(function (response) {
        if (!response.ok) {
          // 실행 중 전환 차단 등 — 사유를 보여주고 화면 선택을 원상 복구
          return response.json().then(function (data) {
            styledAlert(data.detail || (uiLang === 'en' ? 'Cannot switch robot.' : '로봇을 전환할 수 없습니다.'))
              .then(function () { loadHangeulStatus(); });
          });
        }
        // 로봇마다 각각 독립: 동작 목록/순서/안전범위/로그가 전부 해당
        // 로봇 파일로 바뀌어야 하므로 전체 화면을 다시 불러온다.
        window.location.reload();
      });
  }

  // ── 트리 그리드: 체크박스 + 접기/펼치기(현재 실행 순서) + 더블클릭 이름변경
  //    + 예약 시각 + 행 안의 선택 로봇(연결) 드롭다운 ──────────────────
  // 행 DOM은 로봇 구성(id 목록)이 바뀔 때만 새로 만든다 — 3초 폴링이 체크
  // 상태/입력 중인 시간 값/펼침 상태/포커스를 지우지 않게 하기 위함.
  var checkAllBox = document.getElementById('hangeul-check-all');
  var multiExecBtn = document.getElementById('hangeul-multi-execute');
  var multiCancelBtn = document.getElementById('hangeul-multi-cancel');
  var multiResetBtn = document.getElementById('hangeul-multi-reset');
  var rowCache = {};      // robot_id → {root, check, time, nameText, nameEdit, toggle, status, attach, children, expanded}
  var rowOrderKey = '';

  function renderRobotGrid(robots) {
    // 처음 받은 사람의 첫 화면 — 빈 표가 아니라 다음에 무엇을 누를지 적는다.
    // 등록된 로봇은 그 사람의 것이므로 출하물에는 한 대도 들어 있지 않다.
    if (!robots.length) {
      if (rowOrderKey !== '\u0000empty') {
        rowOrderKey = '\u0000empty';
        rowCache = {};
        gridBody.innerHTML = '';
        var empty = document.createElement('div');
        empty.className = 'hangeul-grid-empty';
        var title = document.createElement('div');
        title.className = 'hangeul-grid-empty-title';
        title.textContent = hi18n().emptyTitle;
        var body = document.createElement('div');
        body.className = 'hangeul-grid-empty-body';
        body.textContent = hi18n().emptyBody;
        empty.appendChild(title);
        empty.appendChild(body);
        gridBody.appendChild(empty);
      }
      return;
    }
    var key = robots.map(function (robot) { return robot.robot_id; }).join(',');
    if (key !== rowOrderKey) {
      rowOrderKey = key;
      var previous = rowCache;
      rowCache = {};
      gridBody.innerHTML = '';
      robots.forEach(function (robot) {
        var old = previous[robot.robot_id];
        rowCache[robot.robot_id] = buildRow(robot, old);
        gridBody.appendChild(rowCache[robot.robot_id].root);
      });
      syncCheckAllBox();
    }
    robots.forEach(function (robot) {
      updateRow(robot);
    });
  }

  function buildRow(robot, old) {
    var root = document.createElement('div');
    root.className = 'hangeul-grid-row';
    root.dataset.robotId = robot.robot_id;

    var main = document.createElement('div');
    main.className = 'hangeul-grid-row-main';

    var checkCell = document.createElement('span');
    checkCell.className = 'hangeul-grid-col hangeul-col-check';
    var check = document.createElement('input');
    check.type = 'checkbox';
    check.title = uiLang === 'en' ? 'Include in multi-robot run' : '다중 실행에 포함';
    if (old) check.checked = old.check.checked;
    check.addEventListener('click', function (e) { e.stopPropagation(); });
    check.addEventListener('change', syncCheckAllBox);
    checkCell.appendChild(check);

    var nameCell = document.createElement('span');
    nameCell.className = 'hangeul-grid-col hangeul-col-name';
    var toggle = document.createElement('span');
    toggle.className = 'hangeul-tree-toggle';
    toggle.textContent = '▸';
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleExpand(robot.robot_id);
    });
    var nameText = document.createElement('span');
    nameText.className = 'hangeul-row-name';
    nameText.title = uiLang === 'en' ? 'Click: select · Double-click: rename' : '클릭: 편집 대상 선택 · 더블클릭: 이름 변경';
    var nameEdit = document.createElement('input');
    nameEdit.type = 'text';
    nameEdit.className = 'hangeul-row-name-edit';
    nameEdit.style.display = 'none';
    // 더블클릭은 브라우저에서 click(1회)→click(2회)→dblclick 순으로 발생한다.
    // 클릭에 곧바로 selectRobot()을 붙이면, 아직 선택되지 않은 다른 로봇의
    // 이름을 더블클릭할 때 첫 클릭이 먼저 그 로봇을 선택(=새로고침)해버려
    // dblclick이 뜨기도 전에 페이지가 넘어가 이름 수정이 열리지 않았다
    // (사용자 보고로 발견). 표준 해법대로 클릭을 살짝 지연시켜, 그 사이에
    // 두 번째 클릭(dblclick)이 오면 선택 대신 이름 수정으로 처리한다.
    var pendingSelectTimer = null;
    nameText.addEventListener('click', function (e) {
      e.stopPropagation();
      if (pendingSelectTimer) return;
      pendingSelectTimer = setTimeout(function () {
        pendingSelectTimer = null;
        selectRobot(robot.robot_id);
      }, 280);
    });
    nameText.addEventListener('dblclick', function (e) {
      e.stopPropagation();
      if (pendingSelectTimer) {
        clearTimeout(pendingSelectTimer);
        pendingSelectTimer = null;
      }
      beginRename(robot.robot_id);
    });
    nameEdit.addEventListener('click', function (e) { e.stopPropagation(); });
    nameEdit.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') commitRename(robot.robot_id);
      if (e.key === 'Escape') cancelRename(robot.robot_id);
    });
    nameEdit.addEventListener('blur', function () { commitRename(robot.robot_id); });
    nameCell.appendChild(toggle);
    nameCell.appendChild(nameText);
    nameCell.appendChild(nameEdit);

    var statusCell = document.createElement('span');
    statusCell.className = 'hangeul-grid-col hangeul-col-status';
    var statusText = document.createElement('span');
    statusCell.appendChild(statusText);
    // 2026-07-23: 로봇을 전환하지 않아도 마지막 결과를 바로 볼 수 있게(로그
    // 패널은 로봇별로 전체 새로고침돼 전환할 때마다 흐름이 끊겼다).
    var lastResultText = document.createElement('span');
    lastResultText.className = 'hangeul-last-result';
    statusCell.appendChild(lastResultText);
    var multiSpan = document.createElement('span');
    multiSpan.className = 'hangeul-multi-state';
    statusCell.appendChild(multiSpan);

    var timeCell = document.createElement('span');
    timeCell.className = 'hangeul-grid-col hangeul-col-time';
    var time = document.createElement('input');
    time.type = 'time';
    // 시각 칸도 브라우저 지역 설정을 따라 '오전/오후'로 그려진다.
    // 화면 언어를 따르게 한다 (부재 모드 시각 칸과 같은 처리).
    time.lang = uiLang === 'ko' ? 'ko' : 'en-GB';
    time.className = 'hangeul-status-time';
    time.title = uiLang === 'en'
      ? 'Scheduled start time (24h). Empty = start now.'
      : '예약 실행 시각 (24시간제). 비우면 즉시 실행.';
    if (old) time.value = old.time.value;
    time.addEventListener('click', function (e) { e.stopPropagation(); });
    // 2026-07-23 (사용자 지적: 시간지우기는 시간 입력 옆에 있어야 함) — 지우기
    // 대상(시간 입력)과 같은 칸에, 작은 아이콘 버튼으로 붙여 둔다.
    var timeClearBtn = document.createElement('button');
    timeClearBtn.type = 'button';
    timeClearBtn.className = 'hangeul-time-clear-btn';
    timeClearBtn.textContent = '✕';
    timeClearBtn.title = uiLang === 'en'
      ? 'Clear the scheduled time (run immediately)'
      : '예약 시각을 지웁니다 (즉시 실행으로 전환)';
    timeClearBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      time.value = '';
    });
    timeCell.appendChild(time);
    timeCell.appendChild(timeClearBtn);

    var attachCell = document.createElement('span');
    attachCell.className = 'hangeul-grid-col hangeul-col-attach';
    var attach = document.createElement('select');
    attach.className = 'hangeul-attach-select';
    attach.addEventListener('click', function (e) { e.stopPropagation(); });
    attach.addEventListener('change', function () {
      attachRobotType(robot.robot_id, attach.value);
    });
    attachCell.appendChild(attach);

    var clearCell = document.createElement('span');
    clearCell.className = 'hangeul-grid-col hangeul-col-clear';
    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'hangeul-clear-btn';
    clearBtn.textContent = uiLang === 'en' ? 'Clear' : '지우기';
    clearBtn.title = uiLang === 'en'
      ? "Clear this robot's assigned run order back to default"
      : '이 로봇에 지정된 실행 순서를 지우고 기본 자세로 되돌립니다';
    clearBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      clearRobotSequence(robot.robot_id);
    });
    clearCell.appendChild(clearBtn);

    // 2026-07-23: 행마다 바로 삭제 — 체크박스+툴바 조합 없이도 이 로봇 하나만
    // 확실하게 지울 수 있다(다중실행 체크박스와 기능이 겹치던 문제 해소).
    var deleteCell = document.createElement('span');
    deleteCell.className = 'hangeul-grid-col hangeul-col-delete';
    var deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'hangeul-row-delete-btn';
    deleteBtn.textContent = hi18n().colDelete;
    deleteBtn.title = uiLang === 'en' ? 'Delete this robot' : '이 로봇 삭제';
    deleteBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      deleteRobot(robot.robot_id);
    });
    deleteCell.appendChild(deleteBtn);

    main.appendChild(checkCell);
    main.appendChild(nameCell);
    main.appendChild(statusCell);
    main.appendChild(timeCell);
    main.appendChild(attachCell);
    main.appendChild(clearCell);
    main.appendChild(deleteCell);

    var children = document.createElement('div');
    children.className = 'hangeul-grid-children';
    children.style.display = 'none';

    root.appendChild(main);
    root.appendChild(children);

    return {
      root: root, check: check, time: time, nameText: nameText, nameEdit: nameEdit,
      toggle: toggle, statusText: statusText, lastResultText: lastResultText, multiSpan: multiSpan, attach: attach,
      children: children, expanded: false, editing: false,
      // 콘솔이 준 원본. 어느 런타임을 보는지 등 행이 스스로 답해야 할 것이 여기 있다.
      robot: robot,
    };
  }

  function updateRow(robot) {
    var cache = rowCache[robot.robot_id];
    if (!cache) return;
    cache.robot = robot;
    cache.root.classList.toggle('hangeul-row-selected', robot.robot_id === selectedRobotId);
    if (!cache.editing) {
      cache.nameText.textContent = uiLang === 'en' ? robot.robot_id : robot.display_name;
    }
    // 상태 낱말은 콘솔이 두 말로 준다. 화면이 한글을 그대로 그리면
    // 영어로 바꿔도 '대기·완료'가 한글로 남는다.
    var stateWords = robot.simple_state_i18n || {};
    cache.statusText.textContent = stateWords[uiLang] || robot.simple_state || '';
    // 실제 로봇이 움직이는 동안('실행') 상태 글씨를 깜박여 눈에 띄게 한다.
    cache.statusText.classList.toggle('hangeul-status-running', robot.simple_state === '실행');
    if (cache.lastResultText) {
      if (robot.last_error) {
        cache.lastResultText.textContent = (uiLang === 'en' ? 'Last: error / ' : '마지막: 오류 / ') + robot.last_error;
        cache.lastResultText.classList.add('hangeul-last-result-error');
      } else if (robot.last_result) {
        cache.lastResultText.textContent = (uiLang === 'en' ? 'Last: ' : '마지막: ') + robot.last_result;
        cache.lastResultText.classList.remove('hangeul-last-result-error');
      } else {
        cache.lastResultText.textContent = '';
        cache.lastResultText.classList.remove('hangeul-last-result-error');
      }
    }
    cache.multiSpan.textContent = multiStateLabel(robot.multi_run);
    renderAttachSelect(cache.attach, robot.attached_robot);
    cache.lastSteps = robot.sequence_steps || [];
    if (cache.expanded) renderChildren(cache);
  }

  // 그리드 행의 '지우기' — 그 로봇의 지정된 실행 순서를 비우고 기본 자세로
  // (백엔드가 '기본자세' 동작을 찾으면 실제로 그 자세 1단계로 지정, 없으면
  // 완전히 빈 상태 — 응답의 default_pose_applied로 어느 쪽인지 알려준다).
  function clearRobotSequence(robotId) {
    var cache = rowCache[robotId];
    var label = cache ? cache.nameText.textContent : robotId;
    var message = uiLang === 'en'
      ? 'Clear the assigned run order for "' + label + '"? It will reset to the default pose.'
      : '"' + label + '"에 지정된 실행 순서를 지웁니까? 기본 자세로 되돌립니다.';
    styledConfirm(message, uiLang === 'en' ? 'Clear run order' : '실행 순서 지우기', true).then(function (ok) {
      if (!ok) return;
      fetch('/api/hangeul/clear-sequence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ robot_id: robotId })
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data.success) {
            styledAlert(data.error || (uiLang === 'en' ? 'Failed to clear.' : '지우기 실패'));
            return;
          }
          var note = data.default_pose_applied
            ? (uiLang === 'en' ? label + ': cleared — reset to default pose.' : label + ': 지우기 완료 (기본 자세로 되돌림)')
            : (uiLang === 'en' ? label + ': cleared (no default pose taught yet).' : label + ': 지우기 완료 (아직 기본자세를 가르치지 않음)');
          slogSafe(note, 's-log-info');
          loadHangeulStatus();
        });
    });
  }

  function renderAttachSelect(select, attached) {
    var desired = attached || '';
    if (select.dataset.rendered === '1' && select.dataset.attached === desired && select.dataset.lang === uiLang) return;
    select.innerHTML = '';
    if (!attached) {
      var placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = PLACEHOLDER_LABEL;
      placeholder.disabled = true;
      placeholder.selected = true;
      placeholder.hidden = true;
      select.appendChild(placeholder);
    }
    robotTypes.forEach(function (typeName) {
      var option = document.createElement('option');
      option.value = typeName;
      // 부품 번호(arm_mycobot)가 아니라 사람이 읽는 이름을 보인다.
      option.textContent = robotTypeLabels[typeName] || typeName;
      if (attached === typeName) option.selected = true;
      select.appendChild(option);
    });
    var noneOption = document.createElement('option');
    noneOption.value = '';
    noneOption.textContent = NONE_LABEL;
    select.appendChild(noneOption);
    select.dataset.rendered = '1';
    select.dataset.attached = desired;
    select.dataset.lang = uiLang;
  }

  function attachRobotType(robotId, typeValue) {
    fetch('/api/robots/' + encodeURIComponent(robotId) + '/attach', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: typeValue || null })
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          styledAlert(data.detail || (uiLang === 'en' ? 'Cannot change connection.' : '연결을 변경할 수 없습니다.'))
            .then(function () { loadHangeulStatus(); });
        });
      }
      // 고른 팔이 바뀌면 아래 '자세 만들기'의 관절 수·번호·단위가 통째로
      // 달라진다(OMX 4축 J11~J14 / MyCobot 6축 J1~J6). 목록만 다시 그리면
      // 아래 화면은 옛 팔의 관절을 그대로 들고 있다 — 사용자 보고.
      // 로봇 선택과 같은 처리를 한다: 화면 전체를 다시 불러온다.
      if (robotId === selectedRobotId) {
        window.location.reload();
        return;
      }
      var cache = rowCache[robotId];
      if (cache) cache.attach.dataset.rendered = '0';   // 강제 재렌더
      loadHangeulStatus();
    });
  }

  function toggleExpand(robotId) {
    var cache = rowCache[robotId];
    if (!cache) return;
    cache.expanded = !cache.expanded;
    cache.toggle.textContent = cache.expanded ? '▾' : '▸';
    cache.children.style.display = cache.expanded ? 'block' : 'none';
    if (cache.expanded) renderChildren(cache);
  }

  function renderChildren(cache) {
    var steps = cache.lastSteps || [];
    cache.children.innerHTML = '';
    if (steps.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'hangeul-grid-child hangeul-grid-child-empty';
      empty.textContent = uiLang === 'en' ? '(default pose)' : '기본 자세';
      cache.children.appendChild(empty);
      return;
    }
    steps.forEach(function (step) {
      var child = document.createElement('div');
      child.className = 'hangeul-grid-child';
      child.textContent = step.display_name_kr || step.skill_id;
      cache.children.appendChild(child);
    });
  }

  function multiStateLabel(info) {
    if (!info) return '';
    var en = uiLang === 'en';
    if (info.state === 'scheduled') return '⏰ ' + info.start_at + (en ? ' scheduled' : ' 예약');
    if (info.state === 'running') return en ? '▶ Running' : '▶ 다중 실행 중';
    if (info.state === 'done') return en ? '✔ Done' : '✔ 다중 실행 완료';
    if (info.state === 'cancelled') return en ? '⏹ Cancelled' : '⏹ 취소됨';
    if (info.state === 'failed') return '⚠ ' + (info.detail || (en ? 'Failed' : '실패'));
    return '';
  }

  function checkedRobotIds() {
    return Object.keys(rowCache).filter(function (robotId) {
      return rowCache[robotId].check.checked;
    });
  }

  function syncCheckAllBox() {
    if (!checkAllBox) return;
    var ids = Object.keys(rowCache);
    var checked = checkedRobotIds();
    checkAllBox.checked = ids.length > 0 && checked.length === ids.length;
    checkAllBox.indeterminate = checked.length > 0 && checked.length < ids.length;
  }

  function slogSafe(message, cls) {
    if (typeof window.slog === 'function') window.slog(message, cls || 's-log-info');
  }

  // ── 이름 더블클릭 인라인 수정 ────────────────────────────────────
  function beginRename(robotId) {
    var cache = rowCache[robotId];
    if (!cache || cache.editing) return;
    cache.editing = true;
    cache.nameEdit.value = cache.nameText.textContent;
    cache.nameText.style.display = 'none';
    cache.nameEdit.style.display = 'inline-block';
    cache.nameEdit.focus();
    cache.nameEdit.select();
  }

  function cancelRename(robotId) {
    var cache = rowCache[robotId];
    if (!cache) return;
    cache.editing = false;
    cache.nameEdit.style.display = 'none';
    cache.nameText.style.display = '';
  }

  function commitRename(robotId) {
    var cache = rowCache[robotId];
    if (!cache || !cache.editing) return;
    var name = cache.nameEdit.value.trim();
    cancelRename(robotId);
    if (!name || name === cache.nameText.textContent) return;
    fetch('/api/robots/' + encodeURIComponent(robotId) + '/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data.success) {
          styledAlert(data.detail || (uiLang === 'en' ? 'Failed to rename.' : '이름 변경 실패'))
            .then(function () { loadHangeulStatus(); });
        } else {
          loadHangeulStatus();
        }
      });
  }

  // 다중 실행: 기존과 동일하게 안전 확인 팝업(s-modal)을 먼저 통과해야
  // 서버에 요청한다. 서버는 전체 검증 통과 시에만 시작한다.
  // 상태점검 — **고른 자리에서 누른다.** 체크박스가 이미 여기 있으므로
  // 로봇이 수십 대로 늘어도 고르고 바로 누르면 된다.
  function runMultiSelfCheck() {
    var ids = checkedRobotIds();
    if (ids.length === 0) {
      styledAlert(hi18n().checkNone);
      return;
    }
    // **같은 팔은 한 번만 점검한다.** 로봇 두 대가 같은 런타임을 보면 같은
    // 팔이다. 두 번 돌리면 그 팔만 두 배로 닳고, 사람은 같은 결과를 두 번 본다.
    var seen = {};
    ids = ids.filter(function (robotId) {
      var row = rowCache[robotId];
      var where = (row && row.robot && row.robot.runtime_url) || robotId;
      if (seen[where]) return false;
      seen[where] = true;
      return true;
    });
    // 안전 확인과 결과 표시는 **기존 것**을 쓴다(simple.js). 점검용으로
    // 또 만들면 사람이 두 가지를 외워야 한다.
    if (typeof window.startSelfCheckFor === 'function') {
      window.startSelfCheckFor(ids);
    }
  }

  function runMultiExecute() {
    var entries = checkedRobotIds().map(function (robotId) {
      return { robot_id: robotId, start_at: rowCache[robotId].time.value || '' };
    });
    if (entries.length === 0) {
      styledAlert(uiLang === 'en' ? 'Check at least one robot first.' : '실행할 로봇을 먼저 체크하세요.');
      return;
    }
    var launch = function () {
      fetch('/api/hangeul/multi-execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          robots: entries,
          operator: 'hangeul_operator',
          safety_inputs: {
            operator_present: true,
            workspace_clear: true,
            human_nearby: false,
            manual_stop_available: true,
            estop_ready: true
          }
        })
      })
        .then(function (response) {
          return response.json().then(function (data) { return { ok: response.ok, data: data }; });
        })
        .then(function (result) {
          if (!result.ok || result.data.success === false) {
            var reason = result.data.detail || result.data.error || (uiLang === 'en' ? 'Unknown error' : '알 수 없는 오류');
            styledAlert((uiLang === 'en' ? 'Cannot start multi-run:\n' : '다중 실행 불가:\n') + reason);
            slogSafe((uiLang === 'en' ? 'Multi-run rejected: ' : '다중 실행 거부: ') + reason, 's-log-err');
          } else {
            var summary = (result.data.runs || []).map(function (run) {
              return run.display_name + (run.scheduled ? ' ⏰' + run.start_at : (uiLang === 'en' ? ' now' : ' 즉시'));
            }).join(', ');
            slogSafe((uiLang === 'en' ? 'Multi-run accepted: ' : '다중 실행 접수: ') + summary, 's-log-ok');
          }
          loadHangeulStatus();
        })
        .catch(function (error) {
          styledAlert((uiLang === 'en' ? 'Multi-run request failed: ' : '다중 실행 요청 실패: ') + error.message);
        });
    };
    if (typeof window.showModal === 'function') {
      window.showModal(launch);   // 안전 확인 5개 항목 → '모두 확인 → 실행'
    } else {
      styledConfirm(uiLang === 'en'
        ? 'Have you confirmed the workspace is safe (no people nearby / stop device ready)?'
        : '로봇 주변 안전(사람 없음/정지장치 준비)을 확인했습니까?'
      ).then(function (ok) { if (ok) launch(); });
    }
  }

  // 완료/실패/취소로 끝난 다중 실행 표시를 지우고, 체크박스/예약 시각도
  // 처음 상태(모두 해제/빈칸)로 되돌린다. 예약·진행 중인 항목은 서버가
  // 건드리지 않으므로 화면도 그대로 둔다. 모든 로봇(체크 여부 무관)의
  // 상태 표시(완료/오류)도 대기로 되돌린다 — '초기화는 모두 대기 상태여야
  // 한다'는 지적에 따라 체크박스 범위 제한을 없앰.
  function resetMultiRuns() {
    fetch('/api/hangeul/multi-reset', { method: 'POST' })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        Object.keys(rowCache).forEach(function (robotId) {
          if ((data.kept_active || []).indexOf(robotId) !== -1) return;
          rowCache[robotId].check.checked = false;
          rowCache[robotId].time.value = '';
        });
        syncCheckAllBox();
        var count = (data.cleared || []).length;
        var kept = (data.kept_active || []).length;
        var statusReset = (data.status_reset || []).length;
        var parts = [];
        if (uiLang === 'en') {
          if (count > 0) parts.push('multi-run markers ' + count);
          if (statusReset > 0) parts.push('status ' + statusReset);
          slogSafe(
            parts.length > 0
              ? 'Reset: ' + parts.join(', ') + (kept > 0 ? ' (' + kept + ' in progress kept)' : '')
              : (kept > 0 ? 'Nothing to reset (' + kept + ' in progress kept)' : 'Nothing to reset.'),
            's-log-info');
        } else {
          if (count > 0) parts.push('다중 실행 표시 ' + count + '건');
          if (statusReset > 0) parts.push('상태 표시 ' + statusReset + '건');
          slogSafe(
            parts.length > 0
              ? '초기화: ' + parts.join(', ') + (kept > 0 ? ' (진행 중 ' + kept + '건은 유지)' : '')
              : (kept > 0 ? '초기화할 항목 없음 (진행 중 ' + kept + '건은 유지)' : '초기화할 항목이 없습니다.'),
            's-log-info');
        }
        loadHangeulStatus();
      });
  }

  function cancelMultiRuns() {
    fetch('/api/hangeul/multi-cancel', { method: 'POST' })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var count = (data.cancelled || []).length;
        slogSafe(
          uiLang === 'en'
            ? (count > 0 ? 'Cancelled ' + count + ' multi-run(s).' : 'Nothing to cancel.')
            : (count > 0 ? '다중 실행/예약 취소: ' + count + '건' : '취소할 예약/실행이 없습니다.'),
          count > 0 ? 's-log-info' : 's-log-err');
        loadHangeulStatus();
      });
  }

  // ── 그리드에서 시작한 다중 실행의 일시정지/재개 ─────────────────────
  // 기존 '⏸ 일시 정지' 버튼(simple.js)은 브라우저 쪽 단일 로봇 대기열
  // 루프(state.running)만 멈췄지, 그리드의 다중 실행은 백엔드 스레드가
  // 직접 관절 이동을 보내므로 전혀 몰랐다 — "일시 정지가 안 된다"는 지적의
  // 원인. 같은 버튼에 리스너를 하나 더 달아 그리드 쪽 일시정지/재개도
  // 함께 처리한다(simple.js 쪽 로직과는 독립적으로 동작 — 서로 방해 안 함).
  var pauseBtn = document.getElementById('btn-pause');
  var multiPaused = false;
  var anyMultiRunActive = false;   // 3초 폴링으로 갱신 — 그리드 다중 실행이 하나라도 진행/예약 중인지

  // 실제 원인: simple.js의 updatePauseBtn()이 `btn.disabled = !state.running &&
  // !state.paused`로 판정한다. 그리드 다중 실행은 state.running을 절대 안 켜므로
  // 버튼이 항상 비활성화돼 클릭 자체가 브라우저에서 씹혔다(리스너는 붙어 있어도
  // disabled 버튼은 클릭 이벤트가 안 뜬다) — "일시 정지가 안 된다"의 진짜 원인.
  // updatePauseBtn을 감싸서, simple.js가 뭐라고 판단하든 그리드 다중 실행이
  // 진행/예약 중이면 항상 강제로 활성화한다.
  function updatePauseBtnForMulti() {
    if (!pauseBtn) return;
    if (multiPaused) {
      pauseBtn.disabled = false;
      pauseBtn.textContent = uiLang === 'en' ? '▶ Resume' : '▶ 계속 진행';
      pauseBtn.style.background = '#10b981';
      pauseBtn.style.borderColor = '#059669';
      pauseBtn.style.color = '#fff';
    } else if (anyMultiRunActive) {
      pauseBtn.disabled = false;
      pauseBtn.textContent = uiLang === 'en' ? '⏸ Pause' : '⏸ 일시 정지';
      pauseBtn.style.background = '#f59e0b';
      pauseBtn.style.borderColor = '#d97706';
      pauseBtn.style.color = '#111827';
    }
    // 그리드 쪽에 활성 다중 실행이 없으면 simple.js 자체 판단(비활성화 등)에 맡긴다.
  }

  // simple.js는 최상위 스크립트라 updatePauseBtn이 전역(window)에 그대로 걸린다.
  // 이를 감싸서, simple.js가 이 함수를 호출할 때마다(카드 클릭 등 온갖 곳에서
  // 호출됨) 곧바로 뒤이어 그리드 판단을 다시 반영한다 — 3초 폴링 사이에도
  // 버튼이 도로 비활성화되는 일이 없게 한다.
  if (typeof window.updatePauseBtn === 'function') {
    var _originalUpdatePauseBtn = window.updatePauseBtn;
    window.updatePauseBtn = function () {
      _originalUpdatePauseBtn.apply(this, arguments);
      updatePauseBtnForMulti();
    };
  }

  function toggleMultiPause() {
    if (multiPaused) {
      fetch('/api/hangeul/multi-resume', { method: 'POST' })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          multiPaused = false;
          updatePauseBtnForMulti();
          var count = (data.resumed || []).length;
          slogSafe(
            uiLang === 'en'
              ? (count > 0 ? 'Resumed ' + count + ' multi-run(s).' : 'Nothing to resume.')
              : (count > 0 ? '다중 실행 재개: ' + count + '건' : '재개할 일시정지가 없습니다.'),
            's-log-ok');
        });
    } else {
      fetch('/api/hangeul/multi-pause-hold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operator: 'hangeul_operator' })
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          var count = (data.paused || []).length;
          if (count > 0) {
            multiPaused = true;
            updatePauseBtnForMulti();
          }
          slogSafe(
            uiLang === 'en'
              ? (count > 0 ? 'Paused ' + count + ' multi-run(s).' : 'No multi-run in progress.')
              : (count > 0 ? '다중 실행 일시정지: ' + count + '건' : '진행 중인 다중 실행이 없습니다.'),
            count > 0 ? 's-log-info' : 's-log-err');
        });
    }
  }

  if (pauseBtn) {
    pauseBtn.addEventListener('click', toggleMultiPause);
  }

  function loadRobotTypes() {
    return fetch('/api/robot-types')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        robotTypeCards = data.cards || [];
        robotTypes = robotTypeCards.length
          ? robotTypeCards.map(function (c) { return c.part_id; })
          : (data.types || []);
        robotTypeLabels = {};
        robotTypeCards.forEach(function (c) { robotTypeLabels[c.part_id] = c.label; });
      });
  }

  // ── 로봇별 로그 파일 연동 ─────────────────────────────────────────
  // 화면 하단 로그(#s-log)를 선택된 로봇의 ui_log.jsonl에 저장/복원한다.
  function replayRobotLog() {
    var log = document.getElementById('s-log');
    if (!log) return;
    fetch('/api/hangeul/log')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        (data.entries || []).forEach(function (entry) {
          var el = document.createElement('div');
          el.className = 's-log-entry ' + (entry.cls || 's-log-info');
          el.textContent = '[' + (entry.ts || '') + '] ' + entry.message;
          log.insertBefore(el, log.firstChild);
        });
      });
  }

  function installLogPersistence() {
    if (typeof window.slog !== 'function') return;
    var originalSlog = window.slog;
    window.slog = function (msg, cls) {
      originalSlog(msg, cls);
      try {
        fetch('/api/hangeul/log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: String(msg), cls: cls || 's-log-info' })
        });
      } catch (ignored) { /* 로그 저장 실패는 화면 동작을 막지 않는다 */ }
    };
  }

  function defaultRobotId(robots) {
    var hasRobot4 = robots.some(function (robot) { return robot.robot_id === 'robot_4'; });
    return hasRobot4 ? 'robot_4' : (robots[0] && robots[0].robot_id);
  }

  // 로봇 추가 — 모델을 눈으로 고른다.
  // 전에는 이름을 묻고, 이어서 "omx 또는 mycobot_280_m5"를 손으로 받아 적게 했다.
  // 사람이 부품 번호를 외워야 하는 화면은 화면이 아니다.
  var addModal = document.getElementById('s-add-robot-modal');
  var addNameInput = document.getElementById('add-robot-name');
  var addGrid = document.getElementById('add-robot-model-grid');
  var addConfirmBtn = document.getElementById('btn-add-robot-confirm');
  var addCancelBtn = document.getElementById('btn-add-robot-cancel');
  var addPicked = '';

  function renderModelGrid() {
    if (!addGrid) return;
    addGrid.innerHTML = '';
    var d = hi18n();
    // 실물로 해본 팔을 앞에 놓는다. 배선만 맞춘 것과 같은 자리에 두면
    // 사람은 둘을 같은 것으로 읽는다.
    var order = robotTypeCards.slice().sort(function (a, b) {
      var av = a.evidence === 'verified' ? 0 : 1;
      var bv = b.evidence === 'verified' ? 0 : 1;
      return av - bv || a.label.localeCompare(b.label);
    });
    order.forEach(function (card) {
      var el = document.createElement('button');
      el.type = 'button';
      el.className = 's-model-card' + (card.part_id === addPicked ? ' is-picked' : '');
      var name = document.createElement('div');
      name.className = 's-model-card-name';
      name.textContent = card.label;
      var spec = document.createElement('div');
      spec.className = 's-model-card-spec';
      var bits = [card.joint_count + (uiLang === 'en' ? ' axes' : '축')];
      if (card.hand) bits.push((uiLang === 'en' ? 'hand: ' : '손: ') + card.hand);
      else bits.push(uiLang === 'en' ? 'no hand' : '손 없음');
      if (card.reach_mm) bits.push(card.reach_mm + 'mm');
      if (card.payload_g) bits.push(card.payload_g + 'g');
      spec.textContent = bits.join(' · ');
      var badge = document.createElement('span');
      badge.className = 's-model-card-evidence '
        + (card.evidence === 'verified' ? 'is-verified' : 'is-wired');
      badge.textContent = (uiLang === 'en' ? card.evidence_en : card.evidence_ko)
        || (uiLang === 'en' ? 'unknown' : '알 수 없음');
      el.appendChild(name);
      el.appendChild(spec);
      el.appendChild(badge);
      el.addEventListener('click', function () {
        addPicked = card.part_id;
        if (addConfirmBtn) addConfirmBtn.disabled = false;
        renderModelGrid();
      });
      addGrid.appendChild(el);
    });
    if (!order.length) {
      var empty = document.createElement('div');
      empty.className = 's-model-card-spec';
      empty.textContent = d.addNoModels;
      addGrid.appendChild(empty);
    }
  }

  function closeAddRobot() {
    if (addModal) addModal.style.display = 'none';
    addPicked = '';
    if (addConfirmBtn) addConfirmBtn.disabled = true;
  }

  function addRobot() {
    if (!addModal) return;
    addPicked = '';
    if (addNameInput) addNameInput.value = '';
    if (addConfirmBtn) addConfirmBtn.disabled = true;
    renderModelGrid();
    addModal.style.display = 'flex';
    if (addNameInput) addNameInput.focus();
  }

  function submitAddRobot() {
    if (!addPicked) return;
    fetch('/api/robots/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: (addNameInput ? addNameInput.value : '').trim(),
        model: addPicked
      })
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          styledAlert(data.detail || (uiLang === 'en' ? 'Cannot add robot.' : '로봇을 추가할 수 없습니다.'));
        });
      }
      closeAddRobot();
      window.location.reload();
    });
  }

  if (addCancelBtn) addCancelBtn.addEventListener('click', closeAddRobot);
  if (addConfirmBtn) addConfirmBtn.addEventListener('click', submitAddRobot);
  if (addModal) {
    addModal.addEventListener('click', function (e) { if (e.target === addModal) closeAddRobot(); });
  }

  // 그리드 위 작은 아이콘 툴바의 삭제 — 정확히 1대만 체크했을 때만 동작
  // (체크박스는 다중 실행 선택과 공유되므로 실수 방지를 위해 1건으로 제한).
  // 2026-07-23: 체크박스 기반 삭제(removeCheckedRobot)와 행별 🗑 버튼
  // (deleteRobot) 둘 다 같은 로직을 쓰도록 분리 — robotId를 직접 받는다.
  function deleteRobot(robotId) {
    var cache = rowCache[robotId];
    var label = cache ? cache.nameText.textContent : robotId;
    var message = uiLang === 'en'
      ? 'Delete robot "' + label + '"?\nIts files move to the archive (_deleted) and can be restored.'
      : '"' + label + '" 로봇을 삭제합니까?\n자세/순서/로그 파일은 보관함(_deleted)으로 이동되며 복구할 수 있습니다.';
    styledConfirm(message, uiLang === 'en' ? 'Delete robot' : '로봇 삭제', true).then(function (ok) {
      if (!ok) return;
      fetch('/api/robots/' + encodeURIComponent(robotId), { method: 'DELETE' })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (data) {
              styledAlert(data.detail || (uiLang === 'en' ? 'Cannot delete robot.' : '로봇을 삭제할 수 없습니다.'))
                .then(function () { loadHangeulStatus(); });
            });
          }
          window.location.reload();
        });
    });
  }

  function removeCheckedRobot() {
    var checked = checkedRobotIds();
    if (checked.length !== 1) {
      styledAlert(uiLang === 'en' ? 'Check exactly one robot to delete.' : '삭제할 로봇 1대만 체크하세요.');
      return;
    }
    deleteRobot(checked[0]);
  }

  // ── 열 너비 조절 (헤더 드래그 → CSS 변수 → localStorage) ───────────
  var COL_WIDTH_STORAGE_KEY = 'dexterHangeulGridColWidths';
  var gridRoot = document.getElementById('hangeul-robot-grid');
  var DEFAULT_COL_WIDTHS = { name: 200, status: 90, time: 150, attach: 150, clear: 120 };
  // 2026-07-23: 컬럼별 최소폭 — 예전엔 전부 50px 하한이라 리사이저로 시간
  // 위젯이나 select 텍스트가 잘리도록 줄일 수 있었다.
  var MIN_COL_WIDTHS = { name: 120, status: 70, time: 90, attach: 100, clear: 96 };

  function loadColWidths() {
    var widths = DEFAULT_COL_WIDTHS;
    try {
      var saved = JSON.parse(localStorage.getItem(COL_WIDTH_STORAGE_KEY) || '{}');
      widths = Object.assign({}, DEFAULT_COL_WIDTHS, saved);
    } catch (ignored) { /* 손상된 값은 기본값 사용 */ }
    applyColWidths(widths);
  }

  function applyColWidths(widths) {
    if (!gridRoot) return;
    Object.keys(widths).forEach(function (col) {
      gridRoot.style.setProperty('--hangeul-col-' + col + '-w', widths[col] + 'px');
    });
  }

  function saveColWidth(col, px) {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(COL_WIDTH_STORAGE_KEY) || '{}'); } catch (ignored) { /* noop */ }
    saved[col] = px;
    localStorage.setItem(COL_WIDTH_STORAGE_KEY, JSON.stringify(saved));
    applyColWidths(saved);
  }

  function installColumnResizers() {
    var resizers = document.querySelectorAll('.hangeul-col-resizer');
    resizers.forEach(function (handle) {
      var col = handle.dataset.col;
      var minWidth = MIN_COL_WIDTHS[col] || 50;

      function beginResize(startClientX) {
        var headerCell = handle.parentElement;
        var startWidth = headerCell.getBoundingClientRect().width;
        function widthAt(clientX) {
          return Math.max(minWidth, Math.round(startWidth + (clientX - startClientX)));
        }
        return {
          move: function (clientX) {
            applyColWidths((function () { var w = {}; w[col] = widthAt(clientX); return w; })());
          },
          end: function (clientX) {
            saveColWidth(col, widthAt(clientX));
          },
        };
      }

      handle.addEventListener('mousedown', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var session = beginResize(e.clientX);
        function onMove(moveEvent) { session.move(moveEvent.clientX); }
        function onUp(upEvent) {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          session.end(upEvent.clientX);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      });

      // 2026-07-23: 태블릿 운영자 패널에서 마우스가 없어 컬럼 폭을 못 바꾸던
      // 문제 — 같은 로직을 터치 이벤트로도 연결한다.
      handle.addEventListener('touchstart', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var touch = e.touches[0];
        var session = beginResize(touch.clientX);
        function onMove(moveEvent) { session.move(moveEvent.touches[0].clientX); }
        function onEnd(endEvent) {
          document.removeEventListener('touchmove', onMove);
          document.removeEventListener('touchend', onEnd);
          document.removeEventListener('touchcancel', onEnd);
          session.end((endEvent.changedTouches && endEvent.changedTouches[0].clientX) || touch.clientX);
        }
        document.addEventListener('touchmove', onMove, { passive: true });
        document.addEventListener('touchend', onEnd);
        document.addEventListener('touchcancel', onEnd);
      }, { passive: false });
    });
  }

  function resetColWidths() {
    localStorage.removeItem(COL_WIDTH_STORAGE_KEY);
    applyColWidths(DEFAULT_COL_WIDTHS);
  }

  // ── '지정하기' — 팝업으로 대상 로봇을 직접 골라 그 로봇의 현재 실행
  //    순서만 즉시 반영한다(이름 없음, 1회성·휘발성). '현재 선택된 로봇'
  //    이라는 전역 상태에 기대지 않고 매번 명시적으로 고르게 해 엉뚱한
  //    로봇에 지정되는 사고를 막는다(사용자 보고로 추가).
  var assignModal = document.getElementById('s-assign-modal');
  var assignRobotList = document.getElementById('assign-robot-list');
  var assignConfirmBtn = document.getElementById('btn-assign-modal-confirm');
  var assignCancelBtn = document.getElementById('btn-assign-modal-cancel');
  var assignTitleEl = document.getElementById('assign-modal-title');
  var assignSubtitleEl = document.getElementById('assign-modal-subtitle');

  function openAssignRobotModal() {
    if (typeof window.state === 'undefined' || !window.state.queue || window.state.queue.length === 0) {
      styledAlert(uiLang === 'en' ? 'Add movements to the queue first.' : '먼저 대기열에 동작을 담으세요.');
      return;
    }
    if (!assignModal || !assignRobotList) return;
    var d = hi18n();
    if (assignTitleEl) assignTitleEl.textContent = d.assignModalTitle;
    if (assignSubtitleEl) assignSubtitleEl.textContent = d.assignModalSubtitle;
    if (assignCancelBtn) assignCancelBtn.textContent = d.assignCancel;
    if (assignConfirmBtn) assignConfirmBtn.textContent = d.assignConfirm;
    assignRobotList.innerHTML = '';
    var ids = Object.keys(rowCache);
    ids.forEach(function (robotId) {
      var cache = rowCache[robotId];
      var label = document.createElement('label');
      label.style.cssText = 'display:flex; align-items:center; gap:8px; padding:8px 10px; border:1px solid #334155; border-radius:6px; cursor:pointer;';
      var radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = 'assign-target-robot';
      radio.value = robotId;
      if (robotId === selectedRobotId) radio.checked = true;
      radio.addEventListener('change', function () {
        if (assignConfirmBtn) assignConfirmBtn.disabled = false;
      });
      var text = document.createElement('span');
      text.textContent = cache ? cache.nameText.textContent : robotId;
      label.appendChild(radio);
      label.appendChild(text);
      assignRobotList.appendChild(label);
    });
    if (assignConfirmBtn) assignConfirmBtn.disabled = ids.indexOf(selectedRobotId) === -1;
    assignModal.style.display = 'flex';
  }

  function closeAssignRobotModal() {
    if (assignModal) assignModal.style.display = 'none';
  }

  function submitAssignRobotModal() {
    var picked = assignRobotList ? assignRobotList.querySelector('input[name="assign-target-robot"]:checked') : null;
    if (!picked) return;
    var robotId = picked.value;
    var skillIds = window.state.queue.map(function (item) { return item.skill_id; });
    fetch('/api/hangeul/assign-sequence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_ids: skillIds, robot_id: robotId })
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        closeAssignRobotModal();
        if (!data.success) {
          styledAlert(data.error || (uiLang === 'en' ? 'Assign failed.' : '지정 실패'));
          return;
        }
        var label = rowCache[robotId] ? rowCache[robotId].nameText.textContent : robotId;
        slogSafe(
          (uiLang === 'en' ? 'Assigned to ' + label + ': ' : label + '에 지정 완료: ')
            + data.step_count + (uiLang === 'en' ? ' steps' : '개 동작'),
          's-log-ok');
        var cache = rowCache[robotId];
        if (cache && cache.expanded) loadHangeulStatus();
      })
      .catch(function (error) {
        closeAssignRobotModal();
        slogSafe((uiLang === 'en' ? 'Assign failed: ' : '지정 실패: ') + error.message, 's-log-err');
      });
  }

  // ── 언어 전환(🌐) 시 그리드/툴바도 함께 갱신 ─────────────────────────
  // simple.js가 이 버튼에 먼저 바인딩되어 localStorage를 새 값으로 바꿔
  // 놓으므로(스크립트 로드 순서: simple.js → hangeul-grid.js, 리스너는
  // 등록 순서대로 실행됨), 여기서는 그 값을 그대로 다시 읽기만 하면 된다.
  var langToggleBtn = document.getElementById('btn-lang');
  if (langToggleBtn) {
    langToggleBtn.addEventListener('click', function () {
      uiLang = localStorage.getItem('dexterUiLang') === 'en' ? 'en' : 'ko';
      NONE_LABEL = uiLang === 'en' ? 'none' : '없음';
      PLACEHOLDER_LABEL = uiLang === 'en' ? '-Select-' : '-선택하세요-';
      applyHangeulStaticI18n();
      rowOrderKey = '';   // 행을 전부 다시 만들어 새 uiLang으로 라벨 갱신
      loadHangeulStatus();
    });
  }

  if (addBtn) {
    addBtn.addEventListener('click', addRobot);
  }
  if (removeBtn) {
    removeBtn.addEventListener('click', removeCheckedRobot);
  }
  var resetWidthsBtn = document.getElementById('hangeul-reset-col-widths');
  if (resetWidthsBtn) {
    resetWidthsBtn.addEventListener('click', resetColWidths);
  }
  if (checkAllBox) {
    checkAllBox.addEventListener('change', function () {
      Object.keys(rowCache).forEach(function (robotId) {
        rowCache[robotId].check.checked = checkAllBox.checked;
      });
      syncCheckAllBox();
    });
  }
  if (multiExecBtn) {
    multiExecBtn.addEventListener('click', runMultiExecute);
  }
  if (multiCancelBtn) {
    multiCancelBtn.addEventListener('click', cancelMultiRuns);
  }
  if (multiResetBtn) {
    multiResetBtn.addEventListener('click', resetMultiRuns);
  }
  var multiCheckBtn = document.getElementById('hangeul-multi-check');
  if (multiCheckBtn) {
    multiCheckBtn.addEventListener('click', runMultiSelfCheck);
  }
  var assignBtn = document.getElementById('btn-assign');
  if (assignBtn) {
    assignBtn.addEventListener('click', openAssignRobotModal);
  }
  if (assignCancelBtn) {
    assignCancelBtn.addEventListener('click', closeAssignRobotModal);
  }
  if (assignConfirmBtn) {
    assignConfirmBtn.addEventListener('click', submitAssignRobotModal);
  }

  // ── 🧠 SLLM 도우미 (제안 전용) ─────────────────────────────────
  // 근거: /root/Beom/docs/SLLM_FINAL_DECISION_20260814_KR.md
  //  - 화면은 후보만 보여주고, 대상 로봇을 항상 명시한다.
  //  - 후보가 없으면 실행 버튼 자체를 만들지 않는다.
  //  - 후보를 골라도 바로 실행하지 않는다 — 실행 대기열에 담고, 실행은
  //    기존 '실행 시작' → 확인 모달 → 서버 안전 게이트 경로를 그대로 쓴다.
  //  - 승인된 후보는 1회용 토큰(proposal_id)을 갖고, 실행 API가 이를 검증한다.
  var sllmCandidates = [];

  function sllmRobotLabel() {
    var cache = rowCache[selectedRobotId];
    var name = cache && cache.nameText ? cache.nameText.textContent : '';
    return (name ? name + ' (' + selectedRobotId + ')' : (selectedRobotId || '선택된 로봇 없음'));
  }

  function setSllmMessage(text) {
    var box = document.getElementById('sllm-candidates');
    if (box) { box.textContent = text; }
  }

  function loadSllmSettings() {
    return fetch('/api/sllm/settings')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var s = d.settings || {};
        var enabled = document.getElementById('sllm-enabled');
        var seqs = document.getElementById('sllm-search-sequences');
        var minScore = document.getElementById('sllm-min-score');
        var maxCand = document.getElementById('sllm-max-candidates');
        var note = document.getElementById('sllm-runtime-note');
        var badge = document.getElementById('sllm-runtime-badge');
        if (enabled) enabled.checked = !!s.enabled;
        if (seqs) seqs.checked = !!s.search_sequences;
        if (minScore) minScore.value = s.min_score;
        if (maxCand) maxCand.value = s.max_candidates;
        if (note) note.textContent = d.runtime_note || '';
        if (badge) badge.textContent = (d.retriever || '') + ' · sLLM ' + (d.sllm_runtime || '');
      })
      .catch(function () { /* 설정 조회 실패해도 검색은 시도할 수 있게 둔다 */ });
  }

  window.saveSllmSettings = function () {
    var body = {
      enabled: document.getElementById('sllm-enabled').checked,
      search_sequences: document.getElementById('sllm-search-sequences').checked,
      min_score: parseFloat(document.getElementById('sllm-min-score').value),
      max_candidates: parseInt(document.getElementById('sllm-max-candidates').value, 10)
    };
    fetch('/api/sllm/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (typeof slog === 'function') {
          slog(d.ok ? 'SLLM 설정 저장됨' : ('SLLM 설정 저장 실패: ' + (d.error || '')),
            d.ok ? 's-log-ok' : 's-log-err');
        }
        loadSllmSettings();
      });
  };

  window.openSllmModal = function () {
    var modal = document.getElementById('s-sllm-modal');
    if (!modal) return;
    var target = document.getElementById('sllm-target-robot');
    if (target) target.textContent = sllmRobotLabel();
    sllmCandidates = [];
    setSllmMessage('찾을 동작을 한 줄로 입력하세요.');
    loadSllmSettings();
    modal.style.display = 'flex';
    var input = document.getElementById('sllm-query');
    if (input) { input.value = ''; input.focus(); }
  };

  window.closeSllmModal = function () {
    var modal = document.getElementById('s-sllm-modal');
    if (modal) modal.style.display = 'none';
  };

  function renderSllmCandidates(data) {
    var box = document.getElementById('sllm-candidates');
    if (!box) return;
    box.textContent = '';
    if (!data.candidates || !data.candidates.length) {
      box.textContent = (data.no_match_reason || data.error || '후보를 찾지 못했습니다.')
        + ' — 저장된 자세·순서 이름으로 다시 찾아보세요.';
      return;
    }
    if (data.requires_operator_choice) {
      var hint = document.createElement('div');
      hint.style.cssText = 'color:#fbbf24; font-size:0.76rem; margin-bottom:8px;';
      hint.textContent = '⚠ 비슷한 후보가 여럿입니다. 자동으로 고르지 않습니다 — 직접 선택하세요.';
      box.appendChild(hint);
    }
    data.candidates.forEach(function (candidate, index) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex; align-items:center; gap:8px; padding:8px; margin-bottom:6px;'
        + ' background:#1e293b; border:1px solid #334155; border-radius:6px;';

      var textBox = document.createElement('div');
      textBox.style.cssText = 'flex:1; min-width:0;';
      var title = document.createElement('div');
      title.style.cssText = 'color:#f1f5f9; font-weight:700; font-size:0.85rem;';
      title.textContent = (candidate.target_type === 'sequence' ? '📂 ' : '🤖 ') + candidate.label_kr;
      var meta = document.createElement('div');
      meta.style.cssText = 'color:#64748b; font-size:0.72rem; margin-top:2px;';
      meta.textContent = (candidate.target_type === 'sequence' ? '저장 순서' : '저장 자세')
        + ' · 일치도 ' + Math.round(candidate.score * 100) + '%'
        + ' · 단계 ' + candidate.match_stage
        + ' · rev ' + candidate.target_revision
        + ' · 로봇 ' + candidate.instance_id;
      textBox.appendChild(title);
      textBox.appendChild(meta);

      var button = document.createElement('button');
      button.className = 's-btn s-btn-sm';
      button.style.cssText = 'background:#10b981; border-color:#059669; color:#fff; white-space:nowrap;';
      button.textContent = '이 후보 선택';
      button.addEventListener('click', function () { approveSllmCandidate(index); });

      row.appendChild(textBox);
      row.appendChild(button);
      box.appendChild(row);
    });
  }

  window.runSllmSuggest = function () {
    var input = document.getElementById('sllm-query');
    var query = input ? input.value.trim() : '';
    if (!query) { setSllmMessage('찾을 동작을 한 줄로 입력하세요.'); return; }
    if (!selectedRobotId) { setSllmMessage('먼저 로봇을 선택하세요.'); return; }
    setSllmMessage('찾는 중…');
    fetch('/api/sllm/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instance_id: selectedRobotId, query: query })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        sllmCandidates = d.candidates || [];
        renderSllmCandidates(d);
        if (typeof slog === 'function') {
          slog('SLLM 제안(실행 아님): "' + query + '" → 후보 ' + sllmCandidates.length + '건', 's-log-info');
        }
      })
      .catch(function (error) { setSllmMessage('제안 요청 실패: ' + error.message); });
  };

  function queueApprovedPose(candidate) {
    // 실행 토큰은 skill_id별로 보관했다가 실행 API 호출 때 1회만 실려 나간다.
    window.__sllmGrants = window.__sllmGrants || {};
    window.__sllmGrants[candidate.target_id] = candidate.proposal_id;
    var catalog = (window.state && window.state.catalog) || [];
    var movement = null;
    for (var i = 0; i < catalog.length; i++) {
      if (catalog[i].skill_id === candidate.target_id) { movement = catalog[i]; break; }
    }
    if (!movement) {
      movement = {
        skill_id: candidate.target_id,
        display_name_kr: candidate.label_kr,
        display_name_en: candidate.label_en || candidate.label_kr,
        icon: '🧠'
      };
    }
    if (typeof addToQueue === 'function') addToQueue(movement);
  }

  function approveSllmCandidate(index) {
    var candidate = sllmCandidates[index];
    if (!candidate) return;
    fetch('/api/sllm/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instance_id: selectedRobotId,
        proposal_id: candidate.proposal_id,
        operator: 'web_operator'
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          styledAlert('후보를 쓸 수 없습니다: ' + (d.error || '알 수 없는 사유'));
          return;
        }
        if (candidate.target_type === 'sequence') {
          var steps = (d.detail && d.detail.steps) || [];
          if (typeof appendSequenceRecipe === 'function') {
            appendSequenceRecipe(candidate.target_id, steps);
          }
        } else {
          queueApprovedPose(candidate);
        }
        window.closeSllmModal();
        styledAlert('실행 대기열에 담았습니다: ' + candidate.label_kr
          + '\n\n실행하려면 평소처럼 [실행 시작]을 누르고 확인 절차를 거치세요. '
          + '(SLLM은 실행하지 않습니다)');
      })
      .catch(function (error) { styledAlert('승인 요청 실패: ' + error.message); });
  }

  applyHangeulStaticI18n();
  loadColWidths();
  installColumnResizers();
  installLogPersistence();
  replayRobotLog();
  loadRobotTypes().then(loadHangeulStatus);
  setInterval(loadHangeulStatus, 3000);
})();
