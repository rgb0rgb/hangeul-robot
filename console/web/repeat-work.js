/* A/B execution belongs to the console, not the browser's request queue. */
(function () {
  'use strict';
  var robot = '', signature = '', job = null, pending = false, polling = false;
  var $ = function (id) { return document.getElementById('repeat-' + id); };
  function text(ko, en) { return lang === 'ko' ? ko : en; }
  async function api(path, body) {
    var res = await fetch(BACKEND + '/api/repeat-work' + path, body ? {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    } : {});
    var data = await res.json();
    if (!res.ok || data.success === false) throw new Error(data.error || data.detail || 'Request failed');
    return data;
  }
  function labels() {
    document.querySelectorAll('[data-repeat-ko]').forEach(function (el) {
      el.textContent = el.getAttribute(lang === 'ko' ? 'data-repeat-ko' : 'data-repeat-en');
    });
    var j = $('joint').value, unit = isMyCobotUi() ? (isGripperJoint(j) ? '%' : '°') :
      (((state.robotJoints || {}).value_units || {}).raw_position || 'ticks');
    $('a-label').textContent = text('A 위치', 'Position A') + ' (' + unit + ')';
    $('b-label').textContent = text('B 위치', 'Position B') + ' (' + unit + ')';
    var band = (state.jointTickLimits || {})[j];
    $('range').textContent = band ? text('허용 범위: ', 'Allowed range: ') + formatUiRange(j, band) : '';
  }
  function render() {
    labels();
    var s = job ? job.state : 'idle';
    var active = ['running', 'pausing', 'paused', 'canceling'].indexOf(s) !== -1;
    ['joint','a','b','count','wait-a','wait-b','capture-a','capture-b','start'].forEach(function (id) {
      $(id).disabled = active || pending || !robot;
    });
    $('save').disabled = pending || !robot;
    $('pause').disabled = pending || s !== 'running';
    $('resume').disabled = pending || ['paused','pausing'].indexOf(s) === -1;
    $('cancel').disabled = pending || !active || s === 'canceling';
    var names = {idle: text('대기 중','Idle'), running: text('실행 중','Running'),
      pausing: text('현재 이동 후 일시정지','Pausing after current move'), paused: text('일시정지','Paused'),
      canceling: text('취소 중','Canceling'), canceled: text('취소됨 · 다시 시작하려면 정지 해제','Canceled · reset stop before restarting'),
      failed: text('실패','Failed'), completed: text('완료','Completed')};
    $('status').textContent = (names[s] || s) + (job && job.count ?
      ' · ' + job.completed + '/' + job.count + text('회 완료',' cycles complete') +
      (active ? ' · ' + job.cycle + text('회차 ',' cycle ') + job.phase : '') : '') +
      (job && job.error ? ' · ' + job.error : '');
  }
  function refresh() {
    var joints = state.robotJoints || {}, nextRobot = joints.instance_id || '';
    var defs = (joints.all_joints || []).filter(function (j) {
      return !j.excluded && (state.excludedJointIds || []).indexOf(j.joint_id) === -1;
    });
    var next = nextRobot + '|' + JSON.stringify(defs) + '|' + lang;
    if (next !== signature) {
      var oldJoint = $('joint').value;
      if (robot !== nextRobot) { job = null; $('a').value = ''; $('b').value = ''; }
      robot = nextRobot; signature = next;
      $('joint').replaceChildren();
      defs.forEach(function (j) {
        var opt = document.createElement('option'); opt.value = String(j.joint_id);
        opt.textContent = lang === 'ko' ? j.label_kr : j.label_en;
        $('joint').appendChild(opt);
      });
      if (defs.some(function (j) { return String(j.joint_id) === oldJoint; })) $('joint').value = oldJoint;
    }
    render();
  }
  window.refreshRepeatWork = refresh;
  function readPlan(prefix) {
    var field = function (id) { return document.getElementById(prefix + id).value; };
    var joint = field('joint'), a = field('a'), b = field('b');
    var count = Number(field('count')), wa = Number(field('wait-a')), wb = Number(field('wait-b'));
    if (!joint || !a.trim() || !b.trim() || !Number.isFinite(Number(a)) || !Number.isFinite(Number(b)) ||
        !Number.isSafeInteger(count) || count < 1 || !Number.isFinite(wa) || !Number.isFinite(wb) || wa < 0 || wb < 0) {
      throw new Error(text('A·B 위치, 횟수, 대기 시간을 확인하세요.', 'Check positions, count and waiting times.'));
    }
    a = uiToRawValue(joint, a); b = uiToRawValue(joint, b);
    if (a === b) throw new Error(text('A와 B는 서로 다른 위치여야 합니다.', 'A and B must be different.'));
    var band = (state.jointTickLimits || {})[joint];
    if (band && (a < band[0] || a > band[1] || b < band[0] || b > band[1])) {
      throw new Error(text('A와 B 모두 허용 범위 안에 입력하세요.', 'Both positions must be within the allowed range.'));
    }
    return {joint_id:joint, a:a, b:b, count:count, wait_a:wa, wait_b:wb};
  }
  window.readRepeatWorkPlan = function () { return readPlan('repeat-'); };
  function updateSaveMode() {
    var on = document.getElementById('save-motion-repeat').checked;
    document.getElementById('save-repeat-editor').style.display = on ? 'grid' : 'none';
    ['lbl-save-joints-title','save-joints-picker','lbl-save-ticks-title','save-ticks-editor'].forEach(function (id) {
      var el = document.getElementById(id);
      el.style.display = on ? 'none' : (id === 'save-joints-picker' ? 'flex' : id === 'save-ticks-editor' ? 'grid' : '');
    });
  }
  window.setupRepeatPoseSave = function (plan) {
    window.repeatPoseRobotId = robot;
    var radio = document.getElementById('save-motion-repeat');
    radio.checked = !!plan; radio.disabled = !plan;
    if (plan) {
      document.getElementById('save-motion-type-panel').style.display = 'block';
      var select = document.getElementById('save-repeat-joint');
      select.replaceChildren();
      Array.from($('joint').options).forEach(function (opt) { select.appendChild(opt.cloneNode(true)); });
      select.value = plan.joint_id;
      ['a','b'].forEach(function (key) { document.getElementById('save-repeat-' + key).value = rawToUiValue(plan.joint_id, plan[key]); });
      document.getElementById('save-repeat-count').value = plan.count;
      document.getElementById('save-repeat-wait-a').value = plan.wait_a;
      document.getElementById('save-repeat-wait-b').value = plan.wait_b;
      document.getElementById('save-modal-title').textContent = text('반복 작업을 동작으로 저장', 'Save repeat movement');
      document.getElementById('save-modal-subtitle').textContent = text(
        'A·B 위치, 반복 횟수와 각 위치의 대기 시간을 함께 저장합니다. 실행 순서에서는 한 동작으로 사용합니다.',
        'Save A/B positions, cycles and waits together. The sequence uses one movement.');
    } else {
      document.getElementById('save-motion-absolute').checked = true;
    }
    updateSaveMode(); labels();
  };
  window.readRepeatPoseSave = function () {
    if (window.repeatPoseRobotId !== robot) throw new Error(text('로봇이 바뀌었습니다. 저장 창을 다시 여세요.', 'Robot changed. Reopen the save dialog.'));
    return document.getElementById('save-motion-repeat').checked ? readPlan('save-repeat-') : null;
  };
  document.querySelectorAll('[name="save-motion-type"]').forEach(function (radio) { radio.addEventListener('change', updateSaveMode); });
  $('save').addEventListener('click', function () {
    try { readPlan('repeat-'); openSaveModal(); }
    catch (err) { alertOrStyled(err.message); }
  });
  async function poll() {
    refresh();
    if (!robot || polling || pending) return;
    var requested = robot, previousJob = job;
    polling = true;
    try {
      var data = await api('?robot_id=' + encodeURIComponent(requested));
      if (robot !== requested || pending || job !== previousJob) return;
      if (data.id && (!job || data.id !== job.id)) {
        $('joint').value = data.joint_id;
        $('a').value = rawToUiValue(data.joint_id, data.targets[0]);
        $('b').value = rawToUiValue(data.joint_id, data.targets[1]);
        $('count').value = data.count; $('wait-a').value = data.waits[0]; $('wait-b').value = data.waits[1];
      }
      job = data; render();
    } catch (err) { $('status').textContent = text('상태 확인 실패: ', 'Status unavailable: ') + err.message; }
    finally { polling = false; }
  }
  $('joint').addEventListener('change', function () { $('a').value = ''; $('b').value = ''; labels(); });
  ['a','b'].forEach(function (side) {
    $('capture-' + side).addEventListener('click', async function () {
      var id = robot, joint = $('joint').value;
      try {
        var res = await fetch(BACKEND + '/api/read-pose?instance_id=' + encodeURIComponent(id));
        var data = await res.json();
        if (!data.success || !data.present || data.present[joint] === undefined) throw new Error(data.error || 'No position');
        if (robot === id && $('joint').value === joint) $(side).value = rawToUiValue(joint, data.present[joint]);
      } catch (err) { $('status').textContent = err.message; }
    });
  });
  $('start').addEventListener('click', function () {
    var joint = $('joint').value, count = Number($('count').value);
    var a = $('a').value, b = $('b').value, wa = Number($('wait-a').value), wb = Number($('wait-b').value);
    if (!a.trim() || !b.trim() || !Number.isSafeInteger(count) || count < 1 ||
        !Number.isFinite(Number(a)) || !Number.isFinite(Number(b)) || !Number.isFinite(wa) || !Number.isFinite(wb) || wa < 0 || wb < 0) {
      $('status').textContent = text('A·B 위치, 횟수, 대기 시간을 확인하세요.', 'Check positions, count and waiting times.'); return;
    }
    var payload = {robot_id: robot, joint_id: joint, a: uiToRawValue(joint,a), b: uiToRawValue(joint,b),
      count: count, wait_a: wa, wait_b: wb, speed: 'slow'};
    showModal(async function () {
      pending = true; render();
      try {
        payload.safety_inputs = getSafetyInputs();
        var result = await api('/start', payload);
        if (robot === payload.robot_id) job = result;
      } catch (err) { if (robot === payload.robot_id) job = {state:'failed', error:err.message}; }
      finally { pending = false; render(); }
    });
  });
  ['pause','resume','cancel'].forEach(function (action) {
    $(action).addEventListener('click', async function () {
      pending = true; render();
      var id = robot;
      try {
        var result = await api('/control', {robot_id:id, action:action});
        if (robot === id) job = result;
        if (result.stop_result && !result.stop_result.stopped) {
          if (job) job.error = text('정지 응답을 확인하지 못했습니다.', 'Stop was not confirmed.');
        }
      } catch (err) { if (job) job.error = err.message; }
      finally { pending = false; render(); }
    });
  });
  refresh(); poll(); setInterval(poll, 1000);
}());
