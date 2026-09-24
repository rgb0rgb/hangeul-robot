// Dexter 단순 사용자 모드 — simple.js
// 3단계: 동작 고르기 → 순서 담기 → 실행
// 안전 게이트는 백엔드가 그대로 처리 (우회 없음)

'use strict';

var BACKEND = '';   // 같은 origin (FastAPI가 서빙)
var UI_LANG_STORAGE_KEY = 'dexterUiLang';
var UI_THEME_STORAGE_KEY = 'dexterUiTheme';
var UI_THEME_MIGRATION_STORAGE_KEY = 'dexterUiThemeSbuxMigrationV1';
var UI_WIDTH_STORAGE_KEY = 'dexterUiWidth';
var ROBOT_MODEL_STORAGE_KEY = 'dexterRobotModel';
var ROBOT_DEVICE_STORAGE_KEY = 'dexterRobotDevice';
// 2026-08-09: OMX/mycobot이 포트를 하나의 키(dexterRobotDevice)로 공유하던 버그 수정.
// mycobot용으로 COM6를 입력해두면 OMX로 다시 전환했을 때도 COM6가 남아있어 OMX 쪽
// ttyUSB0가 "사라진 것처럼" 보였다 — 로봇별로 별도 키에 저장한다.
var ROBOT_DEVICE_DEFAULTS = {
  mock: '/dev/ttyUSB0',
  openmanipulator_x: '/dev/ttyUSB0',
  mycobot_280_m5: '/dev/ttyACM0'
};

function robotDeviceStorageKey(model) {
  return ROBOT_DEVICE_STORAGE_KEY + '__' + model;
}
// 2026-07-18 (사용자 지시): WSL2 usbip ALSA 드라이버가 반복적으로 hang되어 음성
// 명령이 계속 실패하자, "5. 음성 명령" 메뉴 자체를 없애기로 결정. 두 플래그를
// false로 고정해 메뉴/자동 청취 루프를 모두 끈다(코드는 남겨두되 진입점만 차단).
var IS_VOICE_MATCHING_PORT = false;
var lang = localStorage.getItem(UI_LANG_STORAGE_KEY) === 'en' ? 'en' : 'ko';
var lastMicroMovePlan = null;
var VOICE_RECOGNITION_ENABLED = IS_VOICE_MATCHING_PORT;

// 접근 키: 한글 로봇에는 **접근 키가 없다** (2026-08-21에 완전히 없앴다).
// 콘솔도 로봇 런타임도 127.0.0.1에만 열린다. 키는 같은 컴퓨터 안에서
// 자기 자신에게 문을 잠그는 일이었고, 사람이 키를 만들어 넣는 단계만 남았다.
// 옛 화면은 열자마자 키 입력 창을 띄웠고, 그 창 앞에서 화면 준비가 멈춰
// 관절 이름이 옛 상태로 남아 있었다. 창도, 키도 없다.

// ─── i18n ────────────────────────────────────────────────────────
var I18N = {
  ko: {
    title: (window.DEXTER_UI_TITLE || 'Hangeul Robot'),
    subtitle: '동작 순서 → 순서 담기 → 실행',
    expertMode: '전문가 모드 ↗',
    langBtn: 'English',
    settingsMenu: '⚙️ 환경 설정',
    settingsTheme: '화면 배경',
    settingsWidth: '화면 크기',
    settingsRobot: '로봇 선택',
    settingsDevice: '연결 포트',
    serverRestartHelp: '완전 초기화 후 재시작',
    selfCheck: '🔧 상태점검',
    selfCheckHome: '로봇을 기본 자세에 두고 시작한다',
    restampTitle: '🗂 옛 자세 이어받기',
    restampTip: '지문 계산식이 바뀌기 전에 저장된 자세를 확인하고 이어받습니다. 부품이 진짜 바뀐 자세는 건드리지 않습니다.',
    restampSubtitle: '지문 계산식에 단위·교정이 들어가면서, 부품이 바뀌지 않았는데도 그전에 저장한 자세가 막힐 수 있습니다. 값은 그대로 있습니다. 확인하면 한 번에 이어받습니다. 부품이 진짜 바뀐 자세는 건드리지 않습니다.',
    restampCounting: '세어 보는 중…',
    restampNothing: '이어받을 자세가 없습니다.',
    restampMovable: '이어받을 수 있는 자세',
    restampSkipped: '부품이 달라져 건드리지 않을 자세',
    restampRunning: '이어받는 중…',
    restampDone: '이어받았습니다:',
    restampFailed: '이어받지 못했습니다.',
    checkPick: '점검할 로봇 고르기',
    checkPickFirst: '점검할 로봇을 하나 이상 고르세요.',
    checkLoading: '로봇 목록을 불러오는 중…',
    checkNoRobot: '등록된 로봇이 없습니다.',
    checkAllOk: '모두 정상',
    checkHasProblem: '대에 문제가 있습니다',
    selfCheckTip: '쓰기 전에 로봇을 조금씩 움직여 보고 부품마다 이상 여부를 알려 줍니다.',
    selfCheckTitle: '🔧 상태점검',
    selfCheckSubtitle: '쓰기 전에 관절을 조금씩 움직여 보고 부품마다 알려 줍니다. 응답하지 않는 곳은 움직여 보지 않습니다.',
    selfCheckStart: '점검 시작',
    selfCheckRunning: '점검하는 중…',
    selfCheckWait: '움직이고 있습니다. 기다려 주세요.',
    selfCheckDone: '점검 끝 — ',
    selfCheckFailed: '점검하지 못했습니다.',
    selfCheckClose: '닫기',
    usageTitle: '사용 기록',
    usageNone: '사용 기록: 아직 없습니다.',
    usageTime: '총 움직인 시간',
    usageCount: '움직인 횟수',
    usageBusiest: '제일 많이 쓴 곳',
    usageLastCheck: '마지막 점검',
    warn: '안전 주의: 이 화면은 실제 로봇과 연결됩니다. 반드시 운영자 입회 하에 사용하세요.',
    warnActive: '[실행 중] 실제 로봇이 움직입니다 — 비상정지 준비',
    step1: '동작 순서',
    step2: '실행 순서(드래앤드롭 지원)',
    step3: '반복 / 휴식',
    repeatHint: '반복 없이 1회 실행이 기본입니다. 여러 번 반복하려면 횟수를 입력하세요.',
    repeatToggleOpen: '설정 열기 ▾',
    repeatToggleClose: '설정 닫기 ▴',
    labelCount: '반복 횟수', labelTimes: '회', labelWork: '작동', labelRest: '휴식', labelMin: '분',
    queueEmpty: '위에서 동작을 골라 여기에 담으세요',
    clearQueue: '전체 비우기',
    preview: '미리보기',
    execBtn: '▶ 실행 시작',
    execRunning: '실행 중...',
    execDone: '완료',
    execBlocked: '차단됨',
    verified: '검증됨',
    unverified: '미검증',
    modalTitle: '⚠️ 실제 로봇이 움직입니다',
    modalSubtitle: '아래 5가지를 직접 확인하셨습니까? 확인 후 실행 버튼을 누르세요.',
    mItem1: '운영자(나)가 현장에 있고 언제든 개입 가능하다',
    mItem2: '로봇 주변 작업 공간이 정리되어 있다',
    mItem3: '로봇 가동 범위 안에 사람이 없다',
    mItem4: '수동 정지 장치를 손에 닿는 곳에 두었다',
    mItem5: '비상 정지(E-Stop)가 준비되어 있다',
    modalCancel: '취소',
    modalConfirm: '모두 확인 → 실행',
    loadFail: '동작 목록 불러오기 실패 (백엔드 미연결)',
    previewOk: '매핑 완료',
    previewFail: '미매핑 단계 있음',
    schedulePreview: '스케줄: {total}회 / {mode} / 휴식블록 {rest}개',
    gripperLabel: '손 (좁게: + / 넓게: -)',
    saveSequence: '💾 순서 저장',
    loadSequence: '📂 순서 불러오기',
    jogTitle: '자세 만들기',
    jogHint: '안전 수칙 범위 내에서 각 관절값을 수동 조작(Jog)하고, 원하는 각도를 새로운 카드로 등록 저장할 수 있습니다.',
    adminLimits: '⚙️ 안전 범위 설정',
    optCount: '🔢 지정 횟수 반복 (Repeat Count Mode)',
    optTime: '⏱️ 시간제 작동/휴식 (Work/Rest Timer Mode)',
    totalHours: '⏱️ 전체 작업시간:',
    hours: '시간',
    estop: '🚨 긴급 정지',
    estopReset: '🟢 긴급 정지 해제',
    aiTitle: '명령',
    voiceTitle: '명령 입력',
    voicePreset: '음성 명령 예시 선택 (Presets)',
    voiceDirect: '텍스트로 명령 입력',
    voiceSend: '저장',
    visionTitle: '',
    visionScenario: '카메라 화면 상황 선택 (Scenario)',
    visionPlaceholder: '📷 카메라 피드가 비어 있습니다.',
    trackTitle: '목표물 추적',
    trackFollow: '팔이 목표물을 따라간다',
    trackFollowDesc: '끄면 보기만 합니다. 켜면 실제 로봇이 조금씩 움직입니다 — 사람이 옆에 있어야 합니다.',
    trackStart: '시작',
    trackStop: '중지',
    trackClear: '목표 해제',
    voiceRecord: '',
    voiceRecordActive: '',
    
    // Additional UI Elements translations
    tabMovements: '동작 순서',
    tabTargets: '대상 고르기',
    noTargets: '등록된 대상이 없습니다. 아래 \'카메라 영상\' 패널에서 대상을 등록해 주세요.',
    modalSaveSeqTitle: '💾 실행 순서 저장 (Save Sequence)',
    modalSaveSeqSubtitle: '현재 대기열에 추가된 모든 동작 순서를 레시피로 저장합니다.',
    lblSeqSaveName: '저장할 순서 이름 (Recipe Name)',
    seqSaveNamePlaceholder: '예: 물건을 집어서 탁자위로 올리기',
    btnSaveSeqCancel: '취소',
    btnSaveSeqConfirm: '저장',
    modalLoadSeqTitle: '📂 저장된 순서 불러오기 (Load Sequence)',
    modalLoadSeqSubtitle: '이전에 저장했던 동작 순서를 가져와 대기열에 채워 넣습니다.',
    btnLoadSeqClose: '닫기',
    lblJogHeaderJoint: '관절명 (Joint)',
    lblJogHeaderValue: '현재 수치 (Value)',
    lblJogHeaderDirect: '직접 입력 (Direct Target)',
    lblJogHeaderJog: '미세 조작 (Jog)',
    j11Label: '고정대',
    j12Label: '관절 1',
    j13Label: '관절 2',
    j14Label: '관절 3',
    btnReadPose: '🔄 현재값 읽기',
    btnSavePose: '💾 자세 저장',
    btnMove: '이동',
    placeholderValue: '수치',
    lblSaveNameKr: '동작 이름',
    lblSaveNameEn: '동작 이름',
    lblSaveDescKr: '동작 설명',
    lblSaveDescEn: '동작 설명',
    lblSaveIcon: '🎨 아이콘 이모지 선택 (Select Icon)',
    saveIconPlaceholder: '직접 이모지 입력도 가능',
    lblSaveTip: '💡 팁: Windows 키 + 마침표(.)를 누르거나, \'📁 파일 선택\' 버튼을 클릭해 PC의 커스텀 이미지를 등록할 수 있습니다.',
    lblSaveDelay: '⏱️ 동작 완료 후 대기 시간 (Dwell/Wait Time, 초)',
    lblSaveJointsTitle: '💾 저장할 관절 선택 (미선택 관절은 현재 위치 유지)',
    lblSaveTicksTitle: '🔧 각도 목표값 세부 설정 (Target Ticks Editor)',
    btnSavePoseCancel: '취소',
    btnSavePoseSubmit: '저장 완료',
    btnEditDelete: '삭제',
    btnFileSelect: '📁 파일 선택',
    voiceGridTitle: '등록 음성 (모두 활성화 상태)',
    voiceMappedTitle: '명령 후보 저장',
    voiceMappedPhrasePrefix: '입력된 명령:',
    voiceMappedActionLabel: '저장할 실행 후보 지정',
    voiceSaveMapping: '💾 명령 후보 매칭 저장',
    voiceFeedbackDefault: '텍스트 명령을 전송하면 실행 후보가 여기에 표시됩니다. 필요하면 후보를 저장해 다음 실행에 사용합니다.',
    lblVisionScenario: '실제 카메라 촬영 등록',
    visionCaptureLabelPlaceholder: '예: 컵, 빨간 물건, 작업 대상',
    btnVisionStart: '실행',
    btnVisionCapture: '촬영',
    btnVisionStop: '정지',
    modalAdminTitle: '⚙️ 관리자 안전 범위 설정 (Admin Limits)',
    modalAdminSubtitle: '각 관절의 안전 각도 가이드라인(도) 및 손 범위(틱)를 설정합니다. 이 범위 외의 수치로 동작 저장 시 미검증 카드로 강제 분류됩니다.',
    lblAdminColItem: '관절 / 범위항목',
    lblAdminColMin: '최소값 (Min)',
    lblAdminColMax: '최대값 (Max)',
    btnAdminClose: '취소',
    btnAdminSubmit: '설정 적용',
    voiceInputPlaceholder: '예: 다시시작',
    tabRange: '📐 관절 구동 범위',
    tabTemp: '🔥 관절 온도 임계값',
    lblAdminTempTitle: '관절 온도 정지 임계값 (℃) — 이 온도를 넘으면 새 동작을 거부합니다 (정지/일시정지는 예외)',
    lblAdminTempAll: '전체 관절에 동일 값 적용:',
    btnAdminTempApplyAll: '전체 적용',
    tabVel: '⚡ 관절 동작 속도',
    lblAdminVelTitle: '관절 동작 속도 (1~200, 클수록 빠름 · 1단위≈0.229rpm) — 일반 동작에만 적용, 정지/일시정지 속도는 고정입니다',
    lblAdminVelAll: '전체 관절에 동일 값 적용:',
    btnAdminVelApplyAll: '전체 적용',
    lblAdminVelHint: '기본값: 팔 40, 손 50. 상한 200은 실물 검증된 범위입니다.',
    lblAdminProfileTitle: '기본 이동 프로파일',
    lblAdminProfileDesc: '이동 거리가 멀면 구간을 나눠서 실행합니다 — 나뉘는 구간 크기가 프로파일마다 다릅니다. SAFE는 가장 촘촘하게 나눠 안전하지만 자주 끊기고, FAST는 덜 나눠 더 부드럽게 움직입니다(속도/가속도 값 자체는 세 프로파일 모두 실물 검증된 값입니다).',
    optProfileSafe: 'SAFE — 가장 촘촘히 분할(800틱), 가장 안전, 가장 자주 끊김',
    optProfileSmooth: 'SMOOTH — 더 촘촘히 분할(400틱), 저속·저가속, 더 자주 끊김',
    optProfileFast: 'FAST — 덜 분할(1200틱), 더 빠르고 부드러움',
    optProfileCustom: 'CUSTOM — 아래 값을 직접 지정',
    lblAdminCustomStage: '분할 임계값 (틱, 100~1200)',
    lblAdminCustomAccel: '가속도 (6~40)',
    lblAdminCustomHint: '상한(1200/40)은 FAST 프로파일의 실물 검증 값을 넘지 않습니다. 값이 클수록 덜 나뉘고(끊김 감소) 더 빠르게 움직입니다.',
    tabPerson: '🚨 사람 감지',
    btnSecMonitoring: '🔒 보안 모니터링',
    modalSecTitle: '🔒 보안 모니터링 (Security Monitoring)',
    sllmHelperBtn: '🧠 SLLM 도우미',
    sllmHelperTitle: '말로 찾기 — 저장된 자세/순서 중에서 후보만 제안합니다. 실행은 기존 확인 절차를 그대로 거칩니다.',
    sllmSubtitle: '저장된 자세·순서 중에서 후보만 제안합니다. 관절 목표값을 새로 만들지 않으며, 실행은 지금까지와 똑같이 확인 절차를 거칩니다.',
    sllmTargetLabel: '대상 로봇',
    sllmRuntimeBadge: '검색 라우터',
    sllmSearchBtn: '🔍 후보 찾기',
    sllmQueryPlaceholder: '예: 기본자세로, 왼쪽 90도, 물건 집기',
    sllmCandidatesEmpty: '찾을 동작을 한 줄로 입력하세요.',
    sllmEnabledLabel: 'SLLM 도우미 사용',
    sllmSeqLabel: '저장 순서도 검색',
    sllmMinLabel: '최소 점수',
    sllmMaxLabel: '후보 개수',
    sllmSaveBtn: '설정 저장',
    sllmCloseBtn: '닫기',
    awayGroupTitle: '부재 모드',
    sllmSettingsSummary: '⚙️ SLLM 설정',
    saveNameKrPlaceholder: '예: 바닥 물건 집기 자세',
    seqIconPlaceholder: '직접 이모지 입력 또는 이미지 데이터',
    awayBtnTitle: '자리를 비우거나 잠들기 전에 켜면, 켜져 있는 동안 로봇이 어떤 요청에도 움직이지 않습니다.',
    assignBtnTitle: '이름을 붙이지 않고 이 로봇의 현재 실행 순서만 즉시 바꿉니다 (1회성, 순서 저장 목록에는 남지 않음)',
    lblMicroTitle: '미세 이동 전용 모드',
    lblMicroDesc: '1회 최대 200틱, 지정 횟수만큼 천천히 반복 조그합니다.',
    lblMicroJoint: '관절',
    lblMicroDelta: '미세 이동',
    lblMicroRepeat: '횟수',
    btnMicroRun: '실행',
    modalSecSubtitle: '보안 가드 시스템이 실시간으로 탐지한 시스템 접근 및 제어 요청의 보안 이력을 표시합니다. (읽기 전용)',
    lblSecStatusLabel: '가드 감시 상태:',
    lblSecDetailTitle: '⚠️ 위협 상세 정보 (Threat Details)',
    btnSecClose: '닫기',
    btnSecResolve: '✔️ 보안 경보 해제 및 확인 완료',
    lblPersonCameraEnabled: '카메라 사람 감지 사용',
    lblPersonCameraEnabledDesc: '카메라가 없는 로봇은 끄세요. 끄면 운영자 수동 확인이 유일한 안전 체크가 되며, 그 사실이 기록에 남습니다. 켠 상태에서 카메라 연결이 끊기면 실행이 차단됩니다.',
    lblAdminPersonTitle: '카메라 사람 감지 시 실행 차단 정책',
    lblPersonPolicyZone: '위험 구역 기반 (권장)',
    lblPersonPolicyZoneDesc: '아래 위험 구역에 걸친 사람만 차단. 구역 밖 운영자는 감독 가능.',
    lblPersonPolicyFull: '화면 전체 차단',
    lblPersonPolicyFullDesc: '화면 어디든 사람이 보이면 차단. 실행 순간 카메라 밖으로 나가는 운영 방식.',
    lblPersonPolicyWarn: '경고만 (차단 안 함)',
    lblPersonPolicyWarnDesc: '감지 내용을 기록·경고만 하고 실행은 허용. 자동 차단 없음.',
    lblAdminZoneTitle: '위험 구역 좌표 (화면 비율 0~1: 좌 x1 / 상 y1 / 우 x2 / 하 y2)',
    lblAdminZoneHint: '카메라 위치/각도를 바꾸면 이 구역도 반드시 다시 설정하세요.',
  },
  en: {
    title: (window.DEXTER_UI_TITLE || 'Hangeul Robot'),
    subtitle: 'Action Order → Queue → Execute',
    expertMode: 'Expert Mode ↗',
    langBtn: '한국어',
    settingsMenu: '⚙️ Settings',
    settingsTheme: 'Background',
    settingsWidth: 'Width',
    settingsRobot: 'Robot',
    settingsDevice: 'Serial port',
    serverRestartHelp: 'Full reset & restart',
    selfCheck: '🔧 Status check',
    selfCheckHome: 'Put the robot in its home pose before starting',
    restampTitle: '🗂 Carry over old poses',
    restampTip: 'Checks poses saved before the fingerprint formula changed and carries them over. Poses whose parts really changed are left alone.',
    restampSubtitle: 'When units and calibration entered the fingerprint, poses saved before that can be blocked even though no part changed. Their values are intact. Confirm and they are carried over at once. Poses whose parts really changed are left alone.',
    restampCounting: 'Counting…',
    restampNothing: 'Nothing to carry over.',
    restampMovable: 'Poses that can be carried over',
    restampSkipped: 'Left alone (parts really changed)',
    restampRunning: 'Carrying over…',
    restampDone: 'Carried over:',
    restampFailed: 'Could not carry them over.',
    checkPick: 'Pick robots to check',
    checkPickFirst: 'Pick at least one robot to check.',
    checkLoading: 'Loading robots…',
    checkNoRobot: 'No robots registered.',
    checkAllOk: 'all OK',
    checkHasProblem: 'with problems',
    selfCheckTip: 'Moves each joint a little before you use the robot and tells you how each part is doing.',
    selfCheckTitle: '🔧 Status check',
    selfCheckSubtitle: 'Moves each joint a little and reports on every part. Parts that do not answer are not moved.',
    selfCheckStart: 'Start check',
    selfCheckRunning: 'Checking…',
    selfCheckWait: 'The robot is moving. Please wait.',
    selfCheckDone: 'Done — ',
    selfCheckFailed: 'Could not run the check.',
    selfCheckClose: 'Close',
    usageTitle: 'Usage',
    usageNone: 'Usage: nothing recorded yet.',
    usageTime: 'Time moving',
    usageCount: 'Moves',
    usageBusiest: 'Busiest joint',
    usageLastCheck: 'Last check',
    warn: 'Safety notice: This interface is connected to the real robot. Use only with an operator present.',
    warnActive: '[EXECUTING] Robot is moving — keep E-Stop ready',
    step1: 'Action Order',
    step2: 'Execution queue (Drag & Drop)',
    step3: 'Repeat / Rest',
    repeatHint: 'Default is 1 run (no repeat). Enter a count for repeated runs.',
    repeatToggleOpen: 'Open settings ▾',
    repeatToggleClose: 'Close settings ▴',
    labelCount: 'Repeat', labelTimes: '×', labelWork: 'Work', labelRest: 'Rest', labelMin: 'min',
    queueEmpty: 'Pick movements above to add them here',
    clearQueue: 'Clear all',
    preview: 'Preview',
    execBtn: '▶ Start Execution',
    execRunning: 'Running...',
    execDone: 'Done',
    execBlocked: 'Blocked',
    verified: 'Verified',
    unverified: 'Unverified',
    modalTitle: '⚠️ The real robot will move',
    modalSubtitle: 'Have you confirmed all 5 items below? Press Execute when ready.',
    mItem1: 'I (the operator) am present and can intervene at any time',
    mItem2: 'The workspace around the robot is clear',
    mItem3: 'No person is inside the robot\'s range of motion',
    mItem4: 'A manual stop device is within reach',
    mItem5: 'The Emergency Stop (E-Stop) is ready',
    modalCancel: 'Cancel',
    modalConfirm: 'All confirmed → Execute',
    loadFail: 'Failed to load catalog (backend not connected)',
    previewOk: 'All mapped',
    previewFail: 'Unmapped step(s)',
    schedulePreview: 'Schedule: {total} cycles / {mode} / {rest} rest block(s)',
    gripperLabel: 'Hand (Close: + / Open: -)',
    saveSequence: '💾 Save Sequence',
    loadSequence: '📂 Load Sequence',
    jogTitle: 'Create Pose',
    jogHint: 'Jog joint values within safety limits and register new pose cards for one-click execution.',
    adminLimits: '⚙️ Safety Limits',
    optCount: '🔢 Repeat Count Mode',
    optTime: '⏱️ Work/Rest Timer Mode',
    totalHours: '⏱️ Total Duration:',
    hours: 'hours',
    estop: '🚨 E-STOP',
    estopReset: '🟢 Release E-Stop',
    aiTitle: 'Command',
    voiceTitle: 'Command Input',
    voicePreset: 'Select Voice Command Preset',
    voiceDirect: 'Type a command',
    voiceSend: 'Save',
    visionTitle: '',
    visionScenario: 'Select Camera Scenario',
    visionPlaceholder: '📷 Camera feed is empty.',
    trackTitle: 'Target tracking',
    trackFollow: 'Let the arm follow the target',
    trackFollowDesc: 'Off means observe only. On moves the real robot in small steps — stay next to it.',
    trackStart: 'Start',
    trackStop: 'Stop',
    trackClear: 'Release target',
    voiceRecord: 'Voice disabled',
    voiceRecordActive: 'Voice disabled',
    
    // Additional UI Elements translations
    tabMovements: 'Action Order',
    tabTargets: 'Pick Target',
    noTargets: 'No registered targets. Please register one in the Camera panel below.',
    modalSaveSeqTitle: '💾 Save Sequence',
    modalSaveSeqSubtitle: 'Saves all movements in the current queue as a sequence recipe.',
    lblSeqSaveName: 'Sequence Recipe Name',
    seqSaveNamePlaceholder: 'e.g. pick up cup and place on table',
    btnSaveSeqCancel: 'Cancel',
    btnSaveSeqConfirm: 'Save',
    modalLoadSeqTitle: '📂 Load Saved Sequence',
    modalLoadSeqSubtitle: 'Load previously saved movement sequence back into the active queue.',
    btnLoadSeqClose: 'Close',
    lblJogHeaderJoint: 'Joint Name',
    lblJogHeaderValue: 'Current Value',
    lblJogHeaderDirect: 'Direct Target',
    lblJogHeaderJog: 'Jog',
    j11Label: 'Base',
    j12Label: 'Joint 1',
    j13Label: 'Joint 2',
    j14Label: 'Joint 3',
    btnReadPose: '🔄 Read Current',
    btnSavePose: '💾 Save Pose',
    btnMove: 'Go',
    placeholderValue: 'Value',
    lblSaveNameKr: 'Movement Name',
    lblSaveNameEn: 'Movement Name',
    lblSaveDescKr: 'Movement Description',
    lblSaveDescEn: 'Movement Description',
    lblSaveIcon: '🎨 Select Emoji Icon',
    saveIconPlaceholder: 'Or enter custom emoji here',
    lblSaveTip: '💡 Tip: Press Windows Key + dot (.) or click \'📁 Select File\' to register a custom image from your PC.',
    lblSaveDelay: '⏱️ Dwell/Wait Time after completion (sec)',
    lblSaveJointsTitle: '💾 Select Active Joints (unchecked retain position)',
    lblSaveTicksTitle: '🔧 Target Ticks Editor',
    btnSavePoseCancel: 'Cancel',
    btnSavePoseSubmit: 'Save',
    btnEditDelete: 'Delete',
    btnFileSelect: '📁 Select File',
    voiceGridTitle: 'Registered Voice (All Active)',
    voiceMappedTitle: '🔊 Command Candidate Mapping',
    voiceMappedPhrasePrefix: 'Recognized Command:',
    voiceMappedActionLabel: 'Select Candidate to Save',
    voiceSaveMapping: '💾 Save Command Candidate',
    voiceFeedbackDefault: 'Send a typed command to show execution candidates here. Save a candidate if you want to reuse it later.',
    lblVisionScenario: 'Register Real Camera Object',
    visionCaptureLabelPlaceholder: 'e.g., cup, red block, target',
    btnVisionStart: 'Run',
    btnVisionCapture: 'Capture',
    btnVisionStop: 'Stop',
    modalAdminTitle: '⚙️ Safety Limits Setting (Admin Limits)',
    modalAdminSubtitle: 'Configure safety range guidelines (deg) and gripper range (ticks). Custom poses beyond these limits are classified as unverified.',
    lblAdminColItem: 'Joint / Item',
    lblAdminColMin: 'Min Value',
    lblAdminColMax: 'Max Value',
    btnAdminClose: 'Cancel',
    btnAdminSubmit: 'Apply Limits',
    voiceInputPlaceholder: 'e.g., restart',
    tabRange: '📐 Joint Range',
    tabTemp: '🔥 Temp Limits',
    lblAdminTempTitle: 'Joint Temp Limit (℃) — Rejects new motions if exceeded (except stop/pause)',
    lblAdminTempAll: 'Apply same limit to all joints:',
    btnAdminTempApplyAll: 'Apply All',
    tabVel: '⚡ Joint Speed',
    lblAdminVelTitle: 'Joint motion speed (1–200, higher = faster · 1 unit≈0.229rpm) — normal motions only; stop/pause speeds are fixed',
    lblAdminVelAll: 'Apply same speed to all joints:',
    btnAdminVelApplyAll: 'Apply All',
    lblAdminVelHint: 'Defaults: arm 40, hand 50. Max 200 is the hardware-verified ceiling.',
    lblAdminProfileTitle: 'Default motion profile',
    lblAdminProfileDesc: 'Long moves are split into stages — the stage size differs per profile. SAFE splits most finely (safest, most stuttering); FAST splits least (smoother, faster). The velocity/acceleration values themselves are all hardware-verified for all three profiles.',
    optProfileSafe: 'SAFE — finest split (800 ticks), safest, most stuttering',
    optProfileSmooth: 'SMOOTH — finer split (400 ticks), low speed/accel, more stuttering',
    optProfileFast: 'FAST — coarser split (1200 ticks), faster and smoother',
    optProfileCustom: 'CUSTOM — specify your own values below',
    lblAdminCustomStage: 'Stage threshold (ticks, 100–1200)',
    lblAdminCustomAccel: 'Acceleration (6–40)',
    lblAdminCustomHint: 'The cap (1200/40) never exceeds the hardware-verified FAST profile values. Higher values split less (less stuttering) and move faster.',
    tabPerson: '🚨 Person Detection',
    lblPersonCameraEnabled: 'Use camera person detection',
    lblPersonCameraEnabledDesc: 'Turn off for robots without a camera. When off, operator manual confirmation is the only safety check (recorded in evidence). When on, execution is blocked if the camera becomes unavailable.',
    lblAdminPersonTitle: 'Execution blocking policy when a person is detected',
    lblPersonPolicyZone: 'Danger zone based (recommended)',
    lblPersonPolicyZoneDesc: 'Blocks only when a person overlaps the danger zone below. Operator outside the zone can supervise.',
    lblPersonPolicyFull: 'Block on full frame',
    lblPersonPolicyFullDesc: 'Blocks whenever a person is visible anywhere. For workflows where the operator steps out of view during execution.',
    lblPersonPolicyWarn: 'Warn only (no blocking)',
    lblPersonPolicyWarnDesc: 'Records and warns on detection but allows execution. No automatic blocking.',
    lblAdminZoneTitle: 'Danger zone coords (frame ratio 0–1: left x1 / top y1 / right x2 / bottom y2)',
    lblAdminZoneHint: 'If you move or re-aim the camera, you must reconfigure this zone.',
    btnSecMonitoring: '🔒 Security Guard',
    modalSecTitle: '🔒 Security Monitoring',
    sllmHelperBtn: '🧠 SLLM Helper',
    sllmHelperTitle: 'Find by words — suggests candidates from saved poses/sequences only. Running still goes through the usual confirmation.',
    sllmSubtitle: 'Suggests candidates from saved poses and sequences only. It never invents joint targets, and running still goes through the same confirmation as before.',
    sllmTargetLabel: 'Target robot',
    sllmRuntimeBadge: 'Search router',
    sllmSearchBtn: '🔍 Find candidates',
    sllmQueryPlaceholder: 'e.g. go home, turn left 90, pick up',
    sllmCandidatesEmpty: 'Type what you are looking for in one line.',
    sllmEnabledLabel: 'Use SLLM helper',
    sllmSeqLabel: 'Search saved sequences too',
    sllmMinLabel: 'Min score',
    sllmMaxLabel: 'Candidates',
    sllmSaveBtn: 'Save settings',
    sllmCloseBtn: 'Close',
    awayGroupTitle: 'Away Mode',
    sllmSettingsSummary: '⚙️ SLLM settings',
    saveNameKrPlaceholder: 'e.g. pose for picking up an object from the floor',
    seqIconPlaceholder: 'Type an emoji, or paste image data',
    awayBtnTitle: 'Turn this on before you leave or go to sleep. While it is on, the robot will not move for any request.',
    assignBtnTitle: "Replaces this robot's current run order right now, without naming it (one-time; it is not kept in the saved list)",
    lblMicroTitle: 'Fine-Move Only Mode',
    lblMicroDesc: 'Up to 200 ticks per step, repeated slowly for the number of times you set.',
    lblMicroJoint: 'Joint',
    lblMicroDelta: 'Fine move',
    lblMicroRepeat: 'Times',
    btnMicroRun: 'Run',
    modalSecSubtitle: 'Displays security logs of system access and execution requests evaluated by Security Guard. (Read-Only)',
    lblSecStatusLabel: 'Guard Status:',
    lblSecDetailTitle: '⚠️ Threat Details',
    btnSecClose: 'Close',
    btnSecResolve: '✔️ Resolve Security Alerts',
  }
};
function t() { return I18N[lang]; }

// ─── 상태 ────────────────────────────────────────────────────────
var state = {
  catalog: [],        // [{skill_id, display_name_kr, icon, color, ...}]
  robotCardLabel: '',
  robotCardFamily: '',
  queue: [],          // [{skill_id, display_name_kr, display_name_en, icon}]
  running: false,
  paused: false,
  resumeExecution: null,
  previewResult: null,
  estopActive: false,
  activeTimer: null,
  serverVoiceTimer: null,
  serverVoiceLastCommand: '',
  serverVoiceLastCommandAt: 0,
  targets: [],        // Registered custom camera targets
  savedSequences: {}, // Saved frequently used movement recipes
  sequenceIcons: {},
  sequenceIconEditName: null,
  voiceIconEditIndex: null,
  voiceMappings: [],
  safetyLimits: null,
  jointTickLimits: {},
  robotJoints: null,
  armJointIds: [11, 12, 13, 14],
  allJointIds: [11, 12, 13, 14, 15],
  gripperJointId: 15,
  cardDragActive: false
};

var DEFAULT_ROBOT_JOINTS = {
  robot_id: 'openmanipulator_x',
  arm_joints: [
    { id: '11', joint_id: 11, role: 'arm', label_kr: '고정대', label_en: 'Base', default_ticks: 2048 },
    { id: '12', joint_id: 12, role: 'arm', label_kr: '관절 1', label_en: 'Joint 1', default_ticks: 1150 },
    { id: '13', joint_id: 13, role: 'arm', label_kr: '관절 2', label_en: 'Joint 2', default_ticks: 2650 },
    { id: '14', joint_id: 14, role: 'arm', label_kr: '관절 3', label_en: 'Joint 3', default_ticks: 2048 }
  ],
  gripper_joint: { id: '15', joint_id: 15, role: 'gripper', label_kr: '손', label_en: 'Hand', default_ticks: 1958 }
};

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeRobotJoints(payload) {
  var data = payload && Array.isArray(payload.arm_joints) ? payload : DEFAULT_ROBOT_JOINTS;
  var arm = data.arm_joints.slice(0, 8).map(function(j) {
    var id = parseInt(j.joint_id !== undefined ? j.joint_id : j.id, 10);
    return {
      id: String(id),
      joint_id: id,
      role: 'arm',
      label_kr: j.label_kr || ('J' + id),
      label_en: j.label_en || ('J' + id),
      default_ticks: parseInt(j.default_ticks !== undefined ? j.default_ticks : 2048, 10)
    };
  }).filter(function(j) { return !isNaN(j.joint_id); });
  if (arm.length < 1) return normalizeRobotJoints(DEFAULT_ROBOT_JOINTS);
  var gripper = null;
  if (data.gripper_joint) {
    var gid = parseInt(data.gripper_joint.joint_id !== undefined ? data.gripper_joint.joint_id : data.gripper_joint.id, 10);
    if (!isNaN(gid)) {
      gripper = {
        id: String(gid),
        joint_id: gid,
        role: 'gripper',
        label_kr: data.gripper_joint.label_kr || ('J' + gid + ': 손'),
        label_en: data.gripper_joint.label_en || ('J' + gid + ': Hand'),
        default_ticks: parseInt(data.gripper_joint.default_ticks !== undefined ? data.gripper_joint.default_ticks : 1958, 10)
      };
    }
  }
  data.arm_joints = arm;
  data.gripper_joint = gripper;
  data.all_joints = gripper ? arm.concat([gripper]) : arm.slice();
  return data;
}

function applyRobotJoints(payload) {
  state.robotJoints = normalizeRobotJoints(payload);
  var excluded = (payload && Array.isArray(payload.excluded_joints))
    ? payload.excluded_joints.map(function(j) {
        var raw = String(j).replace(/^joint_/, '');
        return parseInt(raw, 10);
      }).filter(function(j) { return !isNaN(j); })
    : [];
  // 제외 관절도 정상 모델에서는 존재하므로 화면에는 유지한다.
  state.excludedJointIds = excluded;
  state.armJointIds = state.robotJoints.arm_joints.map(function(j) { return j.joint_id; });
  state.allJointIds = state.robotJoints.all_joints.map(function(j) { return j.joint_id; });
  state.gripperJointId = state.robotJoints.gripper_joint ? state.robotJoints.gripper_joint.joint_id : null;
  if (payload && payload.joint_tick_limits) {
    state.jointTickLimits = normalizeJointTickLimits(payload);
  }
  renderRobotJointUi();
  rebuildMicroMoveDefs();
  if (window.refreshRepeatWork) window.refreshRepeatWork(true);
}

function allJointIds() {
  return state.allJointIds && state.allJointIds.length ? state.allJointIds : [11, 12, 13, 14, 15];
}

function armJointIds() {
  return state.armJointIds && state.armJointIds.length ? state.armJointIds : [11, 12, 13, 14];
}

function isExcludedJoint(jointId) {
  return Array.isArray(state.excludedJointIds)
    && state.excludedJointIds.indexOf(parseInt(jointId, 10)) >= 0;
}

function operableJointIds() {
  return allJointIds().filter(function(jointId) { return !isExcludedJoint(jointId); });
}

function jointMeta(jointId) {
  var joints = (state.robotJoints && state.robotJoints.all_joints) || DEFAULT_ROBOT_JOINTS.arm_joints.concat([DEFAULT_ROBOT_JOINTS.gripper_joint]);
  for (var i = 0; i < joints.length; i += 1) {
    if (parseInt(joints[i].joint_id, 10) === parseInt(jointId, 10)) return joints[i];
  }
  return { joint_id: parseInt(jointId, 10), label_kr: 'J' + jointId, label_en: 'J' + jointId, default_ticks: 2048 };
}

function jointLabel(jointId) {
  var meta = jointMeta(jointId);
  return lang === 'ko' ? (meta.label_kr || meta.label_en) : (meta.label_en || meta.label_kr);
}

function isMyCobotUi() {
  return getRobotModel() === 'mycobot_280_m5'
    || !!(state.robotJoints && state.robotJoints.robot_family === 'mycobot_280_m5');
}

function isGripperJoint(jointId) {
  return state.gripperJointId !== null && parseInt(jointId, 10) === parseInt(state.gripperJointId, 10);
}

// MyCobot API는 팔을 millidegrees로 주고받지만 화면은 degrees로 표시한다.
// OMX 화면/경로는 기존 ticks 동작을 그대로 유지한다.
function rawToUiValue(jointId, raw) {
  var n = Number(raw);
  if (!isFinite(n)) return raw;
  if (isMyCobotUi() && !isGripperJoint(jointId)) return n / 1000;
  return n;
}

function uiToRawValue(jointId, value) {
  var n = Number(value);
  if (!isFinite(n)) return NaN;
  if (isMyCobotUi() && !isGripperJoint(jointId)) return Math.round(n * 1000);
  return Math.round(n);
}

function formatUiValue(jointId, raw) {
  var n = rawToUiValue(jointId, raw);
  if (!isFinite(Number(n))) return String(raw);
  if (isMyCobotUi() && !isGripperJoint(jointId)) return Number(n).toFixed(2);
  return String(Math.round(Number(n)));
}

function formatUiRange(jointId, range) {
  if (!range) return '';
  var suffix = '';
  if (isMyCobotUi()) suffix = isGripperJoint(jointId) ? ' %' : '°';
  return '(' + formatUiValue(jointId, range[0]) + ' ~ ' + formatUiValue(jointId, range[1]) + suffix + ')';
}

function uiDeltaToRaw(jointId, delta) {
  return uiToRawValue(jointId, delta) - uiToRawValue(jointId, 0);
}

function uiJogPresets(jointId) {
  if (!isMyCobotUi()) return [-50, -10, 10, 50];
  return isGripperJoint(jointId) ? [-10, -1, 1, 10] : [-5, -1, 1, 5];
}

function loadRobotJoints() {
  var model = encodeURIComponent(getRobotModel());
  return fetch(BACKEND + '/api/robot-joints?robot_model=' + model)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      // 어느 로봇인지는 콘솔이 정한다. 브라우저에 남아있던 예전 값(단일 로봇
      // 시절의 'mock' 등)을 그대로 쓰면 MyCobot 화면에서 OMX 관절 번호가 나간다.
      if (data && data.robot_model) {
        localStorage.setItem(ROBOT_MODEL_STORAGE_KEY, data.robot_model);
        if (data.device) {
          localStorage.setItem(robotDeviceStorageKey(data.robot_model), data.device);
        }
        // 환경 설정의 로봇 종류 드롭다운도 지금 로봇을 가리키게 한다.
        var modelSelect = document.getElementById('robot-model-select');
        if (modelSelect) modelSelect.value = data.robot_model;
        var portSelect = document.getElementById('robot-device-select');
        if (portSelect && data.device) portSelect.value = data.device;
      }
      applyRobotJoints(data);
      return data;
    })
    .catch(function() {
      applyRobotJoints(DEFAULT_ROBOT_JOINTS);
      return DEFAULT_ROBOT_JOINTS;
    });
}

var DEFAULT_VOICE_MAPPINGS = state.voiceMappings.slice();
var VOICE_MAPPING_STORAGE_KEY = 'dexterVoiceMappingsActualV2';
var CARD_ORDER_STORAGE_KEY = 'dexterMovementCardOrderV1';

function loadVoiceMappingsFromStorage() {
  try {
    var raw = localStorage.getItem(VOICE_MAPPING_STORAGE_KEY);
    if (!raw) return DEFAULT_VOICE_MAPPINGS.slice();
    var parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_VOICE_MAPPINGS.slice();
    return parsed.filter(function(item) {
      return item && typeof item.phrase === 'string' && typeof item.action === 'string' && typeof item.label === 'string' && item.action !== 'estop';
    }).map(function(item) {
      item.icon = item.icon || getVoiceActionIcon(item.action);
      return item;
    });
  } catch (e) {
    return DEFAULT_VOICE_MAPPINGS.slice();
  }
}

function persistVoiceMappings() {
  try {
    localStorage.setItem(VOICE_MAPPING_STORAGE_KEY, JSON.stringify(state.voiceMappings));
  } catch (e) {
    // Browser storage can be unavailable in private/webview contexts; UI still works in memory.
  }
}

state.voiceMappings = loadVoiceMappingsFromStorage();
persistVoiceMappings();

function loadSequenceIconsFromStorage() {
  try {
    var raw = localStorage.getItem('dexterSequenceIcons');
    if (!raw) return {};
    var parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return parsed;
  } catch (e) {
    return {};
  }
}

function persistSequenceIcons() {
  try {
    localStorage.setItem('dexterSequenceIcons', JSON.stringify(state.sequenceIcons));
  } catch (e) {
    // Keep icon edits in memory if this browser cannot persist local storage.
  }
}

state.sequenceIcons = loadSequenceIconsFromStorage();

// ─── 로그 ────────────────────────────────────────────────────────
function slog(msg, cls) {
  var log = document.getElementById('s-log');
  if (!log) return;
  var el = document.createElement('div');
  el.className = 's-log-entry ' + (cls || 's-log-info');
  el.textContent = '[' + new Date().toTimeString().slice(0,8) + '] ' + msg;
  log.insertBefore(el, log.firstChild);
  if (log.children.length > 60) log.removeChild(log.lastChild);
}

function normalizeJointTickLimits(limits) {
  var tickLimits = {};
  if (limits && limits.joint_tick_limits) {
    allJointIds().forEach(function(j) {
      var raw = limits.joint_tick_limits[j] || limits.joint_tick_limits[String(j)];
      if (Array.isArray(raw) && raw.length === 2) {
        tickLimits[j] = [parseInt(raw[0], 10), parseInt(raw[1], 10)];
      }
    });
  }
  if (!tickLimits[15] && limits && limits['15_min'] !== undefined && limits['15_max'] !== undefined) {
    tickLimits[15] = [parseInt(limits['15_min'], 10), parseInt(limits['15_max'], 10)];
  }
  return tickLimits;
}

function getJointTickLimit(jointId) {
  return state.jointTickLimits[jointId] || null;
}

function formatTickRange(range) {
  return range ? '(' + range[0] + ' ~ ' + range[1] + ')' : '';
}

function renderRobotJointUi() {
  var panel = document.getElementById('s-jog-panel');
  var header = panel ? panel.querySelector('.s-jog-row-header') : null;
  var microPanel = panel ? panel.querySelector('.s-micro-move-panel') : null;
  if (panel && header && microPanel) {
    var node = header.nextElementSibling;
    while (node && node !== microPanel) {
      var next = node.nextElementSibling;
      if (node.classList && node.classList.contains('s-jog-row')) node.remove();
      node = next;
    }
    allJointIds().forEach(function(jointId) {
      var meta = jointMeta(jointId);
      var label = jointLabel(jointId);
      var range = getJointTickLimit(jointId);
      var presets = uiJogPresets(jointId);
      var defaultValue = meta.default_ticks !== undefined ? meta.default_ticks : (isMyCobotUi() ? 0 : 2048);
      var excluded = isExcludedJoint(jointId);
      var row = document.createElement('div');
      row.className = 's-jog-row';
      if (excluded) row.style.opacity = '0.55';
      row.innerHTML =
        '<div style="display:flex; flex-direction:column;">' +
          '<span class="s-jog-joint-name" id="lbl-j' + jointId + '-name">' + escapeHtml(label + (excluded ? (lang === 'ko' ? ' · 현재 장비 제외' : ' · excluded on this device') : '')) + '</span>' +
          '<span id="jog-range-' + jointId + '" style="font-size:0.7rem; color:#64748b;">' + escapeHtml((isMyCobotUi() ? formatUiRange(jointId, range) : formatTickRange(range)) || '(0 ~ 4095)') + '</span>' +
        '</div>' +
        '<span class="s-jog-val" id="jog-val-' + jointId + '">' + escapeHtml(formatUiValue(jointId, defaultValue)) + '</span>' +
        '<div style="display:flex; gap:4px; align-items:center;">' +
          '<input type="number" id="jog-direct-' + jointId + '" ' + (excluded ? 'disabled ' : '') + 'step="' + (isMyCobotUi() && !isGripperJoint(jointId) ? '0.01' : '1') + '" placeholder="' + escapeHtml(t().placeholderValue || '수치') + '" style="width:60px; padding:4px; border-radius:4px; border:1px solid #475569; background:#0f172a; color:#fff; font-size:0.8rem;" />' +
          '<button class="s-btn" id="btn-move-' + jointId + '" ' + (excluded ? 'disabled ' : '') + 'onclick="moveJointTo(' + jointId + ')" style="padding:4px 8px; font-size:0.75rem; background:#3b82f6; border-color:#2563eb; color:#fff; border-radius:4px;">' + escapeHtml(t().btnMove) + '</button>' +
        '</div>' +
        '<div class="s-jog-btns">' +
          '<button class="s-btn s-btn-jog" ' + (excluded ? 'disabled ' : '') + 'onclick="jogJoint(' + jointId + ', ' + uiDeltaToRaw(jointId, presets[0]) + ')">' + presets[0] + '</button>' +
          '<button class="s-btn s-btn-jog" ' + (excluded ? 'disabled ' : '') + 'onclick="jogJoint(' + jointId + ', ' + uiDeltaToRaw(jointId, presets[1]) + ')">' + presets[1] + '</button>' +
          '<button class="s-btn s-btn-jog" ' + (excluded ? 'disabled ' : '') + 'onclick="jogJoint(' + jointId + ', ' + uiDeltaToRaw(jointId, presets[2]) + ')">+' + presets[2] + '</button>' +
          '<button class="s-btn s-btn-jog" ' + (excluded ? 'disabled ' : '') + 'onclick="jogJoint(' + jointId + ', ' + uiDeltaToRaw(jointId, presets[3]) + ')">+' + presets[3] + '</button>' +
        '</div>';
      panel.insertBefore(row, microPanel);
    });
  }

  var picker = document.getElementById('save-joints-picker');
  if (picker) {
    picker.innerHTML = '';
    allJointIds().forEach(function(jointId) {
      var label = document.createElement('label');
      label.style.cssText = 'display:flex; align-items:center; gap:5px; font-size:0.8rem; color:#f1f5f9; cursor:pointer;';
      label.innerHTML = '<input type="checkbox" id="chk-save-j' + jointId + '" checked /> ' + escapeHtml(jointLabel(jointId).replace(':', ''));
      picker.appendChild(label);
    });
  }

  var editor = document.getElementById('save-ticks-editor');
  if (editor) {
    editor.innerHTML = '';
    allJointIds().forEach(function(jointId) {
      var item = document.createElement('div');
      if (state.gripperJointId === jointId && allJointIds().length % 2 === 1) item.style.gridColumn = 'span 2';
      item.innerHTML =
        '<span style="font-size:0.75rem; color:#94a3b8; display:block; margin-bottom:4px;">' + escapeHtml(jointLabel(jointId)) + (isMyCobotUi() ? (isGripperJoint(jointId) ? ' (%):' : ' (°):') : (lang === 'ko' ? ' 목표값:' : ' Ticks:')) + '</span>' +
        '<input type="number" id="save-tick-' + jointId + '" style="width:100%; padding:6px; border-radius:4px; border:1px solid #475569; background:#1e293b; color:#fff; font-size:0.8rem;" />';
      editor.appendChild(item);
    });
  }
  populateMicroMoveJointSelect();
  applyJointLimitUi();
  renderAdminJointInputs();
}

function appendAdminSpan(grid, text, id, style) {
  var span = document.createElement('span');
  if (id) span.id = id;
  span.className = 's-admin-label';
  span.textContent = text;
  span.style.cssText = style || 'font-size:0.8rem; color:#f1f5f9;';
  grid.appendChild(span);
  return span;
}

function appendAdminInput(grid, id, attrs) {
  var input = document.createElement('input');
  input.type = 'number';
  input.id = id;
  input.className = 's-admin-input';
  Object.keys(attrs || {}).forEach(function(k) { input.setAttribute(k, attrs[k]); });
  input.style.cssText = 'padding:4px; font-size:0.8rem; text-align:center; background:#1e293b; color:#fff; border:1px solid #475569; border-radius:4px; width:80px;';
  grid.appendChild(input);
  return input;
}

function renderAdminJointInputs() {
  var d = t();
  var rangeGrid = document.getElementById('admin-range-grid');
  if (rangeGrid) {
    rangeGrid.innerHTML = '';
    appendAdminSpan(rangeGrid, d.lblAdminColItem, 'lbl-admin-col-item', 'font-size:0.8rem; font-weight:700; color:#cbd5e1;');
    appendAdminSpan(rangeGrid, d.lblAdminColMin, 'lbl-admin-col-min', 'font-size:0.75rem; color:#94a3b8; text-align:center;');
    appendAdminSpan(rangeGrid, d.lblAdminColMax, 'lbl-admin-col-max', 'font-size:0.75rem; color:#94a3b8; text-align:center;');
    armJointIds().forEach(function(jointId) {
      appendAdminSpan(rangeGrid, jointLabel(jointId) + (lang === 'ko' ? ' 각도 (도)' : ' angle (deg)'), 'lbl-admin-j' + jointId);
      appendAdminInput(rangeGrid, 'admin-lim-' + jointId + '-min', { step: 'any' });
      appendAdminInput(rangeGrid, 'admin-lim-' + jointId + '-max', { step: 'any' });
    });
    if (state.gripperJointId != null) {
      appendAdminSpan(rangeGrid, jointLabel(state.gripperJointId) + (lang === 'ko' ? ' 범위 (틱)' : ' range (ticks)'), 'lbl-admin-j' + state.gripperJointId);
      appendAdminInput(rangeGrid, 'admin-lim-' + state.gripperJointId + '-min', {});
      appendAdminInput(rangeGrid, 'admin-lim-' + state.gripperJointId + '-max', {});
    }
  }

  var tempGrid = document.getElementById('admin-temp-grid');
  if (tempGrid) {
    tempGrid.innerHTML = '';
    allJointIds().forEach(function(jointId) {
      appendAdminSpan(tempGrid, jointLabel(jointId));
      appendAdminInput(tempGrid, 'admin-temp-' + jointId, { step: 'any' });
    });
  }

  var velGrid = document.getElementById('admin-vel-grid');
  if (velGrid) {
    velGrid.innerHTML = '';
    allJointIds().forEach(function(jointId) {
      appendAdminSpan(velGrid, jointLabel(jointId));
      appendAdminInput(velGrid, 'admin-vel-' + jointId, { step: '1', min: '1', max: '200' });
    });
  }
}

function applyJointLimitUi() {
  allJointIds().forEach(function(j) {
    var range = getJointTickLimit(j);
    if (!range) return;
    var label = document.getElementById('jog-range-' + j);
    if (label) label.textContent = isMyCobotUi() ? formatUiRange(j, range) : formatTickRange(range);
    var direct = document.getElementById('jog-direct-' + j);
    if (direct) {
      direct.min = isMyCobotUi() ? rawToUiValue(j, range[0]) : range[0];
      direct.max = isMyCobotUi() ? rawToUiValue(j, range[1]) : range[1];
      direct.title = 'Allowed: ' + (isMyCobotUi() ? formatUiRange(j, range) : range[0] + ' ~ ' + range[1]);
    }
    var saveInput = document.getElementById('save-tick-' + j);
    if (saveInput) {
      saveInput.min = isMyCobotUi() ? rawToUiValue(j, range[0]) : range[0];
      saveInput.max = isMyCobotUi() ? rawToUiValue(j, range[1]) : range[1];
      saveInput.title = 'Allowed: ' + (isMyCobotUi() ? formatUiRange(j, range) : range[0] + ' ~ ' + range[1]);
    }
  });
}

function tickRangeFromDegreeInputs(jointId) {
  var minEl = document.getElementById('admin-lim-' + jointId + '-min');
  var maxEl = document.getElementById('admin-lim-' + jointId + '-max');
  if (!minEl || !maxEl) return null;
  var minDeg = parseFloat(minEl.value);
  var maxDeg = parseFloat(maxEl.value);
  if (isNaN(minDeg) || isNaN(maxDeg)) return null;
  if (isMyCobotUi()) return [Math.round(minDeg * 1000), Math.round(maxDeg * 1000)];
  var lo = 2048 + Math.floor(minDeg * (4096.0 / 360.0));
  var hi = 2048 + Math.ceil(maxDeg * (4096.0 / 360.0));
  if (lo > hi) {
    var tmp = lo;
    lo = hi;
    hi = tmp;
  }
  lo = Math.max(0, Math.min(4095, lo));
  hi = Math.max(0, Math.min(4095, hi));
  return [lo, hi];
}

function updateAdminRangeLabelsWithTicks() {
  var d = t();
  armJointIds().forEach(function(j) {
    var label = document.getElementById('lbl-admin-j' + j);
    if (!label) return;
    var range = tickRangeFromDegreeInputs(j) || getJointTickLimit(j);
    label.textContent = jointLabel(j) + (lang === 'ko' ? ' 각도 (도)' : ' angle (deg)') + (range && !isMyCobotUi() ? ' / ticks ' + range[0] + '~' + range[1] : '');
  });
  if (state.gripperJointId != null) {
    var labelGrip = document.getElementById('lbl-admin-j' + state.gripperJointId);
    var rangeGrip = getJointTickLimit(state.gripperJointId);
    if (labelGrip) labelGrip.textContent = jointLabel(state.gripperJointId) + (lang === 'ko' ? ' 범위 (틱)' : ' range (ticks)') + (rangeGrip ? ' / ticks ' + rangeGrip[0] + '~' + rangeGrip[1] : '');
  }
}

function loadSafetyLimitsForUi() {
  return fetch(BACKEND + '/api/safety-limits?robot_model=' + encodeURIComponent(getRobotModel()))
    .then(function(r) { return r.json(); })
    .then(function(limits) {
      state.safetyLimits = limits;
      state.jointTickLimits = normalizeJointTickLimits(limits);
      // Safety limits are currently OMX-specific.  Never overwrite a selected
      // myCobot 6-axis descriptor with the legacy 4-axis OMX descriptor.
      if (!isMyCobotUi() && limits.robot_joints) applyRobotJoints(limits.robot_joints);
      if (isMyCobotUi()) {
        return loadRobotJoints().then(function() { return limits; });
      }
      applyJointLimitUi();
      updateAdminRangeLabelsWithTicks();
      return limits;
    })
    .catch(function() {
      slog(lang === 'ko' ? '안전 범위 설정을 불러오지 못했습니다.' : 'Failed to load safety limits.', 's-log-err');
      return null;
    });
}

function installSafetyLimitPreviewHandlers() {
  armJointIds().forEach(function(j) {
    ['min', 'max'].forEach(function(side) {
      var el = document.getElementById('admin-lim-' + j + '-' + side);
      if (el) el.addEventListener('input', updateAdminRangeLabelsWithTicks);
    });
  });
  if (state.gripperJointId == null) return;
  ['min', 'max'].forEach(function(side) {
    var gid = state.gripperJointId;
    var el = document.getElementById('admin-lim-' + gid + '-' + side);
    if (el) {
      el.addEventListener('input', function() {
        var lo = parseInt(document.getElementById('admin-lim-' + gid + '-min').value, 10);
        var hi = parseInt(document.getElementById('admin-lim-' + gid + '-max').value, 10);
        if (!isNaN(lo) && !isNaN(hi)) state.jointTickLimits[gid] = [lo, hi];
        updateAdminRangeLabelsWithTicks();
      });
    }
  });
}

// ─── i18n 적용 ───────────────────────────────────────────────────
function applyI18n() {
  var d = t();
  document.documentElement.lang = lang;
  setText('s-title', d.title);
  setText('s-subtitle', d.subtitle);
  setText('btn-settings-menu', d.settingsMenu);
  setText('lbl-settings-theme', d.settingsTheme);
  setText('lbl-settings-width', d.settingsWidth);
  setText('lbl-settings-robot', d.settingsRobot);
  setText('lbl-settings-device', d.settingsDevice);
  setText('btn-lang', d.langBtn);
  setText('btn-server-restart-help', d.serverRestartHelp);
  setText('m-item-home-text', d.selfCheckHome);
  setText('btn-restamp', d.restampTitle);
  setTitle('btn-restamp', d.restampTip);
  setText('restamp-title', d.restampTitle);
  setText('restamp-subtitle', d.restampSubtitle);
  setText('btn-restamp-close', d.selfCheckClose);
  setTitle('btn-self-check', d.selfCheckTip);
  setText('check-modal-title', d.selfCheckTitle);
  setText('check-modal-subtitle', d.selfCheckSubtitle);
  setText('btn-check-close', d.selfCheckClose);
  setText('btn-expert', d.expertMode);
  setText('lbl-step1', d.step1);
  setText('lbl-step2', d.step2);
  setText('lbl-step3', d.step3);
  setText('lbl-repeat-hint', d.repeatHint);
  setText('lbl-count', d.labelCount);
  setText('lbl-times', d.labelTimes);
  setText('lbl-work', d.labelWork);
  setText('lbl-rest', d.labelRest);
  setText('lbl-min1', d.labelMin);
  setText('lbl-min2', d.labelMin);
  setText('btn-clear-queue', d.clearQueue);
  setText('btn-preview', d.preview);
  setText('btn-execute', state.running ? d.execRunning : d.execBtn);
  setText('btn-repeat-toggle', document.getElementById('s-repeat-panel').style.display === 'none' ? d.repeatToggleOpen : d.repeatToggleClose);
  setText('modal-title', d.modalTitle);
  setText('modal-subtitle', d.modalSubtitle);
  setText('m-item1', d.mItem1);
  setText('m-item2', d.mItem2);
  setText('m-item3', d.mItem3);
  setText('m-item4', d.mItem4);
  setText('m-item5', d.mItem5);
  setText('btn-modal-cancel', d.modalCancel);
  setText('btn-modal-confirm', d.modalConfirm);
  setText('lbl-track-title', d.trackTitle);
  setText('lbl-track-follow', d.trackFollow);
  setText('lbl-track-follow-desc', d.trackFollowDesc);
  setText('btn-track-start', d.trackStart);
  setText('btn-track-stop', d.trackStop);
  setText('btn-track-clear', d.trackClear);
  document.getElementById('s-warn-banner').textContent = d.warn;
  
  // Custom added elements translation
  setText('btn-save-sequence', d.saveSequence);
  setText('btn-load-sequence', d.loadSequence);
  setText('lbl-jog-title', d.jogTitle);
  setText('lbl-jog-hint', d.jogHint);
  setText('btn-admin-limits', d.adminLimits);
  setText('lbl-total-hours', d.totalHours);
  setText('lbl-hours', d.hours);
  
  // Tabs & Steps translation
  setText('tab-movements', d.tabMovements);
  setText('tab-targets', d.tabTargets);
  setText('lbl-no-targets', d.noTargets);

  var gridEl = document.getElementById('s-card-grid');
  if (gridEl && state.catalog.length === 0) {
    gridEl.textContent = lang === 'ko' ? '동작 목록 불러오는 중...' : 'Loading movements...';
  }

  // Step 4 manual jog pendant
  // 미세 이동 전용 모드 — 제목·설명·항목 이름에 id가 없어 번역이 닿지 못했다.
  // 부재 모드 · SLLM 도우미 — hangeul_robot에서 새로 만든 화면이라 번역이 없었다.
  setText('s-away-group-title', d.awayGroupTitle);
  setTitle('btn-assign', d.assignBtnTitle);
  setTitle('btn-away-mode', d.awayBtnTitle);
  setText('lbl-sllm-settings', d.sllmSettingsSummary);
  var nameKrInput = document.getElementById('save-name-kr');
  if (nameKrInput) nameKrInput.placeholder = d.saveNameKrPlaceholder;
  var seqIconInput = document.getElementById('edit-seq-icon');
  if (seqIconInput) seqIconInput.placeholder = d.seqIconPlaceholder;
  setText('btn-sllm-helper', d.sllmHelperBtn);
  setTitle('btn-sllm-helper', d.sllmHelperTitle);
  setText('modal-sllm-subtitle', d.sllmSubtitle);
  setText('lbl-sllm-target', d.sllmTargetLabel);
  setText('sllm-runtime-badge', d.sllmRuntimeBadge);
  setText('btn-sllm-search', d.sllmSearchBtn);
  setText('lbl-sllm-enabled', d.sllmEnabledLabel);
  setText('lbl-sllm-seq', d.sllmSeqLabel);
  setText('lbl-sllm-min', d.sllmMinLabel);
  setText('lbl-sllm-max', d.sllmMaxLabel);
  setText('btn-sllm-save-settings', d.sllmSaveBtn);
  setText('btn-sllm-close', d.sllmCloseBtn);
  var sllmQ = document.getElementById('sllm-query');
  if (sllmQ) sllmQ.placeholder = d.sllmQueryPlaceholder;
  setText('lbl-micro-title', d.lblMicroTitle);
  setText('lbl-micro-desc', d.lblMicroDesc);
  setText('lbl-micro-joint', d.lblMicroJoint);
  setText('lbl-micro-delta', d.lblMicroDelta);
  setText('lbl-micro-repeat', d.lblMicroRepeat);
  setText('btn-micro-move-run', d.btnMicroRun);
  setText('lbl-jog-header-joint', d.lblJogHeaderJoint);
  setText('lbl-jog-header-value', d.lblJogHeaderValue);
  setText('lbl-jog-header-direct', d.lblJogHeaderDirect);
  setText('lbl-jog-header-jog', d.lblJogHeaderJog);
  setText('btn-read-pose', d.btnReadPose);
  setText('btn-save-pose-modal', d.btnSavePose);

  renderRobotJointUi();
  installSafetyLimitPreviewHandlers();

  // Move buttons for configured joints
  allJointIds().forEach(function(jointNum) {
    setText('btn-move-' + jointNum, d.btnMove);
    var directInput = document.getElementById('jog-direct-' + jointNum);
    if (directInput) {
      directInput.placeholder = d.placeholderValue;
    }
  });

  // Step 4 Save Pose Modal labels
  setText('lbl-save-name-kr', d.lblSaveNameKr);
  setText('lbl-save-name-en', d.lblSaveNameEn);
  setText('lbl-save-desc-kr', d.lblSaveDescKr);
  setText('lbl-save-desc-en', d.lblSaveDescEn);
  setSaveLanguageFields();
  setText('lbl-save-icon', d.lblSaveIcon);
  var saveIconInput = document.getElementById('save-icon');
  if (saveIconInput) {
    saveIconInput.placeholder = d.saveIconPlaceholder;
  }
  setText('lbl-save-tip', d.lblSaveTip);
  setText('lbl-save-delay', d.lblSaveDelay);
  setText('lbl-save-joints-title', d.lblSaveJointsTitle);
  setText('lbl-save-ticks-title', d.lblSaveTicksTitle);
  setText('btn-save-pose-cancel', d.btnSavePoseCancel);
  setText('btn-save-pose-submit', d.btnSavePoseSubmit);
  setText('btn-edit-delete', d.btnEditDelete);
  setText('btn-save-icon-file', d.btnFileSelect);
  setText('btn-edit-seq-icon-file', d.btnFileSelect);

  // Step 2 Saved Sequence Modals
  setText('modal-save-seq-title', d.modalSaveSeqTitle);
  setText('modal-save-seq-subtitle', d.modalSaveSeqSubtitle);
  setText('lbl-seq-save-name', d.lblSeqSaveName);
  var seqSaveInput = document.getElementById('seq-save-name');
  if (seqSaveInput) {
    seqSaveInput.placeholder = d.seqSaveNamePlaceholder;
  }
  setText('btn-save-seq-cancel', d.btnSaveSeqCancel);
  setText('btn-save-seq-confirm', d.btnSaveSeqConfirm);
  setText('modal-load-seq-title', d.modalLoadSeqTitle);
  setText('modal-load-seq-subtitle', d.modalLoadSeqSubtitle);
  setText('btn-load-seq-close', d.btnLoadSeqClose);

  // Step 5 Admin limits modal
  setText('modal-admin-title', d.modalAdminTitle);
  setText('modal-admin-subtitle', d.modalAdminSubtitle);
  setText('lbl-admin-col-item', d.lblAdminColItem);
  setText('lbl-admin-col-min', d.lblAdminColMin);
  setText('lbl-admin-col-max', d.lblAdminColMax);
  // 관절 이름은 콘솔이 준 것을 쓴다(renderAdminJointInputs). 여기서 고정 문구로
  // 덮어쓰면 'J11 Base 각도' 같은 옛 이름이 되살아난다 — 실제로 그랬다.
  renderAdminJointInputs();
  setText('btn-admin-close', d.btnAdminClose);
  setText('btn-admin-submit', d.btnAdminSubmit);
  setText('lbl-admin-temp-title', d.lblAdminTempTitle);
  setText('lbl-admin-temp-all', d.lblAdminTempAll);
  setText('btn-admin-temp-apply-all', d.btnAdminTempApplyAll);
  setText('lbl-admin-vel-title', d.lblAdminVelTitle);
  setText('lbl-admin-vel-all', d.lblAdminVelAll);
  setText('btn-admin-vel-apply-all', d.btnAdminVelApplyAll);
  setText('lbl-admin-vel-hint', d.lblAdminVelHint);
  setText('lbl-admin-profile-title', d.lblAdminProfileTitle);
  setText('lbl-admin-profile-desc', d.lblAdminProfileDesc);
  setText('opt-profile-safe', d.optProfileSafe);
  setText('opt-profile-smooth', d.optProfileSmooth);
  setText('opt-profile-fast', d.optProfileFast);
  setText('opt-profile-custom', d.optProfileCustom);
  setText('lbl-admin-custom-stage', d.lblAdminCustomStage);
  setText('lbl-admin-custom-accel', d.lblAdminCustomAccel);
  setText('lbl-admin-custom-hint', d.lblAdminCustomHint);
  setText('lbl-person-camera-enabled', d.lblPersonCameraEnabled);
  setText('lbl-person-camera-enabled-desc', d.lblPersonCameraEnabledDesc);
  setText('lbl-admin-person-title', d.lblAdminPersonTitle);
  setText('lbl-person-policy-zone', d.lblPersonPolicyZone);
  setText('lbl-person-policy-zone-desc', d.lblPersonPolicyZoneDesc);
  setText('lbl-person-policy-full', d.lblPersonPolicyFull);
  setText('lbl-person-policy-full-desc', d.lblPersonPolicyFullDesc);
  setText('lbl-person-policy-warn', d.lblPersonPolicyWarn);
  setText('lbl-person-policy-warn-desc', d.lblPersonPolicyWarnDesc);
  setText('lbl-admin-zone-title', d.lblAdminZoneTitle);
  setText('lbl-admin-zone-hint', d.lblAdminZoneHint);
  setSecurityButtonText(d.btnSecMonitoring);
  setText('modal-sec-title', d.modalSecTitle);
  setText('modal-sec-subtitle', d.modalSecSubtitle);
  setText('lbl-sec-status-label', d.lblSecStatusLabel);
  setText('lbl-sec-detail-title', d.lblSecDetailTitle);
  setText('btn-sec-close', d.btnSecClose);
  setText('btn-sec-resolve', d.btnSecResolve);
  
  setText('lbl-ai-title', d.aiTitle);
  setText('lbl-voice-title', d.voiceTitle);
  setText('lbl-voice-preset', d.voicePreset);
  setText('lbl-voice-direct', d.voiceDirect);
  
  var voiceInput = document.getElementById('s-voice-input');
  if (voiceInput) {
    voiceInput.placeholder = d.voiceInputPlaceholder;
  }
  
  setText('btn-voice-send', d.voiceSend);
  
  var recBtn = document.getElementById('btn-voice-record');
  var browserRecording = !!_recognition;
  if (recBtn) {
    recBtn.innerHTML = browserRecording ? d.voiceRecordActive : d.voiceRecord;
  }
  updateTopVoiceCommandBtn(!!state.serverVoiceTimer);

  setText('lbl-voice-grid-title', d.voiceGridTitle);
  setText('lbl-mapped-title', d.voiceMappedTitle);
  setText('lbl-mapped-phrase-prefix', d.voiceMappedPhrasePrefix);
  setText('lbl-mapped-action-label', d.voiceMappedActionLabel);
  setText('btn-save-mapping', d.voiceSaveMapping);
  
  // Voice feedback placeholder translation
  var voiceFeedbackEl = document.getElementById('s-voice-feedback');
  if (voiceFeedbackEl) {
    var fbText = voiceFeedbackEl.textContent.trim();
    if (fbText.indexOf('음성 명령을') !== -1 || fbText.indexOf('classification result will appear') !== -1 || fbText === '') {
      voiceFeedbackEl.textContent = d.voiceFeedbackDefault;
    }
  }

  setText('btn-tab-range', d.tabRange);
  setText('btn-tab-temp', d.tabTemp);
  setText('btn-tab-vel', d.tabVel);
  setText('btn-tab-person', d.tabPerson);
  
  setText('lbl-vision-title', d.visionTitle);
  
  // Vision capture panel
  setText('lbl-vision-scenario', d.lblVisionScenario);
  var visionCaptureInput = document.getElementById('s-vision-capture-label');
  if (visionCaptureInput) {
    visionCaptureInput.placeholder = d.visionCaptureLabelPlaceholder;
  }
  setText('btn-vision-start', d.btnVisionStart);
  setText('btn-vision-capture', d.btnVisionCapture);
  setText('btn-vision-stop', d.btnVisionStop);
  
  var visionPlaceholder = document.getElementById('s-camera-placeholder');
  if (visionPlaceholder && visionPlaceholder.style.display !== 'none') {
    visionPlaceholder.textContent = d.visionPlaceholder;
  }
  
  // Radio button text updates
  var optCountEl = document.getElementById('lbl-opt-count');
  if (optCountEl) {
    var r1 = optCountEl.querySelector('input');
    optCountEl.textContent = '';
    if (r1) optCountEl.appendChild(r1);
    optCountEl.appendChild(document.createTextNode(' ' + d.optCount));
  }
  
  var optTimeEl = document.getElementById('lbl-opt-time');
  if (optTimeEl) {
    var r2 = optTimeEl.querySelector('input');
    optTimeEl.textContent = '';
    if (r2) optTimeEl.appendChild(r2);
    optTimeEl.appendChild(document.createTextNode(' ' + d.optTime));
  }
  
  // E-Stop button text translation
  var estopBtn = document.getElementById('btn-estop');
  if (estopBtn) {
    estopBtn.textContent = state.estopActive ? d.estopReset : d.estop;
  }
  
  // Translate voice surveillance status text
  var voiceStatusText = document.getElementById('s-voice-status-text');
  if (voiceStatusText) {
    voiceStatusText.textContent = state.serverVoiceTimer
      ? (lang === 'ko' ? '음성 정지 대기' : 'Voice stop armed')
      : (lang === 'ko' ? '음성 대기' : 'Voice idle');
  }
  updateLlmVoiceModeStatus();
  
  updateQueueEmpty();
  populateActionSelect();
  updateExecuteBtn();
  renderVoiceMappings();
  updateAdminRangeLabelsWithTicks();
  refreshAwayModeButton();
}

function setText(id, val) {
  var el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setTitle(id, val) {
  var el = document.getElementById(id);
  if (el) el.title = val;
}

function setSaveLanguageFields() {
  var showKr = lang === 'ko';
  [
    ['lbl-save-name-kr', showKr],
    ['save-name-kr', showKr],
    ['lbl-save-desc-kr', showKr],
    ['save-desc-kr', showKr],
    ['lbl-save-name-en', !showKr],
    ['save-name-en', !showKr],
    ['lbl-save-desc-en', !showKr],
    ['save-desc-en', !showKr]
  ].forEach(function(pair) {
    var el = document.getElementById(pair[0]);
    if (el) el.style.display = pair[1] ? '' : 'none';
  });
  var nameKr = document.getElementById('save-name-kr');
  var nameEn = document.getElementById('save-name-en');
  var descKr = document.getElementById('save-desc-kr');
  var descEn = document.getElementById('save-desc-en');
  if (nameKr) {
    nameKr.placeholder = '예: 바닥 물건 집기 자세';
    nameKr.required = showKr;
  }
  if (descKr) {
    descKr.placeholder = '동작에 대한 간단한 설명';
    descKr.required = false;
  }
  if (nameEn) {
    nameEn.placeholder = 'e.g., Grasp Floor Object Pose';
    nameEn.required = !showKr;
  }
  if (descEn) {
    descEn.placeholder = 'Short movement description';
    descEn.required = false;
  }
}

function setSecurityButtonText(label) {
  var btn = document.getElementById('btn-sec-monitoring');
  if (!btn) return;
  var dot = document.getElementById('sec-alert-dot');
  var prevText = dot ? dot.textContent : '';
  var prevDisplay = dot ? dot.style.display : 'none';
  btn.textContent = label;
  if (!dot) {
    dot = document.createElement('span');
    dot.id = 'sec-alert-dot';
    dot.className = 's-sec-alert-badge';
    dot.style.display = 'none';
  }
  dot.textContent = prevText;
  dot.style.display = prevDisplay;
  btn.appendChild(dot);
}

function toggleSettingsMenu() {
  var panel = document.getElementById('s-settings-panel');
  var btn = document.getElementById('btn-settings-menu');
  if (!panel) return;
  var open = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : 'block';
  if (btn) btn.setAttribute('aria-expanded', open ? 'false' : 'true');
}

function updateLlmVoiceModeStatus() {
  // Voice learning UI is intentionally removed. Keep this as a no-op for older
  // code paths that still stop voice listeners defensively.
}

document.addEventListener('click', function(ev) {
  var panel = document.getElementById('s-settings-panel');
  var menu = document.querySelector('.s-settings-menu');
  var btn = document.getElementById('btn-settings-menu');
  if (!panel || !menu || panel.style.display === 'none') return;
  if (!menu.contains(ev.target)) {
    panel.style.display = 'none';
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }
});

function getUiTheme() {
  var theme = localStorage.getItem(UI_THEME_STORAGE_KEY);
  if (theme === 'llm-dark' && localStorage.getItem(UI_THEME_MIGRATION_STORAGE_KEY) !== 'done') {
    theme = 'light';
    localStorage.setItem(UI_THEME_STORAGE_KEY, theme);
    localStorage.setItem(UI_THEME_MIGRATION_STORAGE_KEY, 'done');
  }
  if (theme === 'sbux') theme = 'light';
  theme = theme || 'light';
  return ['light', 'orange', 'aqua', 'llm-dark', 'industrial', 'graphite'].indexOf(theme) >= 0 ? theme : 'light';
}

function getUiWidth() {
  var width = localStorage.getItem(UI_WIDTH_STORAGE_KEY) || '1120';
  return ['880', '1120', '1280'].indexOf(width) >= 0 ? width : '1120';
}

function applyUiPreferences() {
  var theme = getUiTheme();
  var width = getUiWidth();
  document.body.classList.remove('theme-light', 'theme-orange', 'theme-aqua', 'theme-sbux', 'theme-llm-dark', 'theme-industrial', 'theme-graphite');
  document.body.classList.add('theme-' + theme);
  document.body.style.setProperty('--dexter-main-width', width + 'px');
  var themeSelect = document.getElementById('ui-theme-select');
  var widthSelect = document.getElementById('ui-width-select');
  var robotSelect = document.getElementById('robot-model-select');
  var deviceSelect = document.getElementById('robot-device-select');
  if (themeSelect) themeSelect.value = theme;
  if (widthSelect) widthSelect.value = width;
  if (robotSelect) robotSelect.value = getRobotModel();
  if (deviceSelect) deviceSelect.value = getRobotDevice();
}

function getRobotModel() {
  var value = localStorage.getItem(ROBOT_MODEL_STORAGE_KEY) || 'mock';
  return ['mock', 'openmanipulator_x', 'mycobot_280_m5'].indexOf(value) >= 0 ? value : 'mock';
}

function getRobotDevice() {
  // 자유 입력 필드(COM3/COM6 같은 Windows 네이티브 포트 포함) — 과거 <select>였을 때
  // 고정 두 값만 허용하던 화이트리스트를 제거했다. 로봇 모델별로 별도 저장하며,
  // 값이 없을 때만 그 모델의 기본값을 쓴다.
  var model = getRobotModel();
  var value = localStorage.getItem(robotDeviceStorageKey(model));
  if (value && value.trim()) return value.trim();
  return ROBOT_DEVICE_DEFAULTS[model] || '/dev/ttyUSB0';
}

function onRobotModelChange() {
  var robotSelect = document.getElementById('robot-model-select');
  var deviceSelect = document.getElementById('robot-device-select');
  var model = robotSelect ? robotSelect.value : getRobotModel();
  localStorage.setItem(ROBOT_MODEL_STORAGE_KEY, model);
  // 로봇을 바꿀 때는 이전 로봇의 포트값을 그대로 저장하지 않고, 새 로봇 자신의
  // 저장값(또는 기본값)으로 되돌린다 — 이게 없어서 OMX<->mycobot 전환 시 포트가
  // 서로 덮어써지던 버그였다.
  if (deviceSelect) deviceSelect.value = getRobotDevice();
  slog(
    lang === 'ko'
      ? '로봇 선택 저장: ' + model + ' (' + getRobotDevice() + ')'
      : 'Robot selection saved: ' + model + ' (' + getRobotDevice() + ')',
    's-log-info'
  );
  applyUiPreferences();
  // 화면만 바꾸면 콘솔은 여전히 다른 로봇을 잡고 있다 — OMX 화면에서
  // MyCobot 알림이 뜨던 원인. 콘솔의 선택도 같이 바꾼다.
  fetch(BACKEND + '/api/robots/select-by-model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ robot_model: model })
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.success) {
        slog((lang === 'ko' ? '로봇 선택 실패: ' : 'Robot selection failed: ') + (d.error || ''), 's-log-err');
        return;
      }
      // 로봇마다 동작 목록·순서·안전범위·기록이 모두 다르므로 화면을 다시 불러온다.
      window.location.reload();
    })
    .catch(function() {
      loadRobotJoints().then(function() {
        applyJointLimitUi();
        updateAdminRangeLabelsWithTicks();
      });
    });
}
window.onRobotModelChange = onRobotModelChange;

function onRobotDeviceChange() {
  var deviceSelect = document.getElementById('robot-device-select');
  var model = getRobotModel();
  if (deviceSelect) localStorage.setItem(robotDeviceStorageKey(model), deviceSelect.value);
  slog(
    lang === 'ko'
      ? '연결 포트 저장 (' + model + '): ' + getRobotDevice()
      : 'Device saved (' + model + '): ' + getRobotDevice(),
    's-log-info'
  );
}
window.onRobotDeviceChange = onRobotDeviceChange;

function saveUiPreferences() {
  var themeSelect = document.getElementById('ui-theme-select');
  var widthSelect = document.getElementById('ui-width-select');
  if (themeSelect) localStorage.setItem(UI_THEME_STORAGE_KEY, themeSelect.value);
  if (widthSelect) localStorage.setItem(UI_WIDTH_STORAGE_KEY, widthSelect.value);
  applyUiPreferences();
}
window.saveUiPreferences = saveUiPreferences;

// ─── 카탈로그 로드 ───────────────────────────────────────────────
function loadCatalog() {
  fetch(BACKEND + '/api/simple-catalog?robot_model=' + encodeURIComponent(getRobotModel()))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      state.catalog = d.movements || [];
      state.robotCardLabel = d.robot_label || '';
      state.robotCardFamily = d.robot_family || '';
      return loadSavedSequences().then(function() { return d; });
    })
    .then(function(d) {
      renderCards();
      populateActionSelect();
          renderVoiceMappings();
      slog(lang === 'ko'
        ? '동작 목록 로드 완료: ' + state.catalog.length + '개 / 저장 순서 ' + Object.keys(state.savedSequences).length + '개'
        : 'Catalog loaded: ' + state.catalog.length + ' items / ' + Object.keys(state.savedSequences).length + ' saved sequences',
        's-log-ok');
    })
    .catch(function(e) {
      document.getElementById('s-card-grid').textContent = t().loadFail;
      slog(t().loadFail + ': ' + e.message, 's-log-err');
    });
}

function loadSavedSequences() {
  return fetch(BACKEND + '/api/sequences')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      state.savedSequences = data || {};
      return state.savedSequences;
    })
    .catch(function(e) {
      state.savedSequences = {};
      slog((lang === 'ko' ? '저장 순서 로드 실패: ' : 'Failed to load saved sequences: ') + e.message, 's-log-err');
      return state.savedSequences;
    });
}

function renderIconElement(container, iconValue, defaultChar) {
  container.innerHTML = '';
  if (iconValue && (iconValue.indexOf('data:image/') === 0 || iconValue.indexOf('/') === 0 || iconValue.indexOf('http') === 0)) {
    var img = document.createElement('img');
    img.src = iconValue;
    img.style.width = '32px';
    img.style.height = '32px';
    img.style.objectFit = 'contain';
    img.style.display = 'block';
    img.style.margin = '0 auto';
    container.appendChild(img);
  } else {
    container.textContent = iconValue || defaultChar;
  }
}

function shortRobotCardLabel(value) {
  var raw = String(value || '').toLowerCase();
  if (raw.indexOf('mycobot') !== -1 || raw.indexOf('my_cobot') !== -1 || raw === 'm5') return 'M5';
  if (raw.indexOf('omx') !== -1 || raw.indexOf('openmanipulator') !== -1) return 'OMX';
  return String(value || '');
}

function handleIconUpload(input, targetId) {
  var file = input.files[0];
  if (!file) return;
  
  if (file.size > 200 * 1024) {
    alertOrStyled(lang === 'ko' ? '이미지 크기는 최대 200KB 이하여야 합니다.' : 'Image size must be less than 200KB.');
    input.value = '';
    return;
  }
  
  var reader = new FileReader();
  reader.onload = function(e) {
    var dataUrl = e.target.result;
    document.getElementById(targetId).value = dataUrl;
    
    if (targetId === 'save-icon') {
      selectEmoji('');
    } else if (targetId === 'edit-seq-icon') {
      selectSeqEmoji('');
    }
  };
  reader.readAsDataURL(file);
}

// ─── 카드 렌더링 ─────────────────────────────────────────────────
function loadCardOrder() {
  try {
    var raw = localStorage.getItem(CARD_ORDER_STORAGE_KEY);
    var parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (err) {
    return [];
  }
}

function saveCardOrder(order) {
  try {
    localStorage.setItem(CARD_ORDER_STORAGE_KEY, JSON.stringify(order));
  } catch (err) {}
}

function cardOrderIndex(cardKey) {
  var order = loadCardOrder();
  var idx = order.indexOf(cardKey);
  return idx < 0 ? 100000 : idx;
}

function sortCardsBySavedOrder(items, keyFn) {
  return items.slice().sort(function(a, b) {
    var ai = cardOrderIndex(keyFn(a));
    var bi = cardOrderIndex(keyFn(b));
    if (ai !== bi) return ai - bi;
    return 0;
  });
}

function persistCardOrderFromGrid() {
  var grid = document.getElementById('s-card-grid');
  if (!grid) return;
  var order = [];
  grid.querySelectorAll('.s-card[data-card-key]').forEach(function(card) {
    if (card.dataset.fixedCard === 'true') return;
    order.push(card.dataset.cardKey);
  });
  saveCardOrder(order);
}

function getDragAfterCard(container, x, y) {
  var cards = Array.prototype.slice.call(container.querySelectorAll('.s-card[draggable="true"]:not(.s-card-dragging)'));
  for (var i = 0; i < cards.length; i++) {
    var child = cards[i];
    var box = child.getBoundingClientRect();
    // The card panel is a wrapping CSS grid.  Comparing only Y made a
    // horizontal drag land in a different row/side.  Use the card's visual
    // row and horizontal midpoint so DOM insertion follows what the pointer
    // visibly crosses, one card slot at a time.
    var sameRow = y >= box.top && y <= box.bottom;
    if ((sameRow && x < box.left + box.width / 2) ||
        (!sameRow && y < box.top - Math.max(4, box.height * 0.25))) {
      return child;
    }
  }
  return null;
}

function enableCardDrag(card, cardKey) {
  card.draggable = true;
  card.dataset.cardKey = cardKey;
  card.title = lang === 'ko' ? '드래그해서 카드 순서를 바꿀 수 있습니다.' : 'Drag to reorder this card.';
  card.addEventListener('dragstart', function(e) {
    state.cardDragActive = true;
    card.classList.add('s-card-dragging');
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', cardKey);
    }
  });
  card.addEventListener('dragend', function() {
    card.classList.remove('s-card-dragging');
    persistCardOrderFromGrid();
    setTimeout(function() { state.cardDragActive = false; }, 150);
  });
}

function enableCardGridDrop(grid) {
  if (grid.dataset.dragDropBound === 'true') return;
  grid.dataset.dragDropBound = 'true';
  grid.addEventListener('dragover', function(e) {
    e.preventDefault();
    var dragging = grid.querySelector('.s-card-dragging');
    if (!dragging) return;
    var afterCard = getDragAfterCard(grid, e.clientX, e.clientY);
    if (afterCard == null) {
      grid.appendChild(dragging);
    } else {
      grid.insertBefore(dragging, afterCard);
    }
  });
}

function renderMovementCard(grid, mv) {
  var card = document.createElement('div');
  card.className = 's-card';
  enableCardDrag(card, 'movement:' + mv.skill_id);
  card.style.setProperty('--card-color', mv.color || '#0ea5e9');
  card.style.borderColor = 'transparent';

  var movementRobotLabel = shortRobotCardLabel(mv.robot_label || mv.robot_family || mv.robot_model || state.robotCardLabel);
  if (window.DEXTER_HANGEUL_MOCK && movementRobotLabel) {
    var robotBadge = document.createElement('span');
    robotBadge.className = 's-card-robot-badge robot-family-' + (mv.robot_family || mv.robot_model || 'other');
    robotBadge.textContent = movementRobotLabel;
    card.appendChild(robotBadge);
  }

  var badge = document.createElement('span');
  badge.className = 's-card-badge';
  if (mv.verified !== false) {
    badge.textContent = t().verified;
  } else {
    badge.textContent = t().unverified;
    badge.style.background = 'rgba(239, 68, 68, 0.15)';
    badge.style.color = '#f87171';
    badge.style.border = '1px solid rgba(239, 68, 68, 0.4)';
  }
  card.appendChild(badge);

  var icon = document.createElement('div');
  icon.className = 's-card-icon';
  renderIconElement(icon, mv.icon, '▶');
  card.appendChild(icon);

  var name = document.createElement('div');
  name.className = 's-card-name';
  name.textContent = lang === 'ko'
    ? (mv.display_name_kr || mv.display_name_en || mv.skill_id)
    : (mv.display_name_en || mv.display_name_kr || mv.skill_id);
  card.appendChild(name);

  var desc = document.createElement('div');
  desc.className = 's-card-desc';
  desc.textContent = lang === 'ko'
    ? (mv.description_kr || '')
    : (mv.description_en || '');
  card.appendChild(desc);

  var act = document.createElement('span');
  act.className = 's-card-actuator';
  act.textContent = mv.actuator || '';
  card.appendChild(act);

  var fixedMovementCard = mv.skill_id === 'SAFE_BASIC_POSE_RETURN' || mv.fixed === true || mv.deletable === false;
  if (mv.skill_id && !fixedMovementCard) {
    var editBtn = document.createElement('span');
    editBtn.className = 's-card-edit-btn';
    editBtn.textContent = '✎';
    editBtn.title = lang === 'ko' ? '동작 수정/삭제' : 'Edit/delete movement';
    editBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      openEditModal(mv);
    });
    card.appendChild(editBtn);
  }

  card.addEventListener('click', function() {
    if (state.cardDragActive) return;
    addToQueue(mv);
    card.style.borderColor = mv.color || '#0ea5e9';
    setTimeout(function() { card.style.borderColor = 'transparent'; }, 300);
  });

  grid.appendChild(card);
}

function renderSequenceCard(grid, seqName) {
  // 2026-07-21에는 hangeul의 순서 저장이 로봇당 슬롯 1개뿐이라(묶음이 서로
  // 덮어써짐) 카드를 숨겼었다. 2026-07-22 로봇별 sequence_library.json
  // 도입으로 여러 묶음이 정상 공존하므로 hangeul에서도 카드를 보여준다 —
  // 클릭 시 즉시 대기열에 담겨 '저장이 실제로 됐다'는 눈에 보이는 확인이 된다.
  var skillIds = state.savedSequences[seqName] || [];
  var card = document.createElement('div');
  card.className = 's-card s-sequence-card';
  enableCardDrag(card, 'sequence:' + seqName);
  card.style.setProperty('--card-color', '#8b5cf6');
  card.style.borderColor = 'transparent';

  var sequenceRobotLabel = shortRobotCardLabel(state.robotCardLabel || state.robotCardFamily);
  if (window.DEXTER_HANGEUL_MOCK && sequenceRobotLabel) {
    var robotBadge = document.createElement('span');
    robotBadge.className = 's-card-robot-badge robot-family-' + (state.robotCardFamily || 'other');
    robotBadge.textContent = sequenceRobotLabel;
    card.appendChild(robotBadge);
  }

  var badge = document.createElement('span');
  badge.className = 's-card-badge';
  badge.textContent = lang === 'ko' ? '저장 순서' : 'Saved';
  badge.style.background = 'rgba(139, 92, 246, 0.15)';
  badge.style.color = '#c4b5fd';
  card.appendChild(badge);

  var icon = document.createElement('div');
  icon.className = 's-card-icon';
  renderIconElement(icon, state.sequenceIcons[seqName], '📂');
  card.appendChild(icon);

  var editBtn = document.createElement('span');
  editBtn.className = 's-card-edit-btn';
  editBtn.textContent = '✏️';
  editBtn.style = 'position:absolute; bottom:8px; right:8px; font-size:1rem; cursor:pointer; background:#1e293b; border:1px solid #475569; border-radius:4px; padding:2px 4px; z-index:10;';
  editBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    openEditSequenceModal(seqName);
  });
  card.appendChild(editBtn);

  var name = document.createElement('div');
  name.className = 's-card-name';
  name.textContent = seqName;
  card.appendChild(name);

  var desc = document.createElement('div');
  desc.className = 's-card-desc';
  desc.textContent = skillIds.length + (lang === 'ko' ? '개 동작을 대기열에 추가' : ' steps added to queue');
  card.appendChild(desc);

  var act = document.createElement('span');
  act.className = 's-card-actuator';
  act.textContent = lang === 'ko' ? '자주 쓰는 순서' : 'Recipe';
  card.appendChild(act);

  card.addEventListener('click', function() {
    if (state.cardDragActive) return;
    appendSequenceRecipe(seqName, skillIds);
    card.style.borderColor = '#8b5cf6';
    setTimeout(function() { card.style.borderColor = 'transparent'; }, 300);
  });

  grid.appendChild(card);
}

function renderCards() {
  var grid = document.getElementById('s-card-grid');
  grid.textContent = '';
  enableCardGridDrop(grid);
  renderEmergencyStopCard(grid);
  var combined = [];
  Object.keys(state.savedSequences || {}).forEach(function(seqName) {
    combined.push({ type: 'sequence', key: 'sequence:' + seqName, name: seqName });
  });
  state.catalog.forEach(function(mv) {
    combined.push({ type: 'movement', key: 'movement:' + mv.skill_id, movement: mv });
  });
  combined.sort(function(a, b) {
    var ai = cardOrderIndex(a.key);
    var bi = cardOrderIndex(b.key);
    if (ai !== bi) return ai - bi;
    return 0;
  });
  combined.forEach(function(item) {
    if (item.type === 'sequence') {
      renderSequenceCard(grid, item.name);
    } else {
      renderMovementCard(grid, item.movement);
    }
  });
}

function renderEmergencyStopCard(grid) {
  var card = document.createElement('div');
  card.className = 's-card';
  card.dataset.fixedCard = 'true';
  card.style.setProperty('--card-color', '#dc2626');
  card.style.borderColor = 'rgba(248, 113, 113, 0.65)';

  var badge = document.createElement('span');
  badge.className = 's-card-badge';
  badge.textContent = lang === 'ko' ? '안전' : 'Safety';
  card.appendChild(badge);

  var icon = document.createElement('div');
  icon.className = 's-card-icon';
  icon.textContent = '🚨';
  card.appendChild(icon);

  var name = document.createElement('div');
  name.className = 's-card-name';
  name.textContent = lang === 'ko' ? '긴급 정지' : 'Emergency Stop';
  card.appendChild(name);

  var desc = document.createElement('div');
  desc.className = 's-card-desc';
  desc.textContent = lang === 'ko' ? '음성 매칭과 동일한 E-STOP 기능' : 'Same E-STOP action used by voice matching';
  card.appendChild(desc);

  card.addEventListener('click', function() {
    triggerEStop();
    card.style.borderColor = '#fca5a5';
    setTimeout(function() { card.style.borderColor = 'rgba(248, 113, 113, 0.65)'; }, 300);
  });

  grid.appendChild(card);
}

function renderSequenceCards(grid) {
  if (window.DEXTER_HANGEUL_MOCK) return; // Dexter Hangeul: 저장 순서 카드 미표시
  var names = Object.keys(state.savedSequences || {});
  if (names.length === 0) return;

  sortCardsBySavedOrder(names, function(seqName) { return 'sequence:' + seqName; }).forEach(function(seqName) {
    var skillIds = state.savedSequences[seqName] || [];
    var card = document.createElement('div');
    card.className = 's-card s-sequence-card';
    enableCardDrag(card, 'sequence:' + seqName);
    card.style.setProperty('--card-color', '#8b5cf6');
    card.style.borderColor = 'transparent';

    var badge = document.createElement('span');
    badge.className = 's-card-badge';
    badge.textContent = lang === 'ko' ? '저장 순서' : 'Saved';
    badge.style.background = 'rgba(139, 92, 246, 0.15)';
    badge.style.color = '#c4b5fd';
    card.appendChild(badge);

    var icon = document.createElement('div');
    icon.className = 's-card-icon';
    renderIconElement(icon, state.sequenceIcons[seqName], '📂');
    card.appendChild(icon);

    var editBtn = document.createElement('span');
    editBtn.className = 's-card-edit-btn';
    editBtn.textContent = '✏️';
    editBtn.style = 'position:absolute; bottom:8px; right:8px; font-size:1rem; cursor:pointer; background:#1e293b; border:1px solid #475569; border-radius:4px; padding:2px 4px; z-index:10;';
    editBtn.addEventListener('click', function(e) {
      e.stopPropagation(); // prevent adding to queue
      openEditSequenceModal(seqName);
    });
    card.appendChild(editBtn);

    var name = document.createElement('div');
    name.className = 's-card-name';
    name.textContent = seqName;
    card.appendChild(name);

    var desc = document.createElement('div');
    desc.className = 's-card-desc';
    desc.textContent = skillIds.length + (lang === 'ko' ? '개 동작을 대기열에 추가' : ' steps added to queue');
    card.appendChild(desc);

    var act = document.createElement('span');
    act.className = 's-card-actuator';
    act.textContent = lang === 'ko' ? '자주 쓰는 순서' : 'Recipe';
    card.appendChild(act);

    card.addEventListener('click', function() {
      if (state.cardDragActive) return;
      appendSequenceRecipe(seqName, skillIds);
      card.style.borderColor = '#8b5cf6';
      setTimeout(function() { card.style.borderColor = 'transparent'; }, 300);
    });

    grid.appendChild(card);
  });
}

function setSequenceIcon(seqName, icon) {
  state.sequenceIcons[seqName] = icon;
  state.sequenceIconEditName = null;
  persistSequenceIcons();
  renderCards();
  populateActionSelect();
  slog(lang === 'ko' ? '저장 순서 아이콘 수정: ' + seqName + ' ' + icon : 'Saved sequence icon updated: ' + seqName + ' ' + icon, 's-log-ok');
}

function openEditSequenceModal(seqName) {
  var modal = document.getElementById('s-edit-seq-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  
  document.getElementById('edit-seq-original-name').value = seqName;
  document.getElementById('edit-seq-name').value = seqName;
  
  var activeIcon = state.sequenceIcons[seqName] || '📂';
  selectSeqEmoji(activeIcon);
  
  // Translate title/labels based on current language
  document.getElementById('edit-seq-modal-title').textContent = lang === 'ko' ? '✏️ 순서 카드 수정' : '✏️ Edit Sequence';
  document.getElementById('edit-seq-modal-subtitle').textContent = lang === 'ko' ? '이 순서 카드의 이름, 아이콘을 편집하거나 삭제할 수 있습니다.' : 'Edit the name, icon, or delete this saved sequence.';
  document.getElementById('lbl-edit-seq-name').textContent = lang === 'ko' ? '순서 이름 (Sequence Name)' : 'Sequence Name';
  document.getElementById('lbl-edit-seq-icon').textContent = lang === 'ko' ? '🎨 아이콘 이모지 선택 (Select Icon)' : '🎨 Select Icon Emoji';
  document.getElementById('btn-edit-seq-delete').textContent = lang === 'ko' ? '🗑️ 삭제' : '🗑️ Delete';
  document.getElementById('btn-edit-seq-cancel').textContent = lang === 'ko' ? '취소' : 'Cancel';
  document.getElementById('btn-edit-seq-confirm').textContent = lang === 'ko' ? '저장' : 'Save';
}

function selectSeqEmoji(emoji) {
  document.getElementById('edit-seq-icon').value = emoji;
  var opts = document.querySelectorAll('.seq-icon-emoji-opt');
  opts.forEach(function(opt) {
    if (opt.textContent === emoji) {
      opt.style.borderColor = '#10b981';
      opt.style.background = '#0f172a';
    } else {
      opt.style.borderColor = '#475569';
      opt.style.background = '#1e293b';
    }
  });
}

function closeEditSequenceModal() {
  var modal = document.getElementById('s-edit-seq-modal');
  if (modal) modal.style.display = 'none';
}

function submitEditSequence() {
  var origName = document.getElementById('edit-seq-original-name').value;
  var newName = document.getElementById('edit-seq-name').value.trim();
  var icon = document.getElementById('edit-seq-icon').value.trim() || '📂';
  
  if (!newName) {
    alertOrStyled(lang === 'ko' ? '순서 이름을 입력하세요.' : 'Please enter a name for the sequence.');
    return;
  }
  
  var skillIds = state.savedSequences[origName] || [];
  
  fetch(BACKEND + '/api/save-sequence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: newName,
      skill_ids: skillIds
    })
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (data.success) {
      state.sequenceIcons[newName] = icon;
      persistSequenceIcons();
      
      if (origName !== newName) {
        delete state.savedSequences[origName];
        if (state.sequenceIcons[origName]) {
          delete state.sequenceIcons[origName];
          persistSequenceIcons();
        }
        
        var voiceUpdated = false;
        state.voiceMappings.forEach(function(m) {
          if (m.action === 'sequence:' + origName) {
            m.action = 'sequence:' + newName;
            voiceUpdated = true;
          }
        });
        if (voiceUpdated) {
          persistVoiceMappings();
          renderVoiceMappings();
        }
        
        fetch(BACKEND + '/api/delete-sequence?name=' + encodeURIComponent(origName), { method: 'DELETE' });
      }
      
      state.savedSequences[newName] = skillIds;
      
      slog(lang === 'ko' ? '순서 "' + newName + '" 수정 완료!' : 'Sequence "' + newName + '" updated successfully!', 's-log-ok');
      renderCards();
      populateActionSelect();
          closeEditSequenceModal();
    } else {
      alertOrStyled(lang === 'ko' ? '저장 실패: ' + (data.error || '') : 'Save failed: ' + (data.error || ''));
    }
  })
  .catch(function(err) {
    slog(lang === 'ko' ? '네트워크 오류로 순서 수정 실패' : 'Sequence update failed due to network error', 's-log-err');
  });
}

function deleteSequenceFromEdit() {
  var name = document.getElementById('edit-seq-original-name').value;
  var confirmMsg = lang === 'ko'
    ? '순서 "' + name + '"를 삭제하시겠습니까?'
    : 'Are you sure you want to delete sequence "' + name + '"?';
  confirmOrStyled(confirmMsg, lang === 'ko' ? '순서 삭제' : 'Delete Sequence', true).then(function(confirmed) {
    if (!confirmed) return;

    fetch(BACKEND + '/api/delete-sequence?name=' + encodeURIComponent(name), { method: 'DELETE' })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success) {
        delete state.savedSequences[name];
        if (state.sequenceIcons[name]) {
          delete state.sequenceIcons[name];
          persistSequenceIcons();
        }

        var voiceUpdated = false;
        state.voiceMappings = state.voiceMappings.filter(function(m) {
          return m.action !== 'sequence:' + name;
        });
        persistVoiceMappings();
        renderVoiceMappings();

        slog(lang === 'ko' ? '순서 "' + name + '" 삭제 완료!' : 'Sequence "' + name + '" deleted successfully!', 's-log-ok');
        renderCards();
        populateActionSelect();
            closeEditSequenceModal();
      } else {
        alertOrStyled(lang === 'ko' ? '삭제 실패: ' + (data.error || '') : 'Delete failed: ' + (data.error || ''));
      }
    });
  });
}

// ─── 큐 관리 ─────────────────────────────────────────────────────
function addToQueue(mv) {
  state.queue.push({ skill_id: mv.skill_id, display_name_kr: mv.display_name_kr, display_name_en: mv.display_name_en, icon: mv.icon,
    robot_label: mv.robot_label || state.robotCardLabel, robot_family: mv.robot_family || state.robotCardFamily });
  state.previewResult = null;
  renderQueue();
  updateExecuteBtn();
  slog((lang === 'ko' ? '추가: ' : 'Added: ') + (lang === 'ko' ? mv.display_name_kr : mv.display_name_en));
}

function buildCatalogMap() {
  var catalogMap = {};
  state.catalog.forEach(function(mv) {
    catalogMap[mv.skill_id] = mv;
  });
  return catalogMap;
}

function makeQueueItemFromSkillId(sid, catalogMap) {
  var mv = catalogMap[sid];
  if (mv) {
    return {
      skill_id: mv.skill_id,
      display_name_kr: mv.display_name_kr,
      display_name_en: mv.display_name_en,
      icon: mv.icon,
      robot_label: mv.robot_label || state.robotCardLabel,
      robot_family: mv.robot_family || state.robotCardFamily
    };
  }
  return {
    skill_id: sid,
    display_name_kr: lang === 'ko' ? '미유효 동작 (' + sid + ')' : 'Invalid pose (' + sid + ')',
    display_name_en: 'Invalid pose (' + sid + ')',
    icon: '⚠️'
  };
}

function appendSequenceRecipe(name, skillIds) {
  var catalogMap = buildCatalogMap();
  var added = 0;
  skillIds.forEach(function(sid) {
    state.queue.push(makeQueueItemFromSkillId(sid, catalogMap));
    added++;
  });
  state.previewResult = null;
  renderQueue();
  updateExecuteBtn();
  slog(lang === 'ko' ? '저장 순서 "' + name + '" 추가: ' + added + '개 동작' : 'Saved sequence "' + name + '" added: ' + added + ' steps', 's-log-ok');
}

function removeFromQueue(idx) {
  state.queue.splice(idx, 1);
  state.previewResult = null;
  renderQueue();
  updateExecuteBtn();
}

function clearQueue() {
  state.queue = [];
  state.previewResult = null;
  renderQueue();
  updateExecuteBtn();
}

function renderQueue() {
  var container = document.getElementById('s-queue');
  var emptyEl = document.getElementById('s-queue-empty');
  var controls = document.getElementById('s-queue-controls');
  container.textContent = '';

  if (state.queue.length === 0) {
    var emptyDiv = document.createElement('div');
    emptyDiv.className = 's-queue-empty';
    emptyDiv.id = 's-queue-empty';
    emptyDiv.textContent = t().queueEmpty;
    container.appendChild(emptyDiv);
    if (controls) controls.style.display = 'none';
    return;
  }

  if (controls) controls.style.display = 'flex';

  state.queue.forEach(function(item, idx) {
    var row = document.createElement('div');
    row.className = 's-queue-item';
    row.id = 'q-item-' + idx;

    if (!state.running) {
      row.draggable = true;
      row.addEventListener('dragstart', function(e) {
        e.dataTransfer.setData('text/plain', idx);
        row.classList.add('s-dragging');
      });
      row.addEventListener('dragend', function() {
        row.classList.remove('s-dragging');
      });
      row.addEventListener('dragover', function(e) {
        e.preventDefault();
        row.classList.add('s-dragover');
      });
      row.addEventListener('dragleave', function() {
        row.classList.remove('s-dragover');
      });
      row.addEventListener('drop', function(e) {
        e.preventDefault();
        row.classList.remove('s-dragover');
        var fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
        var toIdx = idx;
        if (!isNaN(fromIdx) && fromIdx !== toIdx) {
          var temp = state.queue.splice(fromIdx, 1)[0];
          // The drop target is the card occupying the destination slot.  If
          // the source was above it, removing the source shifts that target
          // left by one; without this correction a downward move skipped a
          // slot and appeared to move in the wrong direction.
          var insertIdx = toIdx > fromIdx ? toIdx - 1 : toIdx;
          state.queue.splice(insertIdx, 0, temp);
          renderQueue();
          updateExecuteBtn();
        }
      });
    }

    var num = document.createElement('span');
    num.className = 's-queue-num';
    num.textContent = idx + 1;
    row.appendChild(num);

    var icon = document.createElement('span');
    icon.className = 's-queue-icon';
    if (item.icon && (item.icon.indexOf('data:image/') === 0 || item.icon.indexOf('/') === 0 || item.icon.indexOf('http') === 0)) {
      var img = document.createElement('img');
      img.src = item.icon;
      img.style.width = '20px';
      img.style.height = '20px';
      img.style.objectFit = 'contain';
      img.style.verticalAlign = 'middle';
      icon.appendChild(img);
    } else {
      icon.textContent = item.icon || '▶';
    }
    row.appendChild(icon);

    var name = document.createElement('span');
    name.className = 's-queue-name';
    name.textContent = lang === 'ko' ? item.display_name_kr : item.display_name_en;
    row.appendChild(name);

    var queueRobotLabel = shortRobotCardLabel(item.robot_label || item.robot_family);
    if (window.DEXTER_HANGEUL_MOCK && queueRobotLabel) {
      var robotBadge = document.createElement('span');
      robotBadge.className = 's-queue-robot-badge robot-family-' + (item.robot_family || 'other');
      robotBadge.textContent = queueRobotLabel;
      row.appendChild(robotBadge);
    }

    var status = document.createElement('span');
    status.className = 's-queue-status';
    status.id = 'q-status-' + idx;
    row.appendChild(status);

    var removeBtn = document.createElement('button');
    removeBtn.className = 's-queue-remove';
    removeBtn.textContent = '✕';
    removeBtn.title = lang === 'ko' ? '제거' : 'Remove';
    removeBtn.addEventListener('click', (function(i) {
      return function() { removeFromQueue(i); };
    })(idx));
    row.appendChild(removeBtn);

    container.appendChild(row);
  });
}

function updateQueueEmpty() {
  var el = document.getElementById('s-queue-empty');
  if (el) el.textContent = t().queueEmpty;
}

// ─── 실행 버튼 상태 ──────────────────────────────────────────────
function updateExecuteBtn() {
  var btn = document.getElementById('btn-execute');
  if (!btn) return;
  btn.disabled = state.queue.length === 0 || state.running;
  btn.textContent = state.running ? t().execRunning : t().execBtn;
  updatePauseBtn();
}

function updatePauseBtn() {
  var btn = document.getElementById('btn-pause');
  if (!btn) return;
  btn.disabled = !state.running && !state.paused;
  if (state.paused) {
    btn.textContent = lang === 'ko' ? '▶ 계속 진행' : '▶ Resume';
    btn.style.background = '#10b981';
    btn.style.borderColor = '#059669';
    btn.style.color = '#fff';
  } else {
    btn.textContent = lang === 'ko' ? '⏸ 일시 정지' : '⏸ Pause';
    btn.style.background = '#f59e0b';
    btn.style.borderColor = '#d97706';
    btn.style.color = '#111827';
  }
}

// ─── 미리보기 ────────────────────────────────────────────────────
function doPreview() {
  if (state.queue.length === 0) return;
  var steps = state.queue.map(function(item, idx) {
    return { order: idx + 1, stepName: item.display_name_kr, actionType: 'MOVE_TO_POSE', target: '', direction: '', value: null, unit: '', poseId: item.skill_id + '_PREVIEW' };
  });
  var catalogIds = state.catalog.map(function(m) { return m.skill_id; });
  var allMapped = state.queue.every(function(item) { return catalogIds.indexOf(item.skill_id) !== -1; });
  state.previewResult = { all_mapped: allMapped, queue: state.queue };

  var schedBtn = document.getElementById('s-schedule-preview');
  if (schedBtn) {
    if (allMapped) {
      schedBtn.textContent = (lang === 'ko' ? '✓ ' : '✓ ') + t().previewOk + ' — ' + state.queue.length + (lang === 'ko' ? '개 동작' : ' movement(s)');
      schedBtn.style.color = '#4ade80';
    } else {
      schedBtn.textContent = '✗ ' + t().previewFail;
      schedBtn.style.color = '#f87171';
    }
  }

  slog((lang === 'ko' ? '미리보기: ' : 'Preview: ') + (allMapped ? t().previewOk : t().previewFail), allMapped ? 's-log-ok' : 's-log-err');
  updateExecuteBtn();
}

// ─── 안전 모달 ───────────────────────────────────────────────────
var pendingSafetyAction = null;

function showModal(action) {
  pendingSafetyAction = typeof action === 'function' ? action : null;
  document.getElementById('s-modal').style.display = 'flex';
}
function hideModal() {
  document.getElementById('s-modal').style.display = 'none';
  hideHomePoseNotice();
}
function resetQueueVisuals() {
  for (var i = 0; i < state.queue.length; i++) {
    var r = document.getElementById('q-item-' + i);
    var s = document.getElementById('q-status-' + i);
    if (r) {
      r.classList.remove('s-executing', 's-done', 's-blocked');
    }
    if (s) s.textContent = '';
  }
}

// ─── 옛 자세 이어받기 ──────────────────────────────────────────
// 지문에 단위·교정이 들어가면서 부품이 안 바뀌었는데도 옛 자세가 막혔다.
// 값은 그대로 있으므로 **도장만 옮긴다.** 다만 부품이 진짜 달라진 것을 섞어
// 옮기면 엉뚱한 관절값이 되살아나므로, **증명되는 것만** 손댄다.
//
// 자주 쓸 것이 아니라 한 번 지나가는 정비다. 그래서 로봇 목록이 아니라
// 환경설정에 둔다 — 로봇을 골라서 하는 일이 아니다.
function openRestampModal() {
  var menu = document.querySelector('.s-settings-menu');
  if (menu) menu.classList.remove('open');
  document.getElementById('s-restamp-modal').style.display = 'flex';
  document.getElementById('restamp-msg').textContent = '';
  document.getElementById('btn-restamp-run').style.display = '';
  countRestampable();
}

function closeRestampModal() {
  document.getElementById('s-restamp-modal').style.display = 'none';
}

// 누르기 전에 **몇 개가 대상인지** 보여준다. 모르고 누르게 하지 않는다.
function countRestampable() {
  var box = document.getElementById('restamp-count');
  box.textContent = t().restampCounting;
  fetch(BACKEND + '/api/restamp-poses/preview', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.movable) {
        box.textContent = t().restampNothing;
        document.getElementById('btn-restamp-run').style.display = 'none';
        return;
      }
      box.innerHTML = '<div>' + escapeHtml(t().restampMovable) + ': <b>' +
        d.movable + '</b></div>' +
        (d.skipped ? '<div style="color:#94a3b8;">' + escapeHtml(t().restampSkipped) +
                     ': ' + d.skipped + '</div>' : '');
    })
    .catch(function () { box.textContent = t().restampNothing; });
}

function runRestamp() {
  var btn = document.getElementById('btn-restamp-run');
  btn.disabled = true;
  document.getElementById('restamp-msg').textContent = t().restampRunning;
  fetch(BACKEND + '/api/restamp-poses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator: '운영자', confirmed: true })
  }).then(function (r) { return r.json(); })
    .then(function (d) {
      document.getElementById('restamp-msg').textContent = d.ok
        ? (t().restampDone + ' ' + (d.moved || 0))
        : (d.error || t().restampFailed);
      slog(t().restampTitle + ': ' + (d.moved || 0), d.ok ? 's-log-ok' : 's-log-err');
      return countRestampable();
    })
    .catch(function (err) {
      document.getElementById('restamp-msg').textContent = t().restampFailed + ' ' + err;
    })
    .then(function () { btn.disabled = false; });
}

// ─── 상태점검(시운전) — 환경설정 안에 둔다 ──────────────────────
// CMOS가 켤 때 부품을 훑어보는 자리와 같다. 별도 화면이 아니라 환경설정이다.
// **쓰기 전에** 조금 움직여 보고 부품마다 알려 준다 — 실행해 보고 실패해서
// 아는 것(사후)과, 누르기 전에 아는 것(사전)은 다르다.
// 순서는 하나다. **창을 겹치지 않는다.**
//
//     환경설정 → 상태점검  →  안전 주의(기존 것)  →  실행  →  결과 팝업  →  닫기
//
// 전에는 점검 창을 먼저 띄우고 그 위에 안전 창을 띄웠다. 뒤에 가려 보이지
// 않아서 사람은 "화면이 어두워졌는데 아무것도 없다"고 느꼈고, 닫기를 누르자
// 그제야 안전 문구가 나왔다. 그리고 결과는 이미 닫힌 창에 그려서 보이지도
// 않았다 — 다시 열어야 볼 수 있었다. 한 번에 하나씩만 띄운다.
// 상태점검은 **로봇 목록에서 시작한다.** 거기에 이미 체크박스가 있고,
// 실행 시작·예약 취소·초기화가 같은 줄에 있다. 환경설정에 따로 두면 고르는
// 자리와 누르는 자리가 갈라져, 로봇이 수십 대가 되면 사람이 헤맨다.
//
// 목록의 [🔧 상태점검]이 체크된 로봇 id를 들고 이 함수를 부른다.
function startSelfCheckFor(ids) {
  if (!ids || !ids.length) return;
  // 점검은 **기본 자세에서 시작해야** 잰 값을 지난번과 견줄 수 있다. 다만
  // 안전한 자세는 로봇마다 달라 코드가 정할 수 없고, 운영자는 이미 자기
  // 동작 순서를 갖고 있다. 그래서 강제하지 않고 **알리기만** 한다.
  var line = document.getElementById('m-item-home');
  if (line) line.style.display = '';
  // 로봇이 움직인다. **기존 실행과 같은 안전 확인을 쓴다** — 점검이라고
  // 따로 만든 확인을 두면 사람이 두 가지를 외워야 하고, 하나는 느슨해진다.
  // 확인 단추가 hideModal() 뒤에 이 함수를 부른다.
  showModal(function () { runSelfCheck(ids); });
}

function closeSelfCheckModal() {
  document.getElementById('s-check-modal').style.display = 'none';
}

// 이 줄은 상태점검에서만 쓴다. 다른 실행의 확인 창에 남아 있으면 안 된다.
function hideHomePoseNotice() {
  var line = document.getElementById('m-item-home');
  if (line) line.style.display = 'none';
}

function runSelfCheck(ids) {
  // 결과 창을 **먼저** 띄운다. 움직이는 동안 아무것도 안 보이면 사람은
  // 멈춘 줄 안다. 여기에 진행 상황을 적고, 끝나면 같은 자리에 결과가 찬다.
  document.getElementById('s-check-modal').style.display = 'flex';
  document.getElementById('check-result').innerHTML = '';
  document.getElementById('check-usage').innerHTML = '';

  // **한 대씩 차례로 돈다.** 여러 대가 동시에 움직이면 사람이 어느 쪽을
  // 봐야 할지 모르고, 하나를 멈추려다 다른 하나를 놓친다.
  var results = [];
  var chain = Promise.resolve();
  ids.forEach(function (robotId, index) {
    chain = chain.then(function () {
      document.getElementById('check-msg').textContent =
        t().selfCheckWait + ' (' + (index + 1) + '/' + ids.length + ')';
      return fetch(BACKEND + '/api/self-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ robot_id: robotId, operator: '운영자',
                               confirmed: true, workspace_clear: true })
      }).then(function (r) { return r.json(); })
        .then(function (d) {
          results.push({ robotId: robotId, data: d });
          renderSelfCheck(results);
          slog(t().selfCheckTitle + ' [' + robotId + ']: ' +
               (d.verdict || d.stopped || ''),
               d.verdict === '정상' ? 's-log-ok' : 's-log-err');
        })
        .catch(function (err) {
          results.push({ robotId: robotId, data: { stopped: String(err) } });
          renderSelfCheck(results);
        });
    });
  });
  chain.then(function () {
    var bad = results.filter(function (r) { return r.data.verdict !== '정상'; });
    document.getElementById('check-msg').textContent = bad.length
      ? (t().selfCheckDone + bad.length + '/' + results.length + ' ' + t().checkHasProblem)
      : (t().selfCheckDone + t().checkAllOk);
    return loadSelfCheckUsage(ids);
  });
}

function renderSelfCheck(results) {
  // 로봇마다 한 덩이. **어느 로봇 이야기인지 먼저 적는다** — 기종이 섞이면
  // 관절 이름만 보고는 어느 팔인지 알 수 없다.
  var color = { '정상': '#34d399', '이상': '#f87171', '확인 불가': '#94a3b8' };
  document.getElementById('check-result').innerHTML = results.map(function (item) {
    var d = item.data || {};
    var joints = d.joints || {};
    var ids = Object.keys(joints);
    var head = '<div style="font-weight:700;color:#cbd5e1;margin:14px 0 6px;">' +
      escapeHtml(item.robotId) +
      (d.verdict ? ' <span style="color:' + (color[d.verdict] || '#94a3b8') +
                   '">· ' + escapeHtml(d.verdict) + '</span>' : '') + '</div>';
    if (!ids.length) {
      return head + '<div style="color:#94a3b8;padding:4px 0;">' +
        escapeHtml(d.stopped || t().selfCheckFailed) + '</div>';
    }
    return head + ids.map(function (id) {
      var row = joints[id] || {};
      // 관절 이름은 **런타임이 알려준다.** 화면이 몇 번째가 손인지 맞추지 않는다.
      var name = (d.labels && d.labels[id]) || id;
      var why = row.reason || row.note || '';
      if (!why && row.error_deg !== undefined) why = '오차 ' + row.error_deg + '도';
      return '<div style="display:flex;gap:10px;padding:6px 0;border-bottom:1px solid #334155;">' +
        '<span style="width:5em;flex:none;">' + escapeHtml(name) + '</span>' +
        '<span style="width:4.5em;flex:none;font-weight:700;color:' +
          (color[row.state] || '#94a3b8') + '">' + escapeHtml(row.state || '') + '</span>' +
        '<span style="color:#94a3b8;">' + escapeHtml(why) + '</span></div>';
    }).join('');
  }).join('');
}

function loadSelfCheckUsage(ids) {
  var box = document.getElementById('check-usage');
  box.innerHTML = '';
  // 주행거리계도 로봇마다 따로다. 남의 이력을 섞으면 정비 주기가 틀어진다.
  var chain = Promise.resolve();
  (ids || []).forEach(function (robotId) {
    chain = chain.then(function () {
      return fetch(BACKEND + '/api/usage?robot_id=' + encodeURIComponent(robotId),
                   { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          // **기록이 없으면 없다고 말한다.** 0으로 꾸미면 새 로봇과 안 쓴
          // 로봇이 같아 보인다.
          if (!d.has_history) {
            box.innerHTML += '<div style="padding:6px 0;">' + escapeHtml(robotId) +
              ' — ' + escapeHtml(t().usageNone) + '</div>';
            return;
          }
          var rows = [[t().usageTime, Math.round((d.moving_seconds || 0) / 60) +
                       (lang === 'ko' ? '분' : ' min')],
                      [t().usageCount, (d.move_count || 0) + (lang === 'ko' ? '번' : '')],
                      [t().usageBusiest, (d.labels && d.labels[d.busiest_joint]) ||
                                         d.busiest_joint || '—']];
          if (d.last_self_check_at) {
            rows.push([t().usageLastCheck, d.last_self_check_at.replace('T', ' ') +
                       ' · ' + (d.last_self_check_verdict || '')]);
          }
          box.innerHTML += '<div style="font-weight:700;color:#cbd5e1;margin:12px 0 6px;">' +
            escapeHtml(t().usageTitle) + ' — ' + escapeHtml(robotId) + '</div>' +
            rows.map(function (r) {
              return '<div style="display:flex;gap:10px;padding:4px 0;">' +
                '<span style="width:9em;flex:none;">' + escapeHtml(r[0]) + '</span>' +
                '<span>' + escapeHtml(String(r[1])) + '</span></div>';
            }).join('');
        })
        .catch(function () {
          box.innerHTML += '<div style="padding:6px 0;">' + escapeHtml(robotId) +
            ' — ' + escapeHtml(t().usageNone) + '</div>';
        });
    });
  });
  return chain;
}

// ─── 범용 스타일 팝업 (2026-07-23: dexter_grid/hangeul 공용으로 승격) ─────
// 브라우저 기본 alert/confirm은 "127.0.0.1:8501/18092 내용:" 같은 주소창
// 접두어가 붙는 못생긴 창이라(사용자 지적), 앱 디자인에 맞춘 모달로 대체한다.
// 이전엔 hangeul-grid.js에만 있어 hangeul 창에서만 적용됐는데, dexter_grid
// 자체 화면도 같은 문제가 있어(사용자 재지적) simple.js로 옮겨 두 화면 모두
// 적용되게 한다. #s-generic-modal 마크업이 없는 예외적인 페이지에서도 죽지
// 않도록, DOM을 못 찾으면 브라우저 기본 confirm/alert로 조용히 폴백한다.
var _genericModal = document.getElementById('s-generic-modal');
var _genericTitleEl = document.getElementById('generic-modal-title');
var _genericMessageEl = document.getElementById('generic-modal-message');
var _genericInputEl = document.getElementById('generic-modal-input');
var _genericCancelBtn = document.getElementById('generic-modal-cancel');
var _genericConfirmBtn = document.getElementById('generic-modal-confirm');
var _genericResolve = null;

function _closeGenericModal(result) {
  if (_genericModal) _genericModal.style.display = 'none';
  var resolve = _genericResolve;
  _genericResolve = null;
  if (resolve) resolve(result);
}

function showGenericModal(opts) {
  return new Promise(function (resolve) {
    if (!_genericModal || !_genericTitleEl || !_genericMessageEl || !_genericInputEl
        || !_genericCancelBtn || !_genericConfirmBtn) {
      resolve(null);
      return;
    }
    _genericResolve = resolve;
    _genericTitleEl.textContent = opts.title || '';
    _genericMessageEl.textContent = opts.message || '';
    _genericMessageEl.style.display = opts.message ? 'block' : 'none';
    if (opts.showInput) {
      _genericInputEl.style.display = 'block';
      _genericInputEl.value = opts.inputValue || '';
    } else {
      _genericInputEl.style.display = 'none';
    }
    _genericCancelBtn.style.display = opts.showCancel === false ? 'none' : 'inline-block';
    _genericCancelBtn.textContent = opts.cancelLabel || (lang === 'en' ? 'Cancel' : '취소');
    _genericConfirmBtn.textContent = opts.confirmLabel || (lang === 'en' ? 'OK' : '확인');
    _genericConfirmBtn.style.background = opts.danger ? '#dc2626' : '#0ea5e9';
    _genericConfirmBtn.style.borderColor = opts.danger ? '#b91c1c' : '#0284c7';
    _genericModal.style.display = 'flex';
    setTimeout(function () {
      if (opts.showInput) { _genericInputEl.focus(); _genericInputEl.select(); }
      else { _genericConfirmBtn.focus(); }
    }, 50);
  });
}

function styledAlert(message, title) {
  return showGenericModal({
    title: title || (lang === 'en' ? 'Notice' : '알림'),
    message: message, showCancel: false,
  });
}

function styledConfirm(message, title, danger) {
  return showGenericModal({
    title: title || (lang === 'en' ? 'Confirm' : '확인'),
    message: message, showCancel: true, danger: danger,
  }).then(function (result) { return result === true; });
}

function styledPrompt(message, defaultValue, title) {
  return showGenericModal({
    title: title || (lang === 'en' ? 'Input' : '입력'),
    message: message, showInput: true, inputValue: defaultValue, showCancel: true,
  });
}

window.styledConfirm = styledConfirm;
window.styledAlert = styledAlert;
window.styledPrompt = styledPrompt;

if (_genericCancelBtn) _genericCancelBtn.addEventListener('click', function () { _closeGenericModal(null); });
if (_genericConfirmBtn) {
  _genericConfirmBtn.addEventListener('click', function () {
    var value = (_genericInputEl && _genericInputEl.style.display !== 'none') ? _genericInputEl.value : true;
    _closeGenericModal(value);
  });
}
if (_genericInputEl) {
  _genericInputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') _genericConfirmBtn.click();
    if (e.key === 'Escape') _genericCancelBtn.click();
  });
}

function confirmOrStyled(message, title, danger) {
  if (_genericModal) return styledConfirm(message, title, danger);
  return Promise.resolve(window.confirm(message));
}
function alertOrStyled(message, title) {
  if (_genericModal) return styledAlert(message, title);
  window.alert(message);
  return Promise.resolve();
}

function triggerEStop() {
  var btn = document.getElementById('btn-estop');
  if (!btn) return;

  if (state.estopActive) {
    var resumeMsg = lang === 'ko'
      ? '긴급 정지를 해제하고 로봇을 재개합니다. 작업 공간에 사람이 없고 안전한 상태인지 확인하셨습니까?'
      : 'This resumes the robot from emergency stop. Have you confirmed the workspace is clear and safe?';
    confirmOrStyled(resumeMsg).then(function(confirmed) {
      if (!confirmed) {
        slog(lang === 'ko' ? '재개가 취소되었습니다 (확인 필요).' : 'Resume cancelled (confirmation required).', 's-log-err');
        return;
      }
      fetch(BACKEND + '/api/estop-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operator: 'web_operator', confirmed: true })
      })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.success) {
            state.estopActive = false;
            btn.textContent = t().estop;
            btn.style.background = '#dc2626';
            btn.style.borderColor = '#b91c1c';
            btn.style.boxShadow = '0 0 12px rgba(220, 38, 38, 0.5)';
            slog(lang === 'ko' ? '긴급 정지 해제 완료! 로봇 작동 가능 상태입니다.' : 'Emergency Stop reset. Robot is operational.', 's-log-ok');

            resetQueueVisuals();
            var statusEl = document.getElementById('s-exec-status');
            if (statusEl) {
              statusEl.textContent = lang === 'ko' ? '대기 중 (준비 완료)' : 'Ready';
              statusEl.style.color = '#cbd5e1';
            }
          } else {
            alertOrStyled('E-Stop 해제 실패: ' + d.error);
          }
        })
        .catch(function() {
          alertOrStyled('네트워크 오류');
        });
    });
  } else {
    state.running = false;
    state.paused = false;
    state.resumeExecution = null;
    if (state.activeTimer) {
      clearTimeout(state.activeTimer);
      state.activeTimer = null;
    }
    setBanner(false);
    updateExecuteBtn();
    
    resetQueueVisuals();
    
    var statusEl = document.getElementById('s-exec-status');
    if (statusEl) {
      statusEl.textContent = lang === 'ko' ? '긴급 정지 활성화됨!' : 'E-STOP ACTIVE!';
      statusEl.style.color = '#ef4444';
    }
    
    fetch(BACKEND + '/api/estop', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        state.estopActive = true;
        btn.textContent = t().estopReset;
        btn.style.background = '#10b981';
        btn.style.borderColor = '#059669';
        btn.style.boxShadow = '0 0 12px rgba(16, 185, 129, 0.5)';
        
        var msg = d.message || d.warning || '긴급 정지!';
        slog(msg, 's-log-err');
      })
      .catch(function() {
        state.estopActive = true;
        btn.textContent = t().estopReset;
        btn.style.background = '#10b981';
        btn.style.borderColor = '#059669';
        btn.style.boxShadow = '0 0 12px rgba(16, 185, 129, 0.5)';
        slog(lang === 'ko'
          ? '긴급 정지 소프트웨어 락 적용 완료 (하드웨어 통신 제한)'
          : 'Emergency stop software lock applied (hardware communication limited)', 's-log-err');
      });
  }
}

function togglePause() {
  if (!state.running && !state.paused) return;
  var statusEl = document.getElementById('s-exec-status');

  if (state.paused) {
    state.paused = false;
    updatePauseBtn();
    if (statusEl) {
      statusEl.textContent = lang === 'ko' ? '일시 정지 해제: 이어서 진행합니다.' : 'Pause released: resuming.';
      statusEl.style.color = '#4ade80';
    }
    slog(lang === 'ko' ? '일시 정지 해제 — 작업을 이어서 진행합니다.' : 'Pause released — resuming task.', 's-log-ok');
    var resume = state.resumeExecution;
    state.resumeExecution = null;
    if (resume) resume();
    return;
  }

  state.paused = true;
  if (state.activeTimer) {
    clearTimeout(state.activeTimer);
    state.activeTimer = null;
  }
  fetch(BACKEND + '/api/pause-hold', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      slog(d.message || d.warning || (lang === 'ko' ? '일시 정지: 현재 자세 유지' : 'Paused: holding current pose'), 's-log-ok');
    })
    .catch(function(err) {
      slog((lang === 'ko' ? '일시 정지 유지 요청 실패: ' : 'Pause hold request failed: ') + err.message, 's-log-err');
    });
  if (statusEl) {
    statusEl.textContent = lang === 'ko' ? '일시 정지 중 — 계속 진행을 누르면 이어서 실행합니다.' : 'Paused — press Resume to continue.';
    statusEl.style.color = '#fbbf24';
  }
  updatePauseBtn();
}

function doExecute() {
  if (state.running || state.queue.length === 0) return;
  if (state.estopActive) {
    alertOrStyled(lang === 'ko' ? '긴급 정지 상태입니다. 해제 후 실행해 주세요.' : 'E-STOP is active. Reset E-STOP first.');
    return;
  }

  var safetyInputs = {
    operator_present: true,
    workspace_clear: true,
    human_nearby: false,
    manual_stop_available: true,
    estop_ready: true
  };

  var runMode = document.getElementById('opt-repeat-count').checked ? 'count' : 'time';
  var maxCycles = parseInt(document.getElementById('s-repeat-count').value, 10) || 1;
  var workMin = parseFloat(document.getElementById('s-work-min').value || '60');
  var restMin = parseFloat(document.getElementById('s-rest-min').value || '10');
  var totalHours = parseFloat(document.getElementById('s-total-hours').value || '24');

  state.running = true;
  state.paused = false;
  state.resumeExecution = null;
  updateExecuteBtn();
  setBanner(true);

  var statusEl = document.getElementById('s-exec-status');
  if (statusEl) statusEl.style.color = '#cbd5e1';
  
  var queueCopy = state.queue.slice();
  var qIdx = 0;
  var currentCycle = 1;
  var workStartTime = Date.now();
  var workDurationMs = workMin * 60 * 1000;
  var jobStartTime = Date.now();
  var totalJobDurationMs = totalHours * 60 * 60 * 1000;

  slog((lang === 'ko' ? '실행 시작 — 모드: ' : 'Starting execution — Mode: ') + 
       (runMode === 'count' ? 
        (lang === 'ko' ? '지정 횟수 (' + maxCycles + '회)' : 'Count (' + maxCycles + ' times)') : 
        (lang === 'ko' ? '시간제 (작동 ' + workMin + '분 / 휴식 ' + restMin + '분 / 전체 ' + totalHours + '시간)' : 'Time-based (Work ' + workMin + 'm / Rest ' + restMin + 'm / Total ' + totalHours + 'h)')
       )
  );

  function isJobTimeExpired() {
    if (runMode === 'time' && (Date.now() - jobStartTime >= totalJobDurationMs)) {
      slog(lang === 'ko' ? '설정된 전체 작업 시간(' + totalHours + '시간)이 만료되어 자동으로 종료합니다.' : 'Total job duration (' + totalHours + ' hours) expired. Stopping execution.', 's-log-ok');
      finishExecution(true);
      return true;
    }
    return false;
  }

  function pauseIfNeeded(nextFn) {
    if (!state.paused) return false;
    state.resumeExecution = nextFn;
    if (statusEl) {
      statusEl.textContent = lang === 'ko' ? '일시 정지 중 — 계속 진행 대기' : 'Paused — waiting to resume';
      statusEl.style.color = '#fbbf24';
    }
    return true;
  }

  function startRestPhase() {
    if (!state.running) return;
    if (pauseIfNeeded(startRestPhase)) return;
    if (isJobTimeExpired()) return;
    
    resetQueueVisuals();
    var restTimeRemainingSec = Math.round(restMin * 60);
    
    slog(lang === 'ko' ? '휴식 기동: ' + restMin + '분 정지 유지 시작' : 'Rest started: holding position for ' + restMin + 'm', 's-log-ok');
    
    function tickRest() {
      if (!state.running) return;
      if (pauseIfNeeded(tickRest)) return;
      if (isJobTimeExpired()) return;
      
      if (restTimeRemainingSec <= 0) {
        slog(lang === 'ko' ? '휴식 기동 완료! 새로운 작동 주기 시작' : 'Rest complete! Starting new work cycle.', 's-log-ok');
        workStartTime = Date.now();
        qIdx = 0;
        runNext();
      } else {
        var min = Math.floor(restTimeRemainingSec / 60);
        var sec = restTimeRemainingSec % 60;
        
        var elapsedJob = Date.now() - jobStartTime;
        var remainingJobSec = Math.max(0, Math.round((totalJobDurationMs - elapsedJob) / 1000));
        var remJobHours = Math.floor(remainingJobSec / 3600);
        var remJobMin = Math.floor((remainingJobSec % 3600) / 60);
        
        if (statusEl) {
          statusEl.textContent = lang === 'ko'
            ? '[전체남음 ' + remJobHours + 'h ' + remJobMin + 'm] 정지 휴식 중 (남은 시간: ' + min + '분 ' + sec + '초)'
            : '[Total remaining ' + remJobHours + 'h ' + remJobMin + 'm] Resting (time left: ' + min + 'm ' + sec + 's)';
        }
        restTimeRemainingSec--;
        state.activeTimer = setTimeout(tickRest, 1000);
      }
    }
    
    tickRest();
  }

  function runNext() {
    if (!state.running) return;
    if (pauseIfNeeded(runNext)) return;
    if (isJobTimeExpired()) return;

    if (qIdx >= queueCopy.length) {
      if (runMode === 'count') {
        if (currentCycle < maxCycles) {
          currentCycle++;
          qIdx = 0;
          resetQueueVisuals();
          slog(lang === 'ko' ? '시퀀스 완료! 반복 실행 중: ' + currentCycle + '/' + maxCycles + ' 회차...' : 'Sequence finished! Running cycle: ' + currentCycle + '/' + maxCycles + '...');
          runNext();
        } else {
          finishExecution(true);
        }
      } else {
        var elapsed = Date.now() - workStartTime;
        if (elapsed < workDurationMs) {
          qIdx = 0;
          resetQueueVisuals();
          
          var elapsedJob = Date.now() - jobStartTime;
          var remainingJobSec = Math.max(0, Math.round((totalJobDurationMs - elapsedJob) / 1000));
          var remJobHours = Math.floor(remainingJobSec / 3600);
          var remJobMin = Math.floor((remainingJobSec % 3600) / 60);
          
          var remainingSec = Math.max(0, Math.round((workDurationMs - elapsed) / 1000));
          var remMin = Math.floor(remainingSec / 60);
          var remSec = remainingSec % 60;
          
          slog(lang === 'ko' ? '시퀀스 완료! 연속 작동 중 [전체남음: ' + remJobHours + '시간 ' + remJobMin + '분 / 연속남음: ' + remMin + '분 ' + remSec + '초]' : 'Sequence finished! Continuous work [Total rem: ' + remJobHours + 'h ' + remJobMin + 'm / Work rem: ' + remMin + 'm ' + remSec + 's]');
          runNext();
        } else {
          slog(lang === 'ko' ? '작동 시간 종료! 정지 휴식기(' + restMin + '분)를 시작합니다.' : 'Work time expired! Starting rest phase (' + restMin + ' min)...');
          startRestPhase();
        }
      }
      return;
    }

    var item = queueCopy[qIdx];
    var rowEl = document.getElementById('q-item-' + qIdx);
    var statEl = document.getElementById('q-status-' + qIdx);
    if (rowEl) rowEl.classList.add('s-executing');
    
    var prefix = '';
    if (runMode === 'count') {
      prefix = '[' + (lang === 'ko' ? currentCycle + '/' + maxCycles + '회차' : 'Cycle ' + currentCycle + '/' + maxCycles) + '] ';
    } else {
      var elapsedJob = Date.now() - jobStartTime;
      var remainingJobSec = Math.max(0, Math.round((totalJobDurationMs - elapsedJob) / 1000));
      var remJobHours = Math.floor(remainingJobSec / 3600);
      var remJobMin = Math.floor((remainingJobSec % 3600) / 60);
      
      var elapsedWork = Date.now() - workStartTime;
      var remainingSec = Math.max(0, Math.round((workDurationMs - elapsedWork) / 1000));
      var remMin = Math.floor(remainingSec / 60);
      var remSec = remainingSec % 60;
      
      prefix = lang === 'ko'
        ? '[전체남음 ' + remJobHours + 'h ' + remJobMin + 'm / 작동남음 ' + remMin + 'm ' + remSec + 's] '
        : '[Total rem ' + remJobHours + 'h ' + remJobMin + 'm / Work rem ' + remMin + 'm ' + remSec + 's] ';
    }

    if (statusEl) statusEl.textContent = prefix + (lang === 'ko' ? '동작 실행 중 (' : 'Executing (') + (qIdx+1) + '/' + queueCopy.length + ') ' + (lang === 'ko' ? item.display_name_kr : item.display_name_en);

    // SLLM 도우미로 승인받은 동작이면 1회용 실행 토큰을 함께 보낸다(hangeul).
    // 토큰은 서버에서 1회만 소비되므로 보내는 즉시 화면 쪽에서도 지운다 —
    // 남겨두면 다음번 수동 실행이 소비된 토큰을 다시 보내 거부된다.
    var sllmGrantId = (window.__sllmGrants || {})[item.skill_id] || null;
    if (sllmGrantId) delete window.__sllmGrants[item.skill_id];

    fetch(BACKEND + '/api/execute-actual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        skill_id: item.skill_id,
        operator: 'web_operator',
        robot_model: getRobotModel(),
        device: getRobotDevice(),
        safety_inputs: safetyInputs,
        safety_limits: state.safetyLimits || {},
        issue_token: true,
        proposal_id: sllmGrantId
      })
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!state.running) return;

      var ok = d.verdict && (d.verdict === 'ACTUAL_MOTION_EXECUTED_ONCE' || d.verdict === 'REPEAT_COMPLETED' || d.verdict === 'PREFLIGHT_READY_NO_MOTION_EXECUTED');
      var blocked = d.verdict && d.verdict.indexOf('BLOCKED') !== -1;
      
      if (rowEl) {
        rowEl.classList.remove('s-executing');
        rowEl.classList.add(blocked ? 's-blocked' : 's-done');
      }
      if (statEl) statEl.textContent = d.verdict || '';
      var displayName = lang === 'ko' ? item.display_name_kr : (item.display_name_en || item.display_name_kr);
      slog((lang === 'ko' ? '결과: ' : 'Result: ') + displayName + ' → ' + d.verdict + (d.actual_hardware_called ? ' ✓hw' : ''), ok ? 's-log-ok' : 's-log-err');
      
      if (blocked) {
        var reasonMsg = d.verdict;
        if (d.blocked_reasons && d.blocked_reasons.length > 0) {
          reasonMsg += ' (' + d.blocked_reasons.join(', ') + ')';
        }
        if (hasDisconnectLatchBlock(d.blocked_reasons)) {
          var shouldRecover = window.confirm(lang === 'ko'
            ? 'USB 연결이 끊겼다가 복구된 상태로 보입니다. 로봇 포트를 자동 재탐색하고 단선 래치를 해제할까요?'
            : 'The robot USB connection appears to have reconnected. Probe robot ports and clear the disconnect latch?');
          if (shouldRecover) {
            recoverRobotUsbFromUi();
          }
        }
        finishExecution(false, reasonMsg);
        return;
      }

      if (!ok) {
        var errorMsg = d.error || d.message || d.verdict || (lang === 'ko' ? '실행 실패' : 'Execution failed');
        if (d.stage) errorMsg += ' [' + d.stage + ']';
        finishExecution(false, errorMsg);
        return;
      }
      
      qIdx++;
      if (pauseIfNeeded(runNext)) return;
      
      var catalogItem = state.catalog.find(function(c) { return c.skill_id === item.skill_id; });
      var delaySec = catalogItem ? (catalogItem.delay_sec || 0.0) : 0.0;
      
      if (delaySec > 0) {
        if (statEl) statEl.textContent = (lang === 'ko' ? '대기 중 (' : 'Waiting (') + delaySec + '초)...';
        slog((lang === 'ko' ? '대기 중: ' : 'Delaying: ') + delaySec + '초...', 's-log-ok');
        
        state.activeTimer = setTimeout(function() {
          state.activeTimer = null;
          if (pauseIfNeeded(runNext)) return;
          runNext();
        }, delaySec * 1000);
      } else {
        runNext();
      }
    })
    .catch(function(e) {
      if (rowEl) {
        rowEl.classList.remove('s-executing');
        rowEl.classList.add('s-blocked');
      }
      slog((lang === 'ko' ? '오류: ' : 'Error: ') + e.message, 's-log-err');
      finishExecution(false, e.message);
    });
  }

  runNext();
}

function finishExecution(success, reason) {
  state.running = false;
  state.paused = false;
  state.resumeExecution = null;
  if (state.activeTimer) {
    clearTimeout(state.activeTimer);
    state.activeTimer = null;
  }
  setBanner(false);
  updateExecuteBtn();
  updatePauseBtn();
  var statusEl = document.getElementById('s-exec-status');
  if (statusEl) {
    statusEl.textContent = success ? t().execDone : (t().execBlocked + (reason ? ': ' + reason : ''));
    if (!success) statusEl.style.color = '#ef4444';
  }
  slog(success ? (lang === 'ko' ? '실행 완료' : 'Execution complete') : (lang === 'ko' ? '실행 차단: ' : 'Blocked: ') + (reason || ''), success ? 's-log-ok' : 's-log-err');
}

function setBanner(active) {
  var el = document.getElementById('s-warn-banner');
  if (!el) return;
  if (active) { el.classList.add('s-warn-active'); el.textContent = t().warnActive; }
  else { el.classList.remove('s-warn-active'); el.textContent = t().warn; }
}

// ─── 이벤트 바인딩 ───────────────────────────────────────────────
document.getElementById('btn-lang').addEventListener('click', function() {
  lang = lang === 'ko' ? 'en' : 'ko';
  localStorage.setItem(UI_LANG_STORAGE_KEY, lang);
  applyI18n();
  renderCards();
  renderQueue();
  populateActionSelect();
  renderVoiceMappings();
  updateMicroMovePreview();
  refreshAwayModeButton();
  refreshAwayModeSchedule();
});

document.getElementById('btn-clear-queue').addEventListener('click', clearQueue);
document.getElementById('btn-preview').addEventListener('click', doPreview);

document.getElementById('btn-repeat-toggle').addEventListener('click', function() {
  var panel = document.getElementById('s-repeat-panel');
  var isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : 'block';
  this.textContent = isOpen ? t().repeatToggleOpen : t().repeatToggleClose;
});

document.getElementById('btn-execute').addEventListener('click', function() {
  if (state.queue.length === 0 || state.running) return;
  showModal();
});

document.getElementById('btn-modal-cancel').addEventListener('click', hideModal);

document.getElementById('btn-modal-confirm').addEventListener('click', function() {
  hideModal();
  var action = pendingSafetyAction;
  pendingSafetyAction = null;
  if (action) {
    action();
  } else {
    doExecute();
  }
});

document.getElementById('btn-admin-limits').addEventListener('click', openAdminModal);
document.getElementById('btn-admin-close').addEventListener('click', closeAdminModal);
document.getElementById('btn-admin-submit').addEventListener('click', submitAdminLimits);

// ─── 조작 및 자세 저장 (Jog & Save Pose) ───────────────────────────
function getSafetyInputs() {
  return {
    operator_present: true,
    workspace_clear: true,
    human_nearby: false,
    manual_stop_available: true,
    estop_ready: true
  };
}

function readCurrentPose() {
  var btn = document.getElementById('btn-read-pose');
  if (btn) btn.disabled = true;
  fetch(BACKEND + '/api/read-pose?device=' + encodeURIComponent(getRobotDevice()) + '&robot_model=' + encodeURIComponent(getRobotModel()))
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success && data.present) {
        for (var jid in data.present) {
          var el = document.getElementById('jog-val-' + jid);
          if (el) el.textContent = formatUiValue(jid, data.present[jid]);
        }
        slog(lang === 'ko' ? '현재 자세 값을 읽어왔습니다.' : 'Successfully read current pose.', 's-log-ok');
      } else {
        var pf = data.hardware_preflight || {};
        var detail = pf.controller_connected !== undefined
          ? ' controller_connected=' + pf.controller_connected
            + ' angles=' + (pf.angles_response !== undefined ? pf.angles_response : 'invalid')
            + ' error_information=' + (pf.error_information !== undefined ? pf.error_information : 'unknown')
          : '';
        slog(lang === 'ko'
          ? '자세 읽기 실패: ' + (data.error || '') + detail
          : 'Failed to read pose: ' + (data.error || '') + detail, 's-log-err');
      }
    })
    .catch(function(err) {
      slog(lang === 'ko' ? '네트워크 오류로 자세를 읽지 못했습니다.' : 'Network error reading pose.', 's-log-err');
    })
    .finally(function() {
      if (btn) btn.disabled = false;
    });
}

function motionFailureReason(data) {
  return data.error || (data.blocked_reasons && data.blocked_reasons.length
    ? data.blocked_reasons.join('; ') : '') || data.reason || data.verdict ||
    (lang === 'ko' ? '이동 결과를 확인하지 못했습니다' : 'Could not verify the move result');
}

function motionFailureMessage(data, jointId, target) {
  var reason = motionFailureReason(data);
  if (!data.present || data.present[String(jointId)] === undefined || target == null) {
    return (lang === 'ko' ? '이동 확인 실패: ' : 'Move verification failed: ') + reason;
  }
  var actual = formatUiValue(jointId, data.present[String(jointId)]);
  return (lang === 'ko' ? '목표 미도달: 목표 ' : 'Target not reached: target ') +
    formatUiValue(jointId, target) + (lang === 'ko' ? ', 실제 ' : ', actual ') + actual + ' · ' + reason;
}

function jogJoint(jointId, deltaTicks) {
  var deltaUi = rawToUiValue(jointId, deltaTicks);
  var deltaUnit = isMyCobotUi() ? (isGripperJoint(jointId) ? '%' : '°') : 'ticks';
  slog((lang === 'ko' ? 'J' + jointId + ' 관절 이동 요청 (' + deltaUi + ' ' + deltaUnit + ')' : 'Requested J' + jointId + ' move (' + deltaUi + ' ' + deltaUnit + ')'));
  
  var btns = document.querySelectorAll('.s-btn-jog');
  btns.forEach(function(b) { b.disabled = true; });

  fetch(BACKEND + '/api/jog', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      joint_id: jointId,
      delta_ticks: deltaTicks,
      robot_model: getRobotModel(),
      device: getRobotDevice(),
      safety_inputs: getSafetyInputs(),
      safety_limits: state.safetyLimits || {}
    })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.present) {
        for (var jid in data.present) {
          var el = document.getElementById('jog-val-' + jid);
          if (el) el.textContent = formatUiValue(jid, data.present[jid]);
        }
      }
      if (data.success && data.present) {
        slog((lang === 'ko' ? 'J' + jointId + ' 이동 완료 (Target: ' + formatUiValue(jointId, data.target) + ')' : 'J' + jointId + ' moved successfully (Target: ' + formatUiValue(jointId, data.target) + ')'), 's-log-ok');
      } else {
        var actual = data.present && data.present[String(jointId)] !== undefined
          ? formatUiValue(jointId, data.present[String(jointId)]) : '-';
        slog(motionFailureMessage(data, jointId, data.target), 's-log-err');
      }
    })
    .catch(function(err) {
      slog((lang === 'ko' ? '이동 중 오류 발생: ' + err.message : 'Error moving joint: ' + err.message), 's-log-err');
    })
    .finally(function() {
      btns.forEach(function(b) { b.disabled = false; });
    });
}

var MICRO_MOVE_DEFS = {};

function rebuildMicroMoveDefs() {
  MICRO_MOVE_DEFS = {};
  operableJointIds().forEach(function(jointId) {
    var meta = jointMeta(jointId);
    MICRO_MOVE_DEFS[String(jointId)] = {
      jointId: jointId,
      delta: isMyCobotUi() ? 5 : 50,     // MyCobot 5도 · OMX 50틱
      labelKo: meta.label_kr || ('J' + jointId),
      labelEn: meta.label_en || ('J' + jointId)
    };
  });
  populateMicroMoveJointSelect();
}

function defaultMicroMoveKey() {
  var armIds = operableJointIds().filter(function(jointId) { return !isGripperJoint(jointId); });
  return String(armIds[1] || armIds[0] || allJointIds()[0] || 12);
}

function populateMicroMoveJointSelect() {
  var select = document.getElementById('micro-move-joint');
  if (!select) return;
  var previous = select.value;
  select.innerHTML = '';
  operableJointIds().forEach(function(jointId) {
    var opt = document.createElement('option');
    opt.value = String(jointId);
    opt.textContent = jointLabel(jointId);
    select.appendChild(opt);
  });
  select.value = MICRO_MOVE_DEFS[previous] ? previous : defaultMicroMoveKey();
}

function microMoveLimit() {
  // 한계는 그 관절이 실제로 갈 수 있는 폭까지다. 5도라는 고정 상한은
  // 기본값(5도)조차 못 넘게 만들어 미세 이동을 무의미하게 했다.
  if (!isMyCobotUi()) return 200;
  var selected = document.getElementById('micro-move-joint');
  var range = selected ? getJointTickLimit(parseInt(selected.value, 10)) : null;
  if (!range) return 180;
  var span = isGripperJoint(parseInt(selected.value, 10))
    ? range[1] - range[0]
    : (range[1] - range[0]) / 1000;
  return Math.max(5, span / 2);
}

function clampMicroMoveDelta(value) {
  var n = isMyCobotUi() ? parseFloat(value) : parseInt(value, 10);
  var limit = microMoveLimit();
  if (isNaN(n) || n === 0) return isMyCobotUi() ? 5 : 1;
  return Math.max(-limit, Math.min(limit, n));
}

function clampMicroMoveRepeat(value) {
  // 횟수 상한은 두지 않는다(대표 지시). 각 회마다 안전 범위 검사를 그대로 지난다.
  var n = parseInt(value, 10);
  if (isNaN(n) || n < 1) return 1;
  return n;
}

function getMicroMoveSelection() {
  var jointEl = document.getElementById('micro-move-joint');
  var deltaEl = document.getElementById('micro-move-delta');
  var repeatEl = document.getElementById('micro-move-repeat');
  var key = jointEl ? jointEl.value : defaultMicroMoveKey();
  var def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  if (!def) {
    rebuildMicroMoveDefs();
    def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  }
  return {
    key: key,
    jointId: def.jointId,
    delta: clampMicroMoveDelta(deltaEl ? deltaEl.value : def.delta),
    repeat: clampMicroMoveRepeat(repeatEl ? repeatEl.value : 1),
    label: lang === 'ko' ? def.labelKo : def.labelEn
  };
}

function readMicroMoveDeltaForPreview(value) {
  if (value === '' || value === '-' || value === '+') return null;
  var n = isMyCobotUi() ? parseFloat(value) : parseInt(value, 10);
  if (isNaN(n)) return null;
  var limit = microMoveLimit();
  return Math.max(-limit, Math.min(limit, n));
}

function readMicroMoveRepeatForPreview(value) {
  if (value === '') return null;
  var n = parseInt(value, 10);
  if (isNaN(n)) return null;
  return Math.max(1, n);
}

function updateMicroMovePreview(normalize) {
  var preview = document.getElementById('micro-move-preview');
  var deltaEl = document.getElementById('micro-move-delta');
  var repeatEl = document.getElementById('micro-move-repeat');
  if (!preview) return;
  var jointEl = document.getElementById('micro-move-joint');
  var key = jointEl ? jointEl.value : defaultMicroMoveKey();
  var def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  if (!def) {
    rebuildMicroMoveDefs();
    def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  }
  if (!def) return;
  var delta = readMicroMoveDeltaForPreview(deltaEl ? deltaEl.value : def.delta);
  var repeat = readMicroMoveRepeatForPreview(repeatEl ? repeatEl.value : 1);
  if (normalize) {
    if (deltaEl) deltaEl.value = delta == null ? def.delta : delta;
    if (repeatEl) repeatEl.value = repeat == null ? 1 : repeat;
    delta = readMicroMoveDeltaForPreview(deltaEl ? deltaEl.value : def.delta);
    repeat = readMicroMoveRepeatForPreview(repeatEl ? repeatEl.value : 1);
  }
  var unit = isMyCobotUi() ? (isGripperJoint(def.jointId) ? '%' : '°') : ' ticks';
  preview.textContent = 'J' + def.jointId + ' ' + (delta == null ? '입력 중' : ((delta > 0 ? '+' : '') + delta + unit)) + ' x ' + (repeat == null ? '?' : repeat) + (lang === 'ko' ? '회' : 'x');
}

function normalizeMicroMoveInputs() {
  updateMicroMovePreview(true);
}

function updateMicroMoveDefaults() {
  var jointEl = document.getElementById('micro-move-joint');
  var deltaEl = document.getElementById('micro-move-delta');
  var key = jointEl ? jointEl.value : defaultMicroMoveKey();
  var def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  if (!def) {
    rebuildMicroMoveDefs();
    def = MICRO_MOVE_DEFS[key] || MICRO_MOVE_DEFS[defaultMicroMoveKey()];
  }
  if (!def) return;
  if (deltaEl) {
    // 입력칸의 한계·눈금도 로봇에 맞춘다. MyCobot은 도, OMX는 틱이다.
    var limit = microMoveLimit();
    deltaEl.min = String(-limit);
    deltaEl.max = String(limit);
    deltaEl.step = isMyCobotUi() ? '1' : '10';
    deltaEl.value = def.delta;
  }
  updateMicroMovePreview(true);
}

function setMicroMoveControlsDisabled(disabled) {
  ['micro-move-joint', 'micro-move-delta', 'micro-move-repeat', 'btn-micro-move-run'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
  document.querySelectorAll('.s-btn-jog').forEach(function(b) { b.disabled = disabled; });
}

function jogJointOnce(jointId, deltaTicks) {
  return fetch(BACKEND + '/api/jog', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      joint_id: jointId,
      delta_ticks: deltaTicks,
      robot_model: getRobotModel(),
      device: getRobotDevice(),
      safety_inputs: getSafetyInputs(),
      safety_limits: state.safetyLimits || {}
    })
  })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (!data.success) {
        throw new Error(motionFailureReason(data));
      }
      if (data.present) {
        for (var jid in data.present) {
          var el = document.getElementById('jog-val-' + jid);
          if (el) el.textContent = formatUiValue(jid, data.present[jid]);
        }
      }
      return data;
    });
}

function runMicroMoveMode() {
  var move = getMicroMoveSelection();
  normalizeMicroMoveInputs();
  move = getMicroMoveSelection();
  showModal(function() {
    startMicroMoveExecution(move);
  });
}

function startMicroMoveExecution(move) {
  var status = document.getElementById('micro-move-status');
  setMicroMoveControlsDisabled(true);
  updateMicroMovePreview(true);
  var rawDelta = uiDeltaToRaw(move.jointId, move.delta);
  var microUnit = isMyCobotUi() ? (isGripperJoint(move.jointId) ? '%' : '°') : ' ticks';
  slog((lang === 'ko'
    ? '미세 이동 전용 모드 시작: ' + move.label + ' J' + move.jointId + ' ' + move.delta + microUnit + ' x ' + move.repeat + '회'
    : 'Micro move start: ' + move.label + ' J' + move.jointId + ' ' + move.delta + microUnit + ' x ' + move.repeat));

  var chain = Promise.resolve();
  for (var i = 1; i <= move.repeat; i += 1) {
    (function(step) {
      chain = chain.then(function() {
        if (status) {
          status.textContent = (lang === 'ko' ? '실행 중 ' : 'Running ') + step + '/' + move.repeat + ' · J' + move.jointId + ' ' + (move.delta > 0 ? '+' : '') + move.delta;
        }
        return jogJointOnce(move.jointId, rawDelta);
      });
    })(i);
  }

  chain
    .then(function() {
      var steps = [];
      for (var idx = 1; idx <= move.repeat; idx += 1) {
        steps.push({ step: idx, joint_id: move.jointId, delta_ticks: rawDelta });
      }
      lastMicroMovePlan = {
        createdAt: Date.now(),
        label: move.label,
        joint_id: move.jointId,
        delta_ticks: rawDelta,
        repeat: move.repeat,
        steps: steps
      };
      if (status) status.textContent = lang === 'ko' ? '미세 이동 완료' : 'Micro move complete';
      slog((lang === 'ko' ? '미세 이동 완료' : 'Micro move complete'), 's-log-ok');
    })
    .catch(function(err) {
      if (status) status.textContent = (lang === 'ko' ? '미세 이동 중단: ' : 'Micro move stopped: ') + err.message;
      slog((lang === 'ko' ? '미세 이동 중단: ' : 'Micro move stopped: ') + err.message, 's-log-err');
    })
    .finally(function() {
      setMicroMoveControlsDisabled(false);
    });
}

function openSaveModal() {
  document.getElementById('s-save-modal').style.display = 'flex';
  document.getElementById('save-modal-title').textContent = lang === 'ko' ? '💾 현재 자세를 새 동작으로 저장' : '💾 Save Current Pose as New Movement';
  var recentMicroMove = lastMicroMovePlan && (Date.now() - lastMicroMovePlan.createdAt < 10 * 60 * 1000);
  document.getElementById('save-modal-subtitle').textContent = recentMicroMove
    ? (lang === 'ko'
        ? '최근 미세 이동이 있습니다. 저장 방식을 직접 선택하세요.'
        : 'A recent micro-move is available. Choose how to save this card.')
    : (lang === 'ko'
        ? '이 자세를 단순 모드 카드 목록에 등록하여 원클릭으로 실행할 수 있게 만듭니다.'
        : 'Register this pose in the simple mode card list for one-click execution.');
  var motionTypePanel = document.getElementById('save-motion-type-panel');
  var absoluteRadio = document.getElementById('save-motion-absolute');
  var microRadio = document.getElementById('save-motion-micro');
  if (motionTypePanel) motionTypePanel.style.display = recentMicroMove ? 'block' : 'none';
  if (absoluteRadio) absoluteRadio.checked = true;
  if (microRadio) microRadio.checked = false;
  var motionTitle = document.getElementById('save-motion-type-title');
  var absLabel = document.getElementById('save-motion-absolute-label');
  var microLabel = document.getElementById('save-motion-micro-label');
  if (motionTitle) motionTitle.textContent = lang === 'ko' ? '저장 방식' : 'Save Mode';
  if (absLabel) absLabel.textContent = lang === 'ko' ? '끊김 없이 이동' : 'Smooth absolute move';
  if (microLabel) microLabel.textContent = lang === 'ko' ? '미세 이동' : 'Micro move';
  
  document.getElementById('save-skill-id').value = '';
  document.getElementById('save-name-kr').value = '';
  document.getElementById('save-name-en').value = '';
  document.getElementById('save-desc-kr').value = '';
  document.getElementById('save-desc-en').value = '';
  setSaveLanguageFields();
  document.getElementById('save-delay-sec').value = '0.0';
  document.getElementById('btn-edit-delete').style.display = 'none';
  
  allJointIds().forEach(function(j) {
    var chk = document.getElementById('chk-save-j' + j);
    if (chk) chk.checked = true;
  });
  
  // The API stores MyCobot arm targets as millidegrees, but the editor must
  // show degrees. Convert the displayed UI value back to the raw API unit only
  // when submitting the pose.
  allJointIds().forEach(function(j) {
    var valEl = document.getElementById('jog-val-' + j);
    var meta = jointMeta(j);
    var displayed = valEl ? parseFloat(valEl.textContent) : NaN;
    var val = valEl && isFinite(displayed)
      ? (isMyCobotUi() ? displayed : parseInt(displayed, 10))
      : meta.default_ticks;
    var input = document.getElementById('save-tick-' + j);
    if (input) input.value = val;
  });
  applyJointLimitUi();
  
  selectEmoji('💾');
  if (window.setupRepeatPoseSave) {
    var repeatPlan = null;
    try { repeatPlan = window.readRepeatWorkPlan(); } catch (_) {}
    window.setupRepeatPoseSave(repeatPlan);
  }
}

function openEditModal(mv) {
  document.getElementById('s-save-modal').style.display = 'flex';
  document.getElementById('save-modal-title').textContent = lang === 'ko' ? '✎ 동작 카드 수정' : 'Edit Movement Card';
  document.getElementById('save-modal-subtitle').textContent = lang === 'ko' ? '동작 이름, 설명, 제어할 관절과 목표 각도를 편집할 수 있습니다.' : 'Edit the name, description, active joints, and target ticks.';
  var motionTypePanel = document.getElementById('save-motion-type-panel');
  if (motionTypePanel) motionTypePanel.style.display = 'none';
  
  document.getElementById('save-skill-id').value = mv.skill_id;
  document.getElementById('save-name-kr').value = mv.display_name_kr || '';
  document.getElementById('save-name-en').value = mv.display_name_en || '';
  var descKr = mv.description_kr || '';
  descKr = descKr.replace(/\s*\([^)]*미검증[^)]*\)/g, '');
  document.getElementById('save-desc-kr').value = descKr;
  
  var descEn = mv.description_en || '';
  descEn = descEn.replace(/\s*\([^)]*Unverified[^)]*\)/g, '');
  document.getElementById('save-desc-en').value = descEn;
  setSaveLanguageFields();
  document.getElementById('save-delay-sec').value = mv.delay_sec !== undefined ? mv.delay_sec : '0.0';
  var fixedMovementCard = mv.skill_id === 'SAFE_BASIC_POSE_RETURN' || mv.fixed === true || mv.deletable === false;
  document.getElementById('btn-edit-delete').style.display = fixedMovementCard ? 'none' : 'inline-block';
  
  var targets = mv.targets || {};
  allJointIds().forEach(function(j) {
    var hasJoint = targets[j] !== undefined || targets[String(j)] !== undefined;
    var meta = jointMeta(j);
    var val = targets[j] !== undefined ? targets[j] : (targets[String(j)] !== undefined ? targets[String(j)] : meta.default_ticks);
    var chk = document.getElementById('chk-save-j' + j);
    var input = document.getElementById('save-tick-' + j);
    if (chk) chk.checked = hasJoint;
    if (input) input.value = isMyCobotUi() ? rawToUiValue(j, val) : val;
  });
  applyJointLimitUi();
  
  selectEmoji(mv.icon || '💾');
  if (window.setupRepeatPoseSave) window.setupRepeatPoseSave(mv.motion_type === 'repeat' ? mv.repeat_work : null);
}

function selectEmoji(emoji) {
  document.getElementById('save-icon').value = emoji;
  var opts = document.querySelectorAll('.icon-emoji-opt');
  opts.forEach(function(opt) {
    if (opt.textContent === emoji) {
      opt.style.borderColor = '#10b981';
      opt.style.background = '#0f172a';
    } else {
      opt.style.borderColor = '#475569';
      opt.style.background = '#1e293b';
    }
  });
}

function closeSaveModal() {
  document.getElementById('s-save-modal').style.display = 'none';
}

function submitSavePose() {
  var skillId = document.getElementById('save-skill-id').value || null;
  var nameKr = document.getElementById('save-name-kr').value.trim();
  var nameEn = document.getElementById('save-name-en').value.trim();
  var descKr = document.getElementById('save-desc-kr').value.trim();
  var descEn = document.getElementById('save-desc-en').value.trim();
  var icon = document.getElementById('save-icon').value.trim() || '💾';
  var delaySec = parseFloat(document.getElementById('save-delay-sec').value);
  if (isNaN(delaySec)) {
    delaySec = 0.0;
  }

  if (lang === 'ko') {
    if (!nameKr) {
      alertOrStyled('동작 이름을 입력하세요.');
      return;
    }
    nameEn = nameEn || nameKr;
    descEn = descEn || descKr;
  } else {
    if (!nameEn) {
      alertOrStyled('Please enter a movement name.');
      return;
    }
    nameKr = nameKr || nameEn;
    descKr = descKr || descEn;
  }

  var repeatPlan = null;
  try { if (window.readRepeatPoseSave) repeatPlan = window.readRepeatPoseSave(); }
  catch (err) { alertOrStyled(err.message); return; }
  var selectedJoints = [];
  var targets = {};
  var rangeErrors = [];
  (repeatPlan ? [] : allJointIds()).forEach(function(j) {
    var chk = document.getElementById('chk-save-j' + j);
    if (chk && chk.checked) {
      selectedJoints.push(j);
      var input = document.getElementById('save-tick-' + j);
      var entered = parseFloat(input ? input.value : '');
      var val = isMyCobotUi() && !isGripperJoint(j)
        ? uiToRawValue(j, entered)
        : (isMyCobotUi() ? Math.round(entered) : parseInt(entered, 10));
      if (!isNaN(val)) {
        var range = getJointTickLimit(j);
        if (range && (val < range[0] || val > range[1])) {
          rangeErrors.push('J' + j + ' ' + val + ' (' + range[0] + '~' + range[1] + ')');
        }
        targets[j] = val;
      }
    }
  });
  if (rangeErrors.length) {
    alertOrStyled(lang === 'ko'
      ? '안전 범위 밖 목표값입니다: ' + rangeErrors.join(', ')
      : 'Target ticks outside safety range: ' + rangeErrors.join(', '));
    return;
  }
  var saveAsMicro = !skillId
    && lastMicroMovePlan
    && (Date.now() - lastMicroMovePlan.createdAt < 10 * 60 * 1000)
    && document.getElementById('save-motion-micro')
    && document.getElementById('save-motion-micro').checked;

  fetch(BACKEND + '/api/save-pose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      skill_id: skillId,
      instance_id: window.repeatPoseRobotId || (state.robotJoints || {}).instance_id,
      robot_model: getRobotModel(),
      device: getRobotDevice(),
      name_kr: nameKr,
      name_en: nameEn,
      description_kr: descKr,
      description_en: descEn,
      selected_joints: selectedJoints,
      icon: icon,
      targets: targets,
      motion_type: repeatPlan ? 'repeat' : (saveAsMicro ? 'micro' : 'absolute'),
      repeat_work: repeatPlan,
      delay_sec: delaySec,
      micro_move_steps: saveAsMicro
        ? lastMicroMovePlan.steps
        : null
    })
  })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success) {
        slog(lang === 'ko' ? '동작 "' + nameKr + '" 저장 완료!' : 'Pose "' + nameEn + '" saved successfully!', 's-log-ok');
        if (saveAsMicro) {
          slog(lang === 'ko' ? '미세 이동 단계가 동작 카드에 함께 저장되었습니다.' : 'Micro-move steps saved with the card.', 's-log-ok');
          lastMicroMovePlan = null;
        }
        closeSaveModal();
        loadCatalog();
      } else {
        slog(lang === 'ko' ? '저장 실패: ' + (data.error || '') : 'Failed to save pose: ' + (data.error || ''), 's-log-err');
      }
    })
    .catch(function(err) {
      slog(lang === 'ko' ? '자세 저장 중 네트워크 오류 발생' : 'Network error saving pose.', 's-log-err');
    });
}

function deletePoseFromEdit() {
  var skillId = document.getElementById('save-skill-id').value;
  if (!skillId) return;
  var confirmMsg = lang === 'ko' ? '정말로 이 동작을 삭제하시겠습니까?' : 'Are you sure you want to delete this pose?';
  confirmOrStyled(confirmMsg, lang === 'ko' ? '동작 삭제' : 'Delete Pose', true).then(function(confirmed) {
    if (!confirmed) return;

    fetch(BACKEND + '/api/delete-pose?skill_id=' + encodeURIComponent(skillId), {
      method: 'POST'
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          slog(lang === 'ko' ? '동작이 성공적으로 삭제되었습니다.' : 'Pose deleted successfully.', 's-log-ok');
          closeSaveModal();
          loadCatalog();
        } else {
          slog(lang === 'ko' ? '삭제 실패: ' + (data.error || '') : 'Failed to delete: ' + (data.error || ''), 's-log-err');
        }
      })
      .catch(function(err) {
        slog(lang === 'ko' ? '동작 삭제 중 네트워크 오류 발생' : 'Network error deleting pose.', 's-log-err');
      });
  });
}

function moveJointTo(jointId) {
  var inputEl = document.getElementById('jog-direct-' + jointId);
  var uiTarget = isMyCobotUi() ? parseFloat(inputEl.value) : parseInt(inputEl.value, 10);
  var targetTicks = uiToRawValue(jointId, uiTarget);
  if (isNaN(targetTicks)) {
    alertOrStyled(lang === 'ko' ? '올바른 수치를 입력하세요.' : 'Please enter a valid number.');
    return;
  }
  var range = getJointTickLimit(jointId);
  if (range && (targetTicks < range[0] || targetTicks > range[1])) {
    alertOrStyled(lang === 'ko'
      ? 'J' + jointId + ' 안전 범위 밖입니다. 허용: ' + formatUiRange(jointId, range)
      : 'J' + jointId + ' is outside safety range. Allowed: ' + formatUiRange(jointId, range));
    return;
  }
  
  slog((lang === 'ko' ? 'J' + jointId + ' 관절 절대 위치 이동 요청: ' + formatUiValue(jointId, targetTicks) : 'Requested J' + jointId + ' move to: ' + formatUiValue(jointId, targetTicks)));
  
  var btns = document.querySelectorAll('.s-btn-jog');
  btns.forEach(function(b) { b.disabled = true; });

  fetch(BACKEND + '/api/move-to', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      joint_id: jointId,
      target_ticks: targetTicks,
      robot_model: getRobotModel(),
      device: getRobotDevice(),
      safety_inputs: getSafetyInputs()
    })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.present) {
        for (var jid in data.present) {
          var el = document.getElementById('jog-val-' + jid);
          if (el) el.textContent = formatUiValue(jid, data.present[jid]);
        }
      }
      if (data.success && data.present) {
        slog((lang === 'ko' ? 'J' + jointId + ' 이동 완료 (현재: ' + formatUiValue(jointId, data.present[jointId]) + ')' : 'J' + jointId + ' moved successfully (Current: ' + formatUiValue(jointId, data.present[jointId]) + ')'), 's-log-ok');
      } else {
        var actual = data.present && data.present[String(jointId)] !== undefined
          ? formatUiValue(jointId, data.present[String(jointId)]) : '-';
        slog(motionFailureMessage(data, jointId, targetTicks), 's-log-err');
        alertOrStyled((lang === 'ko' ? '이동 실패: ' + motionFailureReason(data) : 'Failed: ' + motionFailureReason(data)));
      }
    })
    .catch(function(err) {
      slog((lang === 'ko' ? '이동 중 오류 발생: ' + err.message : 'Error moving joint: ' + err.message), 's-log-err');
    })
    .finally(function() {
      btns.forEach(function(b) { b.disabled = false; });
    });
}

// ─── 시퀀스 저장/불러오기 ──────────────────────────────────────────
function openSaveSequenceModal() {
  if (state.queue.length === 0) return;
  document.getElementById('s-save-seq-modal').style.display = 'flex';
  document.getElementById('seq-save-name').value = '';
}

function closeSaveSequenceModal() {
  document.getElementById('s-save-seq-modal').style.display = 'none';
}

function submitSaveSequence() {
  var name = document.getElementById('seq-save-name').value.trim();
  if (!name) {
    alertOrStyled(lang === 'ko' ? '순서 이름을 입력하세요.' : 'Please enter a name for the sequence.');
    return;
  }
  
  var skillIds = state.queue.map(function(item) { return item.skill_id; });
  
  fetch(BACKEND + '/api/save-sequence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name,
      skill_ids: skillIds
    })
  })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success) {
        slog(lang === 'ko' ? '순서 "' + name + '"가 저장되었습니다!' : 'Sequence "' + name + '" saved!', 's-log-ok');
        state.savedSequences[name] = skillIds;
        renderCards();
        populateActionSelect();
        closeSaveSequenceModal();
      } else {
        alertOrStyled(lang === 'ko' ? '저장 실패: ' + (data.error || '') : 'Save failed: ' + (data.error || ''));
      }
    })
    .catch(function(err) {
      slog(lang === 'ko' ? '네트워크 오류로 순서 저장 실패' : 'Failed to save sequence due to network error', 's-log-err');
    });
}

function openLoadSequenceModal() {
  document.getElementById('s-load-seq-modal').style.display = 'flex';
  var container = document.getElementById('seq-list-container');
  container.textContent = lang === 'ko' ? '불러오는 중...' : 'Loading...';
  
  fetch(BACKEND + '/api/sequences')
    .then(function(res) { return res.json(); })
    .then(function(data) {
      container.textContent = '';
      var keys = Object.keys(data);
      if (keys.length === 0) {
        container.textContent = lang === 'ko' ? '저장된 순서가 없습니다.' : 'No saved sequences found.';
        return;
      }
      keys.forEach(function(key) {
        var row = document.createElement('div');
        row.style = 'display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:8px 12px; border-radius:6px; border:1px solid #334155; margin-bottom:4px;';
        
        var nameSpan = document.createElement('span');
        nameSpan.textContent = key + ' (' + data[key].length + (lang === 'ko' ? '개 동작)' : ' steps)');
        nameSpan.style = 'font-size:0.85rem; color:#f1f5f9; font-weight:500; cursor:pointer; flex-grow:1;';
        nameSpan.addEventListener('click', function() {
          loadSequenceRecipe(key, data[key]);
          closeLoadSequenceModal();
        });
        row.appendChild(nameSpan);
        
        var delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 's-seq-delete-btn';
        delBtn.textContent = '🗑️';
        delBtn.title = lang === 'ko' ? '순서 삭제' : 'Delete sequence';
        delBtn.addEventListener('pointerdown', function(e) {
          e.stopPropagation();
        });
        delBtn.addEventListener('click', function(e) {
          e.preventDefault();
          e.stopPropagation();
          deleteSequenceRecipe(key);
        });
        row.appendChild(delBtn);
        
        container.appendChild(row);
      });
    })
    .catch(function(err) {
      container.textContent = lang === 'ko' ? '데이터 로드 오류' : 'Error loading data.';
    });
}

function closeLoadSequenceModal() {
  document.getElementById('s-load-seq-modal').style.display = 'none';
}

function loadSequenceRecipe(name, skillIds) {
  state.queue = [];
  var catalogMap = buildCatalogMap();
  
  skillIds.forEach(function(sid) {
    state.queue.push(makeQueueItemFromSkillId(sid, catalogMap));
  });
  
  state.previewResult = null;
  renderQueue();
  updateExecuteBtn();
  slog(lang === 'ko' ? '순서 "' + name + '"를 대기열에 불러왔습니다.' : 'Sequence "' + name + '" loaded into queue.', 's-log-ok');
}

function deleteSequenceRecipe(name) {
  fetch(BACKEND + '/api/delete-sequence?name=' + encodeURIComponent(name), {
    method: 'DELETE'
  })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success) {
        slog(lang === 'ko' ? '순서 "' + name + '" 삭제 완료' : 'Sequence "' + name + '" deleted.', 's-log-ok');
        delete state.savedSequences[name];
        delete state.sequenceIcons[name];
        persistSequenceIcons();
        renderCards();
        populateActionSelect();
        openLoadSequenceModal();
      } else {
        alertOrStyled('삭제 실패');
      }
    })
    .catch(function() {
      alertOrStyled('네트워크 오류');
    });
}

function toggleRepeatModeUI() {
  var isCount = document.getElementById('opt-repeat-count').checked;
  document.getElementById('row-repeat-count').style.opacity = isCount ? '1' : '0.4';
  document.getElementById('s-repeat-count').disabled = !isCount;
  
  document.getElementById('row-repeat-time').style.opacity = isCount ? '0.4' : '1';
  document.getElementById('s-work-min').disabled = isCount;
  document.getElementById('s-rest-min').disabled = isCount;
  document.getElementById('s-total-hours').disabled = isCount;
}

function openAdminModal() {
  document.getElementById('s-admin-modal').style.display = 'flex';
  resetAdminTabDirtyState();
  renderAdminJointInputs();
  installSafetyLimitPreviewHandlers();
  fetch(BACKEND + '/api/safety-limits?robot_model=' + encodeURIComponent(getRobotModel()))
    .then(function(r) { return r.json(); })
    .then(function(limits) {
      state.safetyLimits = limits;
      state.jointTickLimits = normalizeJointTickLimits(limits);
      applyJointLimitUi();
      armJointIds().forEach(function(j) {
        if (limits[j]) {
          document.getElementById('admin-lim-' + j + '-min').value = limits[j][0];
          document.getElementById('admin-lim-' + j + '-max').value = limits[j][1];
        }
      });
      updateAdminRangeLabelsWithTicks();
      if (state.gripperJointId != null) {
        var gMinKey = state.gripperJointId + '_min';
        var gMaxKey = state.gripperJointId + '_max';
        var gMin = limits[gMinKey] !== undefined ? limits[gMinKey] : (limits.gripper_min !== undefined ? limits.gripper_min : limits['15_min']);
        var gMax = limits[gMaxKey] !== undefined ? limits[gMaxKey] : (limits.gripper_max !== undefined ? limits.gripper_max : limits['15_max']);
        document.getElementById('admin-lim-' + state.gripperJointId + '-min').value = gMin;
        document.getElementById('admin-lim-' + state.gripperJointId + '-max').value = gMax;
        state.jointTickLimits[state.gripperJointId] = [parseInt(gMin, 10), parseInt(gMax, 10)];
        updateAdminRangeLabelsWithTicks();
      }
      // 2026-07-04: 관절 온도 임계값 로드. 옛 safety_limits.json에는 이 키가 없을 수
      // 있으므로(하위 호환) 없으면 70을 기본으로 채운다.
      var tempLimits = limits['temperature_limits_c'] || {};
      allJointIds().forEach(function(j) {
        var el = document.getElementById('admin-temp-' + j);
        if (el) el.value = (tempLimits[j] !== undefined ? tempLimits[j] : (tempLimits[String(j)] !== undefined ? tempLimits[String(j)] : 70));
      });
      // 2026-07-05: 관절별 동작 속도 로드. 옛 파일에 키가 없으면 기존 하드코딩과
      // 동일한 기본값(팔 40, 그리퍼 50)을 채운다.
      var velLimits = limits['velocity_limits'] || {};
      allJointIds().forEach(function(j) {
        var el = document.getElementById('admin-vel-' + j);
        var def = (state.gripperJointId != null && j === state.gripperJointId) ? 50 : 40;
        if (el) el.value = (velLimits[j] !== undefined ? velLimits[j] : (velLimits[String(j)] !== undefined ? velLimits[String(j)] : def));
      });
      // 2026-07-05/06 (끊기는 동작 진단): 기본 이동 프로파일 + CUSTOM 수치 로드.
      var profileEl = document.getElementById('admin-motion-profile');
      if (profileEl) profileEl.value = limits['default_motion_profile'] || 'SAFE';
      var customProfile = limits['custom_motion_profile'] || {};
      var customStageEl = document.getElementById('admin-custom-stage-delta');
      if (customStageEl) customStageEl.value = (customProfile.max_stage_delta_ticks !== undefined ? customProfile.max_stage_delta_ticks : 800);
      var customAccelEl = document.getElementById('admin-custom-accel');
      if (customAccelEl) customAccelEl.value = (customProfile.acceleration !== undefined ? customProfile.acceleration : 12);
      toggleCustomMotionProfileInputs();
      // 2026-07-05: 사람 감지 정책 + 위험 구역 로드.
      var camEnabledEl = document.getElementById('admin-person-camera-enabled');
      if (camEnabledEl) camEnabledEl.checked = (limits['person_gate_camera_enabled'] !== false);
      var policy = limits['person_gate_policy'] || 'danger_zone';
      var policyEl = document.querySelector('input[name="person-gate-policy"][value="' + policy + '"]');
      if (policyEl) policyEl.checked = true;
      var zone = limits['person_gate_danger_zone'] || [0, 0, 1, 1];
      ['x1', 'y1', 'x2', 'y2'].forEach(function(k, idx) {
        var el = document.getElementById('admin-zone-' + k);
        if (el) el.value = zone[idx];
      });
    })
    .catch(function() {
      alertOrStyled('설정을 불러오지 못했습니다.');
    });
}

function closeAdminModal() {
  document.getElementById('s-admin-modal').style.display = 'none';
}

// 2026-07-06: CUSTOM 이동 프로파일 선택 시에만 수치 입력란을 보여준다.
function toggleCustomMotionProfileInputs() {
  var sel = document.getElementById('admin-motion-profile');
  var box = document.getElementById('custom-motion-profile-inputs');
  if (!sel || !box) return;
  box.style.display = (sel.value === 'CUSTOM') ? 'block' : 'none';
}

// 2026-07-04: "전체 적용" — 한 번 입력한 값을 J11~J15 온도 필드 전부에 복사한다.
// 저장은 그대로 각 관절별 개별 값으로 이루어지므로, 이후 특정 관절만 다시 따로
// 조정하는 것도 그대로 가능하다(일률 적용은 입력 편의 기능일 뿐 스키마를 바꾸지 않는다).
function applyTempToAllJoints() {
  var v = parseFloat(document.getElementById('admin-temp-all-value').value);
  if (isNaN(v)) {
    alertOrStyled('먼저 적용할 온도 값을 입력하세요.');
    return;
  }
  allJointIds().forEach(function(j) {
    var el = document.getElementById('admin-temp-' + j);
    if (el) el.value = v;
  });
}

// 2026-07-05: 속도 "전체 적용" — 온도의 applyTempToAllJoints와 동일한 편의 기능.
// 저장은 각 관절별 개별 값으로 이루어진다.
function applyVelToAllJoints() {
  var v = parseInt(document.getElementById('admin-vel-all-value').value, 10);
  if (isNaN(v)) {
    alertOrStyled('먼저 적용할 속도 값을 입력하세요.');
    return;
  }
  allJointIds().forEach(function(j) {
    var el = document.getElementById('admin-vel-' + j);
    if (el) el.value = v;
  });
}

function submitAdminLimits() {
  var limits = {};
  var invalid = false;

  armJointIds().forEach(function(j) {
    var minVal = parseFloat(document.getElementById('admin-lim-' + j + '-min').value);
    var maxVal = parseFloat(document.getElementById('admin-lim-' + j + '-max').value);
    if (isNaN(minVal) || isNaN(maxVal) || minVal > maxVal) {
      invalid = true;
    }
    limits[j] = [minVal, maxVal];
  });

  if (state.gripperJointId != null) {
    var gMin = parseInt(document.getElementById('admin-lim-' + state.gripperJointId + '-min').value, 10);
    var gMax = parseInt(document.getElementById('admin-lim-' + state.gripperJointId + '-max').value, 10);
    if (isNaN(gMin) || isNaN(gMax) || gMin > gMax) {
      invalid = true;
    }
    limits[state.gripperJointId + '_min'] = gMin;
    limits[state.gripperJointId + '_max'] = gMax;
    if (state.gripperJointId === 15) {
      limits['15_min'] = gMin;
      limits['15_max'] = gMax;
    }
  }

  // 2026-07-04: 관절 온도 임계값 검증 및 수집. 0~100℃ 밖은 실수 입력으로 간주해 차단한다
  // (모터 사양상 100℃ 넘으면 이미 하드웨어 자체 열 차단 영역이라 설정할 이유가 없다).
  var tempLimits = {};
  allJointIds().forEach(function(j) {
    var tVal = parseFloat(document.getElementById('admin-temp-' + j).value);
    if (isNaN(tVal) || tVal < 0 || tVal > 100) {
      invalid = true;
    }
    tempLimits[j] = tVal;
  });
  limits['temperature_limits_c'] = tempLimits;

  // 2026-07-05: 관절별 동작 속도 검증 및 수집. 1~200 밖은 차단한다
  // (상한 200은 실물 boundary 검증 범위 — 서버도 동일하게 재검증한다).
  var velLimits = {};
  allJointIds().forEach(function(j) {
    var vVal = parseInt(document.getElementById('admin-vel-' + j).value, 10);
    if (isNaN(vVal) || vVal < 1 || vVal > 200) {
      invalid = true;
    }
    velLimits[j] = vVal;
  });
  limits['velocity_limits'] = velLimits;

  // 2026-07-05/06 (끊기는 동작 진단): 기본 이동 프로파일 + CUSTOM 수치 수집.
  var profileSel = document.getElementById('admin-motion-profile');
  var selectedProfile = profileSel ? profileSel.value : 'SAFE';
  limits['default_motion_profile'] = selectedProfile;
  if (selectedProfile === 'CUSTOM') {
    var stageVal = parseInt(document.getElementById('admin-custom-stage-delta').value, 10);
    var accelVal = parseInt(document.getElementById('admin-custom-accel').value, 10);
    if (isNaN(stageVal) || stageVal < 100 || stageVal > 1200) {
      invalid = true;
    }
    if (isNaN(accelVal) || accelVal < 6 || accelVal > 40) {
      invalid = true;
    }
    limits['custom_motion_profile'] = { max_stage_delta_ticks: stageVal, acceleration: accelVal };
  }

  // 2026-07-05: 사람 감지 정책 + 위험 구역 수집. 좌표는 0~1, x1<x2, y1<y2.
  var policySel = document.querySelector('input[name="person-gate-policy"]:checked');
  limits['person_gate_policy'] = policySel ? policySel.value : 'danger_zone';
  var camEnabledBox = document.getElementById('admin-person-camera-enabled');
  limits['person_gate_camera_enabled'] = camEnabledBox ? camEnabledBox.checked : true;
  var zx1 = parseFloat(document.getElementById('admin-zone-x1').value);
  var zy1 = parseFloat(document.getElementById('admin-zone-y1').value);
  var zx2 = parseFloat(document.getElementById('admin-zone-x2').value);
  var zy2 = parseFloat(document.getElementById('admin-zone-y2').value);
  if (isNaN(zx1) || isNaN(zy1) || isNaN(zx2) || isNaN(zy2) ||
      zx1 < 0 || zy1 < 0 || zx2 > 1 || zy2 > 1 || zx1 >= zx2 || zy1 >= zy2) {
    invalid = true;
  } else {
    limits['person_gate_danger_zone'] = [zx1, zy1, zx2, zy2];
  }

  if (invalid) {
    alertOrStyled('입력된 범위 설정이 올바르지 않습니다.');
    return;
  }

  fetch(BACKEND + '/api/save-safety-limits?robot_model=' + encodeURIComponent(getRobotModel()), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(limits)
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.success) {
        slog(lang === 'ko' ? '안전 범위 설정이 성공적으로 저장되었습니다.' : 'Safety limits saved successfully.', 's-log-ok');
        closeAdminModal();
        loadSafetyLimitsForUi().then(loadCatalog);
      } else {
        alertOrStyled('설정 저장 실패: ' + d.error);
      }
    })
    .catch(function() {
      alertOrStyled('네트워크 오류');
    });
}
// ─── AI 음성 및 비전 핸들러 ──────────────────────────────────────────
function applyVoicePreset() {
  var preset = document.getElementById('s-voice-presets').value;
  if (preset) {
    document.getElementById('s-voice-input').value = preset;
  }
}

function parseDexterWakeCommand(cmd) {
  var normalized = String(cmd || '')
    .toLowerCase()
    .replace(/[.,!?:;\-_/\\[\](){}"'“”‘’]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  var wakeNames = ['dexter', '덱스터', '덱트서', '덱터', '댁스터', '덱스타'];
  var wakeTemplates = ['안녕 {name}', 'hey {name}', '헤이 {name}'];
  var wakePhrases = [];
  wakeTemplates.forEach(function(template) {
    wakeNames.forEach(function(name) {
      wakePhrases.push(template.replace('{name}', name));
    });
  });
  var body = '';
  var wake = '';
  for (var i = 0; i < wakePhrases.length; i += 1) {
    var phrase = wakePhrases[i];
    if (normalized === phrase) {
      wake = phrase;
      body = '';
      break;
    }
    if (normalized.indexOf(phrase + ' ') === 0) {
      wake = phrase;
      body = normalized.slice(phrase.length).trim();
      break;
    }
  }
  if (!wake) return { allowed: false, command: '', wake: '', reason: 'wake_required' };
  ['명령 끝', '명령끝', '입력 끝', '입력끝', '음성 끝', '음성끝', '끝', '종료', '오버', 'over'].some(function(endPhrase) {
    if (body === endPhrase) {
      body = '';
      return true;
    }
    if (body.slice(-endPhrase.length - 1) === ' ' + endPhrase) {
      body = body.slice(0, -endPhrase.length).trim();
      return true;
    }
    return false;
  });
  return { allowed: !!body, command: body, wake: wake, reason: body ? 'ok' : 'empty_command' };
}

function isDirectEmergencyStopPhrase(cmd) {
  var text = String(cmd || '').toLowerCase().trim();
  // Strip wake words
  var wakeNames = ['dexter', '덱스터', '덱트서', '덱터', '댁스터', '덱스타'];
  var wakeTemplates = ['안녕 {name}', 'hey {name}', '헤이 {name}'];
  var wakePhrases = [];
  wakeTemplates.forEach(function(template) {
    wakeNames.forEach(function(name) {
      wakePhrases.push(template.replace('{name}', name));
    });
  });
  for (var i = 0; i < wakePhrases.length; i += 1) {
    var phrase = wakePhrases[i];
    if (text === phrase) {
      text = '';
      break;
    }
    if (text.indexOf(phrase + ' ') === 0) {
      text = text.slice(phrase.length).trim();
      break;
    }
  }
  // Strip end phrases
  var endPhrases = ['명령 끝', '명령끝', '입력 끝', '입력끝', '음성 끝', '음성끝', '끝', '종료', '오버', 'over'];
  for (var j = 0; j < endPhrases.length; j += 1) {
    var ep = endPhrases[j];
    if (text.endsWith(' ' + ep)) {
      text = text.slice(0, -ep.length).trim();
      break;
    }
    if (text === ep) {
      text = '';
      break;
    }
  }

  var normalized = text
    .replace(/e[\s-]*stop/g, 'estop')
    .replace(/[.,!?:;\-_/\\[\](){}"'“”‘’]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  var compact = normalized.replace(/\s+/g, '');
  var exact = {
    '정지': true,
    '정지해': true,
    '정지해줘': true,
    '정지해주세요': true,
    '멈춰': true,
    '멈춰줘': true,
    '멈춰주세요': true,
    '스탑': true,
    '스톱': true,
    '스탑해': true,
    '스톱해': true,
    '긴급정지': true,
    'stop': true,
    'estop': true
  };
  return !!exact[compact];
}

function applyVoiceControlResult(d, feedbackEl) {
  feedbackEl.innerHTML = '<strong>' + ((d && (d.detail || d.action)) || '') + '</strong>';
  if (d && d.action === 'stop') {
    feedbackEl.style.color = '#f87171';
    state.estopActive = true;
    state.running = false;
    state.paused = false;
    updateExecuteBtn();
    updatePauseBtn();
    var estopBtn = document.getElementById('btn-estop');
    if (estopBtn) {
      estopBtn.textContent = t().estopReset;
      estopBtn.style.background = '#10b981';
      estopBtn.style.borderColor = '#059669';
    }
    slog(lang === 'ko' ? '음성 긴급 정지 처리됨' : 'Voice emergency stop handled', 's-log-err');
  } else {
    feedbackEl.style.color = '#facc15';
  }
}

function sendEmergencyStopVoiceCommand(cmd, feedbackEl) {
  return fetch(BACKEND + '/api/voice-control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd })
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      applyVoiceControlResult(d, feedbackEl);
      return d;
    })
    .catch(function() {
      feedbackEl.innerHTML = '⚠️ 네트워크 오류';
      feedbackEl.style.color = '#f87171';
    });
}

function hasDisconnectLatchBlock(reasons) {
  return Array.isArray(reasons) && reasons.some(function(reason) {
    return String(reason || '').indexOf('disconnect_latched') !== -1;
  });
}

function recoverRobotUsbFromUi() {
  slog(lang === 'ko' ? 'USB 복구 시작: 로봇 포트를 read-only로 재탐색합니다.' : 'USB recovery started: probing robot ports read-only.', 's-log-info');
  return fetch(BACKEND + '/api/recover-robot-usb', { method: 'POST' })
    .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
    .then(function(d) {
      if (!d.success) {
        throw new Error(d.error || 'robot usb recovery failed');
      }
      slog((lang === 'ko' ? 'USB 포트 복구: ' : 'USB recovered: ') + d.effective_device, 's-log-ok');
      return fetch(BACKEND + '/api/estop-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          operator: 'web_operator',
          confirmed: true,
          workspace_clear: true,
          estop_confirmed: true,
          manual_recovery_confirmed: true
        })
      });
    })
    .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
    .then(function(d) {
      if (!d.success) {
        throw new Error(d.error || (d.disconnect_recovery && d.disconnect_recovery.blocked_reason) || 'disconnect latch reset failed');
      }
      state.estopActive = false;
      updateExecuteBtn();
      slog(lang === 'ko' ? 'USB 단선 래치 복구 완료. 다시 실행해 주세요.' : 'Disconnect latch recovered. Run again.', 's-log-ok');
      return d;
    })
    .catch(function(err) {
      var suffix = lang === 'ko'
        ? ' 서버를 재시작한 뒤 다시 시도하세요.'
        : ' Restart the server, then try again.';
      slog((lang === 'ko' ? 'USB 복구 실패: ' : 'USB recovery failed: ') + err.message + suffix, 's-log-err');
      alertOrStyled((lang === 'ko' ? 'USB 복구 실패: ' : 'USB recovery failed: ') + err.message + '\n\n' + suffix);
    });
}

function openServerRestartHelp() {
  // 완전 초기화 — 콘솔과 로봇 런타임을 모두 끄고, 남은 막힘(단선 기록·일시정지·
  // 장치 임대)을 푼 뒤 다시 띄운다. 일은 tools/launcher.py reset 이 한다(Reset.bat 과 같은 길).
  // 전에는 "새로고침하세요"만 남기고 결과를 보여 주지 않아, 런타임이 빠진 채로 떠도
  // 사람은 알 수 없었다(2026-09-24). 이제 돌아올 때까지 기다렸다가 결과를 보여 준다.
  // **비상 정지는 풀지 않는다** — 정지 해제는 사람이 로봇을 보고 한다.
  var confirmMsg = lang === 'ko'
    ? '콘솔과 로봇 프로그램을 모두 끄고 처음부터 다시 시작합니다. 팔에는 명령을 보내지 않지만, 연결이 다시 열릴 때 스스로 초기화되는 팔이 있으니 팔을 낮은 자세에 두고 누르세요. 30초쯤 걸립니다. 계속할까요?'
    : 'Stop the console and robot programs and start everything again. No command is sent to the arm, but some controllers reset when the connection reopens, so rest the arm low first. Takes about 30 seconds. Continue?';
  confirmOrStyled(confirmMsg, lang === 'ko' ? '완전 초기화 후 재시작' : 'Full reset and restart', true).then(function (confirmed) {
    if (!confirmed) return;
    slog(lang === 'ko' ? '완전 초기화 요청 전송...' : 'Sending full reset request...', 's-log-info');
    var before = '';
    fetch(BACKEND + '/api/launcher-report').then(function (r) { return r.json(); })
      .then(function (d) { before = d.finished_at || ''; })
      .catch(function () {})
      .then(function () {
        return fetch(BACKEND + '/api/server-restart', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ operator: 'web_operator' })
        }).then(function (r) { return r.json(); });
      })
      .then(function (data) {
        if (!data.success) {
          slog((lang === 'ko' ? '재시작 요청 실패: ' : 'Restart request failed: ') + (data.error || ''), 's-log-err');
          alertOrStyled((lang === 'ko' ? '재시작하지 못했습니다: ' : 'Could not restart: ') + (data.error || '') + '\n\n'
            + (lang === 'ko' ? '바탕화면의 "한글 로봇 초기화"(Reset.bat)를 실행하세요.' : 'Run Reset.bat ("Hangeul Robot Reset" on the desktop).'));
          return;
        }
        slog(lang === 'ko' ? '재시작 중 — 돌아올 때까지 기다립니다' : 'Restarting — waiting for it to come back', 's-log-ok');
        waitForRestart(before, Date.now());
      })
      .catch(function () { waitForRestart(before, Date.now()); });
  });
}

function waitForRestart(before, startedAt) {
  var words = lang === 'ko'
    ? {started: '시작', already_running: '이미 떠 있음', no_device: '장치 없음', failed: '실패', port_busy: '포트 사용 중'}
    : {started: 'started', already_running: 'already running', no_device: 'no device', failed: 'failed', port_busy: 'port busy'};
  function done(report) {
    var lines = (report.runtimes || []).map(function (row) {
      return '· ' + (row.robots || []).join(', ') + ': ' + (words[row.state] || row.state)
        + (row.message ? ' — ' + row.message : '');
    });
    (report.problems || []).forEach(function (p) { lines.push('· ' + p); });
    if (!lines.length) lines.push(lang === 'ko' ? '· 등록된 로봇이 없습니다' : '· No robots registered');
    var head = report.ok
      ? (lang === 'ko' ? '다시 시작했습니다.' : 'Restarted.')
      : (lang === 'ko' ? '다시 시작했지만 확인할 것이 있습니다.' : 'Restarted, but some items need attention.');
    alertOrStyled(head + '\n\n' + lines.join('\n'));
    setTimeout(function () { location.reload(); }, 300);
  }
  function tick() {
    if (Date.now() - startedAt > 120000) {
      alertOrStyled(lang === 'ko'
        ? '2분이 지나도 돌아오지 않습니다. 바탕화면의 "한글 로봇 초기화"(Reset.bat)를 실행하세요.'
        : 'Not back after 2 minutes. Run Reset.bat ("Hangeul Robot Reset" on the desktop).');
      return;
    }
    fetch(BACKEND + '/api/launcher-report', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.finished_at && d.finished_at !== before && d.action === 'reset') done(d);
        else setTimeout(tick, 1500);
      })
      .catch(function () { setTimeout(tick, 1500); });
  }
  setTimeout(tick, 3000);
}

function sendVoiceCommand() {
  var cmd = document.getElementById('s-voice-input').value.trim();
  if (!cmd) {
    alertOrStyled(lang === 'ko' ? '명령어를 입력하세요.' : 'Please enter a command.');
    return;
  }

  var feedbackEl = document.getElementById('s-voice-feedback');
  feedbackEl.innerHTML = lang === 'ko' ? '🎙️ 전송 중...' : '🎙️ Sending...';
  feedbackEl.style.color = '#38bdf8';

  if (isDirectEmergencyStopPhrase(cmd)) {
    sendEmergencyStopVoiceCommand(cmd, feedbackEl);
    return;
  }

  var localMapping = findVoiceMappingMatch(cmd);
  if (localMapping) {
    legacyVoiceCommandFallback(cmd, feedbackEl);
    return;
  }

  var wakeCommand = parseDexterWakeCommand(cmd);
  var commandForApi = wakeCommand.allowed ? cmd : ('안녕 덱스터 ' + cmd + ' 끝');
  var commandForDisplay = wakeCommand.allowed ? wakeCommand.command : cmd;

  // 작업4 (2026-07-05): 서버 라우터(/api/voice-command)를 1차 경로로 사용.
  // 정지는 서버가 canonical 검출기로 우선 판정하고, 그 외에는 스킬 후보만 제안한다
  // (실행/대기열 추가는 아래 운영자 확인 클릭으로만). 서버 실패/후보 없음이면
  // 기존 substring 매칭 경로(legacyVoiceCommandFallback)로 폴백.
  fetch(BACKEND + '/api/voice-command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: commandForApi })
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d && d.success && (d.action === 'stop' || d.action === 'stop_suspected_negation_not_executed' || d.action === 'resume_blocked_requires_confirmation')) {
        applyVoiceControlResult(d, feedbackEl);
        return;
      }
      if (d && d.success && d.action === 'voice_ignored_requires_wake') {
        feedbackEl.innerHTML = '<strong>' + (d.detail || 'wake phrase required') + '</strong>';
        feedbackEl.style.color = '#94a3b8';
        return;
      }
      if (d && d.success && d.action === 'skill_proposal' && d.candidate_skill_ids && d.candidate_skill_ids.length) {
        renderVoiceSkillProposal(commandForDisplay, d, feedbackEl);
        return;
      }
      legacyVoiceCommandFallback(commandForDisplay, feedbackEl);
    })
    .catch(function() {
      legacyVoiceCommandFallback(commandForDisplay, feedbackEl);
    });
}

function displayLlmSource(source) {
  return String(source || '')
    .replace(/sllm_semantic/g, '음성 명령 추천')
    .replace(/sllm_retrieval/g, '음성 명령 검색')
    .replace(/sllm_field_catalog/g, 'Dexter 카탈로그')
    .replace(/sllm/gi, '음성 명령')
    .replace(/_/g, ' ');
}

function renderVoiceSkillProposal(cmd, d, feedbackEl) {
  var header = lang === 'ko'
    ? '🎙️ 동작 후보 제안 (' + displayLlmSource(d.source) + ') — 실행은 운영자 확인 필요:'
    : '🎙️ Action candidates proposed (' + displayLlmSource(d.source) + ') — operator confirmation required:';
  feedbackEl.innerHTML = '';
  var headerEl = document.createElement('strong');
  headerEl.textContent = header;
  feedbackEl.appendChild(headerEl);
  feedbackEl.style.color = '#cbd5e1';
  var actionableCount = 0;
  d.candidate_skill_ids.forEach(function(sid) {
    var mv = state.catalog.find(function(x) { return x.skill_id === sid; });
    var btn = document.createElement('button');
    btn.className = 'btn btn-secondary';
    btn.style.cssText = 'display:block;margin:4px 0;font-size:0.8rem;';
    if (mv) {
      actionableCount += 1;
      btn.textContent = '➕ ' + (lang === 'ko' ? mv.display_name_kr : mv.display_name_en) + ' (' + sid + ')';
      btn.onclick = function() {
        addToQueue(mv);
        slog((lang === 'ko' ? '음성 제안 → 운영자 확인 → 대기열 추가: ' : 'Voice proposal → operator confirmed → queued: ') + sid, 's-log-ok');
      };
    } else {
      btn.textContent = '⛔ ' + sid + (lang === 'ko' ? ' (카탈로그 없음 — 추가 불가)' : ' (not in catalog — cannot queue)');
      btn.disabled = true;
    }
    feedbackEl.appendChild(btn);
  });
  if (actionableCount === 0) {
    var mapperHint = document.createElement('div');
    mapperHint.style.cssText = 'margin-top:6px;font-size:0.8rem;color:#facc15;';
    mapperHint.textContent = lang === 'ko'
      ? '인식은 되었지만 추가 가능한 후보가 없습니다. 아래에서 이 음성을 저장 순서/동작과 매칭하세요.'
      : 'Recognized, but no usable candidate was found. Map this voice to a saved sequence or action below.';
    feedbackEl.appendChild(mapperHint);
    openVoiceMapperForPhrase(cmd);
    slog(lang === 'ko' ? '명령 후보 사용 불가: 음성 매칭 등록으로 전환 - ' + cmd : 'Command candidate unusable: opened voice mapper for ' + cmd, 's-log-info');
  }
}

function openVoiceMapperForPhrase(phrase) {
  var form = document.getElementById('s-voice-mapper-form');
  var phraseEl = document.getElementById('s-mapped-phrase-text');
  if (!form || !phraseEl) return;
  form.style.display = 'flex';
  phraseEl.textContent = phrase;
  populateActionSelect();
}

function normalizeVoiceMatchText(value) {
  var text = String(value || '')
    .toLowerCase()
    .replace(/[^0-9a-z가-힣]+/g, '');
  return text
    .replace(/테스트(둘|이|투|two)/g, '테스트2')
    .replace(/테스트(셋|삼|쓰리|three)/g, '테스트3')
    .replace(/test(two)/g, 'test2')
    .replace(/test(three)/g, 'test3');
}

function voicePhraseAliases(phrase) {
  var normalized = normalizeVoiceMatchText(phrase);
  var aliases = normalized ? [normalized] : [];
  if (normalized && normalized.length % 2 === 0) {
    var half = normalized.slice(0, normalized.length / 2);
    if (half && half === normalized.slice(normalized.length / 2)) {
      aliases.push(half);
    }
  }
  return aliases.filter(function(alias, idx, arr) {
    return alias && arr.indexOf(alias) === idx;
  });
}

function findVoiceMappingMatch(cmd) {
  var cmdNorm = normalizeVoiceMatchText(cmd);
  if (!cmdNorm) return null;
  var candidates = [];
  state.voiceMappings.forEach(function(m, idx) {
    if (m.action === 'estop') return;
    voicePhraseAliases(m.phrase).forEach(function(alias) {
      var exact = cmdNorm === alias;
      var safePartial = alias.length >= 4 && cmdNorm.indexOf(alias) !== -1;
      if (exact || safePartial) {
        candidates.push({ mapping: m, alias: alias, idx: idx });
      }
    });
  });
  if (!candidates.length) return null;
  candidates.sort(function(a, b) {
    return b.alias.length - a.alias.length || a.idx - b.idx;
  });
  if (candidates.length > 1 && candidates[0].alias.length === candidates[1].alias.length && candidates[0].mapping.action !== candidates[1].mapping.action) {
    return { ambiguous: true, aliases: candidates.map(function(c) { return c.alias; }) };
  }
  return candidates[0].mapping;
}

function legacyVoiceCommandFallback(cmd, feedbackEl) {
  // 1. Client-side mapping match check first
  var matched = findVoiceMappingMatch(cmd);

  if (matched && matched.ambiguous) {
    feedbackEl.innerHTML = lang === 'ko' ? '⚠️ 음성 명령이 여러 매핑과 겹칩니다. 더 길게 말해 주세요.' : '⚠️ Voice command matches multiple mappings. Please say the full phrase.';
    feedbackEl.style.color = '#facc15';
    slog(lang === 'ko' ? '음성 매칭 보류: 중복 후보 ' + cmd : 'Voice match held: ambiguous candidates for ' + cmd, 's-log-info');
    return;
  }
  
  if (matched) {
    if (matched.action === 'estop') {
      feedbackEl.innerHTML = lang === 'ko'
        ? '⚠️ 음성 매칭의 긴급 정지는 비활성화되어 있습니다. 긴급 정지는 화면 버튼을 사용하세요.'
        : '⚠️ Voice-mapped E-Stop is disabled. Use the on-screen E-Stop button.';
      feedbackEl.style.color = '#facc15';
      slog(lang === 'ko' ? '음성 긴급 정지 매핑 차단: ' + matched.phrase : 'Voice E-Stop mapping blocked: ' + matched.phrase, 's-log-info');
    } else if (matched.action === 'resume') {
      feedbackEl.innerHTML = '<strong>' + (lang === 'ko' ? '🔊 매칭 동작 감지: ' : '🔊 Matched command: ') + matched.label + '</strong>';
      feedbackEl.style.color = '#4ade80';
      if (state.estopActive) {
        triggerEStop();
      }
      slog((lang === 'ko' ? '음성 매칭 작동: ' : 'Voice match triggered: ') + matched.phrase + ' ➔ ' + matched.label, 's-log-ok');
    } else if (matched.action === 'default_pose') {
      var defPose = state.catalog.find(function(x) { 
        return x.skill_id === 'pose_safety' || x.display_name_kr.indexOf('기본') !== -1 || x.display_name_kr.indexOf('안전') !== -1; 
      });
      if (defPose) {
        addToQueue(defPose);
        feedbackEl.innerHTML = '<strong>' + (lang === 'ko' ? '🔊 매칭 동작 감지 (대기열 추가): ' : '🔊 Matched command (Added to queue): ') + (lang === 'ko' ? defPose.display_name_kr : defPose.display_name_en) + '</strong>';
        feedbackEl.style.color = '#4ade80';
        slog((lang === 'ko' ? '음성 매칭 작동: ' : 'Voice match triggered: ') + matched.phrase + ' ➔ ' + (lang === 'ko' ? defPose.display_name_kr : defPose.display_name_en), 's-log-ok');
      } else {
        feedbackEl.innerHTML = lang === 'ko' ? '⚠️ 기본 안전 자세 카드를 동작 목록에서 찾을 수 없습니다.' : '⚠️ Safety pose card not found in catalog.';
        feedbackEl.style.color = '#f87171';
      }
    } else if (matched.action.indexOf('sequence:') === 0) {
      var seqName = matched.action.slice('sequence:'.length);
      var skillIds = state.savedSequences[seqName];
      if (Array.isArray(skillIds)) {
        appendSequenceRecipe(seqName, skillIds);
        feedbackEl.innerHTML = '<strong>' + (lang === 'ko' ? '🔊 매칭 순서 감지 (대기열 추가): ' : '🔊 Matched sequence (Added to queue): ') + matched.label + '</strong>';
        feedbackEl.style.color = '#4ade80';
        slog((lang === 'ko' ? '음성 순서 매칭 작동: ' : 'Voice sequence match triggered: ') + matched.phrase + ' ➔ ' + matched.label, 's-log-ok');
      } else {
        feedbackEl.innerHTML = lang === 'ko' ? '⚠️ 연결된 저장 순서가 존재하지 않습니다.' : '⚠️ Mapped saved sequence does not exist.';
        feedbackEl.style.color = '#f87171';
      }
    } else {
      var mv = state.catalog.find(function(x) { return x.skill_id === matched.action; });
      if (mv) {
        addToQueue(mv);
        feedbackEl.innerHTML = '<strong>' + (lang === 'ko' ? '🔊 매칭 동작 감지 (대기열 추가): ' : '🔊 Matched command (Added to queue): ') + (lang === 'ko' ? mv.display_name_kr : mv.display_name_en) + '</strong>';
        feedbackEl.style.color = '#4ade80';
        slog((lang === 'ko' ? '음성 매칭 작동: ' : 'Voice match triggered: ') + matched.phrase + ' ➔ ' + (lang === 'ko' ? mv.display_name_kr : mv.display_name_en), 's-log-ok');
      } else {
        feedbackEl.innerHTML = lang === 'ko' ? '⚠️ 연결된 동작 카드가 존재하지 않습니다.' : '⚠️ Mapped movement card does not exist.';
        feedbackEl.style.color = '#f87171';
      }
    }
    return;
  }
  
  // 2. Fallback to API check
  fetch(BACKEND + '/api/voice-control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd })
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.success) {
        feedbackEl.innerHTML = '<strong>' + d.detail + '</strong>';
        if (d.action === 'stop' && isDirectEmergencyStopPhrase(cmd)) {
          feedbackEl.style.color = '#f87171';
          if (!state.estopActive) {
            triggerEStop();
          }
        } else if (d.action === 'stop') {
          feedbackEl.style.color = '#facc15';
          feedbackEl.innerHTML = lang === 'ko'
            ? '⚠️ 이 명령은 긴급 정지로 실행하지 않았습니다. 긴급 정지는 화면 버튼을 사용하세요.'
            : '⚠️ This command was not executed as E-Stop. Use the on-screen E-Stop button.';
          openVoiceMapperForPhrase(cmd);
        } else if (d.action === 'resume') {
          feedbackEl.style.color = '#4ade80';
          if (state.estopActive) {
            triggerEStop();
          }
        } else {
          // Open mapper panel for unmapped phrases
          feedbackEl.style.color = '#cbd5e1';
          openVoiceMapperForPhrase(cmd);
          
          if (d.candidate && d.candidate.command_class) {
            feedbackEl.innerHTML += '<br/><span style="font-size:0.75rem; color:#94a3b8;">' + 
              (lang === 'ko' ? '분류: ' : 'Class: ') + d.candidate.command_class + 
              ' | ' + (lang === 'ko' ? '이유: ' : 'Reason: ') + d.candidate.reason + '</span>';
          }
          slog(lang === 'ko' ? 'ℹ️ 미등록 음성 감지: 매핑 설정을 엽니다.' : 'ℹ️ Unregistered voice command: Opening mapper form.', 's-log-info');
        }
      } else {
        feedbackEl.innerHTML = '⚠️ 전송 실패: ' + d.error;
        feedbackEl.style.color = '#f87171';
      }
    })
    .catch(function() {
      feedbackEl.innerHTML = '⚠️ 네트워크 오류';
      feedbackEl.style.color = '#f87171';
    });
}

function runVisionDetection() {
  startVisionCamera();
}

function startVisionCamera() {
  var overlay = document.getElementById('s-vision-overlay');
  var placeholder = document.getElementById('s-camera-placeholder');
  if (overlay) overlay.innerHTML = '';
  if (placeholder) {
    placeholder.style.display = 'none';
    placeholder.textContent = lang === 'ko' ? '📷 실행 중' : '📷 Running';
  }
  startWebcam();
}

function stopVisionCamera() {
  var overlay = document.getElementById('s-vision-overlay');
  var placeholder = document.getElementById('s-camera-placeholder');
  var registerCard = document.getElementById('s-vision-register-card');
  if (overlay) overlay.innerHTML = '';
  if (registerCard) registerCard.style.display = 'none';
  _detectedCandidate = null;
  stopWebcam();
  if (placeholder) {
    placeholder.style.display = 'block';
    placeholder.textContent = lang === 'ko' ? '📷 카메라 대기 중' : '📷 Camera idle';
  }
  slog(lang === 'ko' ? '정지: 카메라 대기 상태로 전환' : 'Stopped: camera idle mode', 's-log-ok');
}

function drawCapturedVisionCandidate(candidate) {
  var overlay = document.getElementById('s-vision-overlay');
  var screen = document.getElementById('s-camera-screen');
  if (!overlay || !screen || !candidate || !candidate.bounding_box) return;
  var box = candidate.bounding_box;
  var w = screen.clientWidth || 640;
  var h = screen.clientHeight || 480;
  var scaleX = w / 640;
  var scaleY = h / 480;
  var left = box.x * scaleX;
  var top = box.y * scaleY;
  var boxW = box.w * scaleX;
  var boxH = box.h * scaleY;
  var color = '#10b981';
  overlay.innerHTML = '<div class="s-vision-box" style="border-color: ' + color + '; box-shadow: 0 0 10px ' + color + '66; left: ' + left + 'px; top: ' + top + 'px; width: ' + boxW + 'px; height: ' + boxH + 'px;">' +
    '<span class="s-vision-label" style="background: ' + color + ';">' + candidate.label + '</span></div>';
}

function captureVisionTrainingFrame() {
  var labelInput = document.getElementById('s-vision-capture-label');
  var label = labelInput ? labelInput.value.trim() : '';
  var registerCard = document.getElementById('s-vision-register-card');
  var placeholder = document.getElementById('s-camera-placeholder');
  if (!label) {
    label = lang === 'ko' ? '촬영 대상' : 'Captured target';
  }
  startVisionCamera();
  if (placeholder) {
    placeholder.textContent = lang === 'ko' ? '📷 촬영 저장 중...' : '📷 Saving capture...';
  }
  fetch(BACKEND + '/api/vision-training-capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: label })
  })
    .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
    .then(function(d) {
      if (!d.success) {
        throw new Error(d.error || 'capture_failed');
      }
      var capture = d.capture;
      // 작업6 (2026-07-05): 서버가 날조 candidate(중앙 bbox, confidence 1.0)를 더 이상
      // 반환하지 않는다 — 실촬영 이미지 + 라벨 + sha256만 사용하고 bbox 오버레이는
      // 실제 검출기가 붙기 전까지 그리지 않는다.
      _detectedCandidate = {
        zone: lang === 'ko' ? '실촬영 (bbox 미검출)' : 'captured (no bbox)',
        label: capture.label,
        image_path: capture.image_path,
        metadata_path: capture.metadata_path,
        sha256: capture.sha256
      };
      if (registerCard) {
        registerCard.style.display = 'flex';
        document.getElementById('s-vision-target-name').value = capture.label;
      }
      slog(lang === 'ko' ? '비전 학습 이미지 저장: ' + capture.image_path : 'Vision training image saved: ' + capture.image_path, 's-log-ok');
    })
    .catch(function(err) {
      if (registerCard) registerCard.style.display = 'none';
      _detectedCandidate = null;
      slog((lang === 'ko' ? '비전 촬영 실패: ' : 'Vision capture failed: ') + err.message, 's-log-err');
    });
}

// ─── STEP 1 탭 제어 ───────────────────────────────────────────────
function switchStep1Tab(tabName) {
  var btnMovements = document.getElementById('tab-movements');
  var btnTargets = document.getElementById('tab-targets');
  var gridMovements = document.getElementById('s-card-grid');
  var gridTargets = document.getElementById('s-target-grid');
  
  if (!btnMovements || !btnTargets || !gridMovements || !gridTargets) return;
  
  if (tabName === 'movements') {
    btnMovements.classList.add('active');
    btnTargets.classList.remove('active');
    gridMovements.style.display = 'grid';
    gridTargets.style.display = 'none';
  } else {
    btnMovements.classList.remove('active');
    btnTargets.classList.add('active');
    gridMovements.style.display = 'none';
    gridTargets.style.display = 'grid';
    renderTargets();
  }
}

// ─── 대상 고르기 렌더링 ──────────────────────────────────────────────
function renderTargets() {
  var grid = document.getElementById('s-target-grid');
  if (!grid) return;
  grid.textContent = '';
  
  if (state.targets.length === 0) {
    var empty = document.createElement('div');
    empty.style.color = '#475569';
    empty.style.fontSize = '0.85rem';
    empty.style.padding = '20px';
    empty.id = 'lbl-no-targets';
    empty.textContent = lang === 'ko' ? '등록된 대상이 없습니다. 아래 \'카메라 영상\' 패널에서 대상을 등록해 주세요.' : 'No registered targets. Please register one in the Camera panel below.';
    grid.appendChild(empty);
    return;
  }
  
  state.targets.forEach(function(tgt) {
    var card = document.createElement('div');
    card.className = 's-card';
    card.style.setProperty('--card-color', '#10b981');
    card.style.borderColor = 'transparent';
    
    var badge = document.createElement('span');
    badge.className = 's-card-badge';
    badge.textContent = lang === 'ko' ? '대상 물체' : 'Target Object';
    card.appendChild(badge);
    
    var icon = document.createElement('div');
    icon.className = 's-card-icon';
    icon.textContent = '🎯';
    card.appendChild(icon);
    
    var name = document.createElement('div');
    name.className = 's-card-name';
    name.textContent = tgt.name;
    card.appendChild(name);
    
    var desc = document.createElement('div');
    desc.className = 's-card-desc';
    desc.textContent = lang === 'ko' ? '위치: ' + tgt.zone + ' (' + tgt.x + ', ' + tgt.y + ')' : 'Pos: ' + tgt.zone + ' (' + tgt.x + ', ' + tgt.y + ')';
    card.appendChild(desc);
    
    card.addEventListener('click', function() {
      addToQueue({
        skill_id: tgt.id,
        display_name_kr: '🎯 ' + tgt.name + ' (' + tgt.zone + ')',
        display_name_en: '🎯 ' + tgt.name + ' (' + tgt.zone + ')',
        icon: '🎯',
        color: '#10b981'
      });
      card.style.borderColor = '#10b981';
      setTimeout(function() { card.style.borderColor = 'transparent'; }, 300);
    });
    
    grid.appendChild(card);
  });
}

function getVoiceActionIcon(action) {
  if (action === 'estop') return '🚨';
  if (action === 'resume') return '🟢';
  if (action === 'default_pose') return '🏠';
  if (action && action.indexOf('sequence:') === 0) return '📂';
  var mv = state.catalog.find(function(x) { return x.skill_id === action; });
  return mv && mv.icon ? mv.icon : '➔';
}

function stripLeadingEmojiLabel(label, icon) {
  if (!label) return '';
  if (icon && label.indexOf(icon) === 0) {
    return label.slice(icon.length).trim();
  }
  return label;
}

function setVoiceMappingIcon(idx, icon) {
  var item = state.voiceMappings[idx];
  if (!item) return;
  item.icon = icon;
  state.voiceIconEditIndex = null;
  persistVoiceMappings();
  renderVoiceMappings();
  slog(lang === 'ko' ? '음성 매핑 아이콘 수정: ' + item.phrase + ' ' + icon : 'Voice mapping icon updated: ' + item.phrase + ' ' + icon, 's-log-ok');
}

// ─── 음성 매핑 그리드 렌더링 ──────────────────────────────────────────
function getVoiceActionLabel(action, storedLabel) {
  if (action === 'estop') {
    return lang === 'ko' ? '🚨 긴급 정지 (E-STOP)' : '🚨 Emergency Stop (E-STOP)';
  }
  if (action === 'default_pose') {
    return lang === 'ko' ? '기본 안전 자세' : 'Default Safety Pose';
  }
  if (action.indexOf('sequence:') === 0) {
    var seqName = action.substring('sequence:'.length);
    return seqName;
  }
  var mv = state.catalog.find(function(item) { return item.skill_id === action; });
  if (mv) {
    return lang === 'ko' ? mv.display_name_kr : mv.display_name_en;
  }
  return storedLabel || action;
}

function renderVoiceMappings() {
  var grid = document.getElementById('s-voice-mapping-grid');
  if (!grid) return;
  grid.innerHTML = '';

  if (state.voiceMappings.length === 0) {
    var empty = document.createElement('div');
    empty.className = 's-voice-empty';
    empty.textContent = lang === 'ko'
      ? '등록된 실제 음성 명령이 없습니다. 위에서 3회 이상 녹음 후 매칭 등록하세요.'
      : 'No real voice commands registered. Record at least 3 samples above.';
    grid.appendChild(empty);
    return;
  }
  
  state.voiceMappings.forEach(function(m, idx) {
    var card = document.createElement('div');
    card.className = 's-voice-map-card';
    if (m.action === 'estop') {
      card.classList.add('estop-mapped');
    }
    
    var badge = document.createElement('span');
    badge.className = 's-voice-badge';
    card.appendChild(badge);
    
    var phrase = document.createElement('span');
    phrase.className = 's-voice-phrase';
    var displayPhrase = m.phrase;
    if (lang === 'en') {
      if (displayPhrase === '정지') displayPhrase = 'Stop';
      else if (displayPhrase === '처음으로') displayPhrase = 'Home';
      else if (displayPhrase === '오른쪽 90도') displayPhrase = 'Right 90';
      else if (displayPhrase === '왼쪽 90도') displayPhrase = 'Left 90';
    }
    phrase.textContent = displayPhrase;
    card.appendChild(phrase);
    
    var action = document.createElement('span');
    action.className = 's-voice-action';
    var icon = m.icon || getVoiceActionIcon(m.action);
    var displayLabel = getVoiceActionLabel(m.action, m.label);
    if (icon && (icon.indexOf('data:image/') === 0 || icon.indexOf('/') === 0 || icon.indexOf('http') === 0)) {
      var img = document.createElement('img');
      img.src = icon;
      img.style.width = '16px';
      img.style.height = '16px';
      img.style.objectFit = 'contain';
      img.style.verticalAlign = 'middle';
      img.style.marginRight = '4px';
      action.appendChild(img);
      action.appendChild(document.createTextNode(stripLeadingEmojiLabel(displayLabel, icon)));
    } else {
      action.textContent = icon + ' ' + stripLeadingEmojiLabel(displayLabel, icon);
    }
    card.appendChild(action);

    var editBtn = document.createElement('button');
    editBtn.className = 's-voice-edit-btn';
    editBtn.type = 'button';
    editBtn.textContent = '✎';
    editBtn.title = lang === 'ko' ? '아이콘 수정' : 'Edit icon';
    editBtn.addEventListener('pointerdown', function(e) {
      e.stopPropagation();
    });
    editBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      state.voiceIconEditIndex = state.voiceIconEditIndex === idx ? null : idx;
      renderVoiceMappings();
    });
    card.appendChild(editBtn);

    var delBtn = document.createElement('button');
    delBtn.className = 's-voice-delete-btn';
    delBtn.type = 'button';
    delBtn.textContent = '×';
    delBtn.title = lang === 'ko' ? '음성 명령 삭제' : 'Delete voice command';
    delBtn.addEventListener('pointerdown', function(e) {
      e.stopPropagation();
    });
    delBtn.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      deleteVoiceMapping(idx);
    });
    card.appendChild(delBtn);

    if (state.voiceIconEditIndex === idx) {
      var palette = document.createElement('div');
      palette.className = 's-voice-icon-palette';
      ['🚨', '🏠', '📂', '▶', '✊', '🤚', '⬆️', '⬇️', '↪️', '🎯'].forEach(function(choice) {
        var iconBtn = document.createElement('button');
        iconBtn.type = 'button';
        iconBtn.className = 's-voice-icon-choice';
        iconBtn.textContent = choice;
        iconBtn.addEventListener('click', function(e) {
          e.preventDefault();
          e.stopPropagation();
          setVoiceMappingIcon(idx, choice);
        });
        palette.appendChild(iconBtn);
      });
      card.appendChild(palette);
    }
    
    grid.appendChild(card);
  });
}

function deleteVoiceMapping(idx) {
  var item = state.voiceMappings[idx];
  if (!item) return;
  state.voiceMappings.splice(idx, 1);
  persistVoiceMappings();
  renderVoiceMappings();
  slog(lang === 'ko' ? '음성 매핑 삭제: ' + item.phrase : 'Voice mapping deleted: ' + item.phrase, 's-log-ok');
}

// ─── 음성 매핑 드롭다운 목록 채우기 ─────────────────────────────────────
function populateActionSelect() {
  var select = document.getElementById('s-mapped-action-select');
  if (!select) return;
  
  select.innerHTML = '';
  
  var optDefault = document.createElement('option');
  optDefault.value = 'default_pose';
  optDefault.textContent = lang === 'ko' ? '기본 안전 자세' : 'Default Safety Pose';
  select.appendChild(optDefault);
  
  state.catalog.forEach(function(mv) {
    var opt = document.createElement('option');
    opt.value = mv.skill_id;
    opt.textContent = lang === 'ko' ? mv.display_name_kr : mv.display_name_en;
    select.appendChild(opt);
  });

  Object.keys(state.savedSequences || {}).forEach(function(seqName) {
    var skillIds = state.savedSequences[seqName] || [];
    var icon = state.sequenceIcons[seqName] || '📂';
    var opt = document.createElement('option');
    opt.value = 'sequence:' + seqName;
    opt.textContent = lang === 'ko'
      ? icon + ' ' + seqName + ' (순서 불러오기, ' + skillIds.length + '개)'
      : icon + ' ' + seqName + ' (Saved sequence, ' + skillIds.length + ' steps)';
    select.appendChild(opt);
  });
}

// ─── 신규 음성 매핑 저장 ─────────────────────────────────────────────
function saveVoiceMapping() {
  var phrase = document.getElementById('s-mapped-phrase-text').textContent;
  var actionSelect = document.getElementById('s-mapped-action-select');
  var action = actionSelect.value;
  var label = actionSelect.options[actionSelect.selectedIndex].text;
  var icon = getVoiceActionIcon(action);
  
  if (!phrase) return;
  
  var existingIdx = state.voiceMappings.findIndex(function(m) { return m.phrase === phrase; });
  if (existingIdx !== -1) {
    state.voiceMappings[existingIdx].action = action;
    state.voiceMappings[existingIdx].label = label;
    state.voiceMappings[existingIdx].icon = icon;
  } else {
    state.voiceMappings.push({ phrase: phrase, action: action, label: label, icon: icon });
  }
  persistVoiceMappings();
  
  document.getElementById('s-voice-mapper-form').style.display = 'none';
  renderVoiceMappings();
  
  slog(lang === 'ko' ? '음성 매핑 등록 완료: ' + phrase + ' ➔ ' + label : 'Voice mapping saved: ' + phrase + ' -> ' + label, 's-log-ok');
}

// ─── 카메라 감지 대상 등록 ────────────────────────────────────────────
var _detectedCandidate = null;
function registerDetectedTarget() {
  var nameInput = document.getElementById('s-vision-target-name');
  var customName = nameInput.value.trim();
  
  if (!_detectedCandidate) {
    alertOrStyled(lang === 'ko' ? '먼저 카메라로 대상을 인식시켜 주세요.' : 'Please detect a target via camera first.');
    return;
  }
  
  var finalName = customName || _detectedCandidate.label;
  
  var newTarget = {
    id: 'target_' + Date.now(),
    name: finalName,
    x: _detectedCandidate.x,
    y: _detectedCandidate.y,
    zone: _detectedCandidate.zone,
    image_path: _detectedCandidate.image_path || '',
    metadata_path: _detectedCandidate.metadata_path || '',
    sha256: _detectedCandidate.sha256 || ''
  };
  
  state.targets.push(newTarget);
  
  document.getElementById('s-vision-register-card').style.display = 'none';
  nameInput.value = '';
  
  renderTargets();
  
  slog(lang === 'ko' ? '대상 등록 완료: ' + finalName + ' (' + _detectedCandidate.zone + ')' : 'Target registered: ' + finalName + ' (' + _detectedCandidate.zone + ')', 's-log-ok');
  
  switchStep1Tab('targets');
}

var _recognition = null;
// 2026-07-04 (사용자 지시): "녹음" 버튼(s-voice-input 옆)이 켜져 있으면 음성 인식이
// 지원된다는 걸 확인한 뒤, 같은 상태를 상단에서도 바로 보이게 별도 버튼을 추가한다.
// 켜짐=초록+O, 꺼짐=빨강. btn-voice-record와 항상 같은 상태를 반영한다(동일한
function updateTopVoiceCommandBtn(active) {
  var btn = document.getElementById('btn-voice-command-top');
  if (!btn) return;
  if (_recognition) {
    btn.style.background = '#16a34a';
    btn.style.borderColor = '#15803d';
    btn.innerHTML = '🟢 ' + (lang === 'ko' ? '음성 명령' : 'Voice Command') + ' O';
  } else if (active) {
    btn.style.background = '#16a34a';
    btn.style.borderColor = '#15803d';
    btn.innerHTML = '🟢 ' + (lang === 'ko' ? '정지 청취' : 'Stop Armed') + ' O';
  } else {
    btn.style.background = '#dc2626';
    btn.style.borderColor = '#b91c1c';
    btn.innerHTML = '🔴 ' + (lang === 'ko' ? '음성 명령' : 'Voice Command');
  }
}

function startSpeechRecognition() {
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    toggleServerVoiceMonitor();
    return;
  }
  
  var btn = document.getElementById('btn-voice-record');
  var feedbackEl = document.getElementById('s-voice-feedback');
  
  if (_recognition) {
    _recognition.stop();
    return;
  }
  
  _recognition = new SpeechRecognition();
  _recognition.lang = lang === 'ko' ? 'ko-KR' : 'en-US';
  _recognition.interimResults = false;
  _recognition.maxAlternatives = 1;
  
  _recognition.onstart = function() {
    btn.style.background = '#dc2626';
    btn.style.borderColor = '#b91c1c';
    btn.innerHTML = '🔴 ' + (lang === 'ko' ? '듣는 중...' : 'Listening...');
    updateTopVoiceCommandBtn(true);
    updateLlmVoiceModeStatus();
    feedbackEl.innerHTML = lang === 'ko' ? '🎙️ 목소리를 듣고 있습니다... ("정지" 또는 "다시시작"이라고 말해보세요)' : '🎙️ Listening to your voice... (Try saying "Stop" or "Resume")';
    feedbackEl.style.color = '#e2e8f0';
  };
  
  _recognition.onresult = function(event) {
    var text = event.results[0][0].transcript;
    document.getElementById('s-voice-input').value = text;
    feedbackEl.innerHTML = (lang === 'ko' ? '📝 인식된 단어: ' : '📝 Recognized: ') + '<strong>' + text + '</strong>';
    feedbackEl.style.color = '#4ade80';
    
    sendVoiceCommand();
  };
  
  _recognition.onerror = function(event) {
    feedbackEl.innerHTML = '⚠️ 음성 인식 오류: ' + event.error;
    feedbackEl.style.color = '#f87171';
    slog(lang === 'ko' ? '브라우저 음성 인식 실패. 서버 측 음성 활성화로 전환합니다.' : 'Browser speech failed. Switching to server voice activation.', 's-log-info');
    toggleServerVoiceMonitor();
  };
  
  _recognition.onend = function() {
    btn.style.background = '#475569';
    btn.style.borderColor = '#334155';
    btn.innerHTML = '🎙 ' + (lang === 'ko' ? '녹음' : 'Record');
    updateTopVoiceCommandBtn(!!state.serverVoiceTimer);
    updateLlmVoiceModeStatus();
    _recognition = null;
  };
  
  _recognition.start();
}

function startLlmServerVoiceRecognition() {
  var btn = document.getElementById('btn-voice-record');
  var input = document.getElementById('s-voice-input');
  var feedbackEl = document.getElementById('s-voice-feedback');
  if (!feedbackEl) return;
  if (!VOICE_RECOGNITION_ENABLED) {
    feedbackEl.innerHTML = lang === 'ko'
      ? '지금은 텍스트 입력만 사용합니다. 음성은 학습 데이터 등록 후 별도 검증이 필요합니다.'
      : 'Typed input only for now. Voice requires training samples and separate verification.';
    feedbackEl.style.color = '#fbbf24';
    updateLlmVoiceModeStatus();
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.style.background = '#dc2626';
    btn.style.borderColor = '#b91c1c';
    btn.innerHTML = lang === 'ko' ? '🔴 듣는 중...' : '🔴 Listening...';
  }
  feedbackEl.innerHTML = lang === 'ko'
    ? '🎙️ 서버 마이크로 음성을 듣고 있습니다...'
    : '🎙️ Listening through the server microphone...';
  feedbackEl.style.color = '#e2e8f0';

  var listenUrl = IS_VOICE_MATCHING_PORT
    ? '/voice-learning-api/recognize?seconds=2'
    : (BACKEND + '/api/server-voice-listen?seconds=2');
  fetch(listenUrl, { method: 'POST' })
    .then(function(r) {
      return r.json().then(function(d) {
        d._status = r.status;
        return d;
      });
    })
    .then(function(data) {
      var voice = data.voice || {};
      var text = String(voice.text || '').trim();
      if (data.action === 'stop') {
        if (input) input.value = text || '정지';
        applyVoiceControlResult({ action: 'stop', detail: text || 'stop' }, feedbackEl);
        return;
      }
      if (!data.success || !text) {
        var err = data.error || voice.error || 'empty_transcript';
        var source = voice.stt_source ? (' / ' + voice.stt_source) : '';
        var audio = voice.audio || {};
        var level = (audio.rms_dbfs !== undefined)
          ? (' / RMS ' + audio.rms_dbfs + ' dBFS, Peak ' + audio.peak_dbfs + ' dBFS')
          : '';
        var msg = err;
        if (err === 'low_microphone_signal') {
          msg = lang === 'ko' ? '마이크 입력이 너무 낮습니다. Britz 마이크에 더 가까이 말하거나 캡처 볼륨/장치를 확인하세요.' : 'Microphone input is too low. Move closer to the Britz mic or check capture gain/device.';
        } else if (err === 'filtered_silence_hallucination') {
          msg = lang === 'ko' ? '무음/잡음에서 나온 STT 환각 문장을 버렸습니다.' : 'Filtered an STT hallucination from silence/noise.';
        }
        feedbackEl.innerHTML = (lang === 'ko' ? '⚠️ 음성 인식 실패: ' : '⚠️ Voice recognition failed: ') + msg + source + level;
        feedbackEl.style.color = '#f87171';
        return;
      }
      if (input) input.value = text;
      feedbackEl.innerHTML = (lang === 'ko' ? '📝 인식된 명령: ' : '📝 Recognized command: ') + '<strong>' + text + '</strong>';
      feedbackEl.style.color = '#4ade80';
      sendVoiceCommand();
    })
    .catch(function(err) {
      feedbackEl.innerHTML = (lang === 'ko' ? '⚠️ 서버 마이크 연결 실패: ' : '⚠️ Server microphone failed: ') + err.message;
      feedbackEl.style.color = '#f87171';
    })
    .finally(function() {
      if (btn) {
        btn.disabled = false;
        btn.style.background = '#1e3a8a';
        btn.style.borderColor = '#1d4ed8';
        btn.innerHTML = lang === 'ko' ? '🎙 녹음' : '🎙 Record';
      }
      updateLlmVoiceModeStatus();
    });
}

function toggleServerVoiceMonitor() {
  if (!VOICE_RECOGNITION_ENABLED) {
    slog(lang === 'ko' ? '지금은 텍스트 입력만 사용합니다. 음성은 학습 후 검증이 필요합니다.' : 'Typed input only for now. Voice requires training and verification.', 's-log-info');
    updateLlmVoiceModeStatus();
    return;
  }
  if (state.serverVoiceTimer) {
    slog(
      lang === 'ko'
        ? '음성 긴급정지 청취는 안전을 위해 계속 유지됩니다.'
        : 'Voice emergency-stop listening stays on for safety.',
      's-log-info'
    );
  } else {
    startServerVoiceMonitor();
  }
}

function startServerVoiceMonitor() {
  var feedbackEl = document.getElementById('s-voice-feedback');
  if (!VOICE_RECOGNITION_ENABLED) {
    setVoiceStatus(false, lang === 'ko' ? '음성 사용 안 함' : 'Voice disabled');
    updateTopVoiceCommandBtn(false);
    updateLlmVoiceModeStatus();
    if (feedbackEl) {
      feedbackEl.innerHTML = lang === 'ko'
        ? '지금은 텍스트 입력만 사용합니다. 긴급 정지는 화면 버튼을 사용하세요.'
        : 'Typed input only for now. Use the on-screen emergency stop button.';
      feedbackEl.style.color = '#fbbf24';
    }
    return;
  }
  if (state.serverVoiceTimer) return;
  setVoiceStatus(true, lang === 'ko' ? '음성 정지 대기' : 'Voice stop armed');
  updateTopVoiceCommandBtn(true);
  updateLlmVoiceModeStatus();
  if (feedbackEl) {
    feedbackEl.innerHTML = lang === 'ko'
      ? '🎙️ 음성 긴급정지 대기 중입니다. 일반 음성 명령을 켜지 않아도 "정지", "멈춰", "스톱"은 감지합니다.'
      : '🎙️ Waiting for emergency stop voice through the server microphone.';
    feedbackEl.style.color = '#e2e8f0';
  }

  // 2026-07-04 수정: 서버가 잠깐 꺼져 있으면(또는 네트워크 문제) 이 루프가 실패마다
  // 빨간 오류 줄을 반복 출력하며 로그를 스팸으로 채우는 문제가 실사용 중 발견됐다.
  // "서버를 계속 켜둘지 필요할 때만 켤지"와는 무관하게, 연결이 끊긴 "상태"는 상태
  // 변화 시 한 번만 알리고, 끊긴 동안은 재시도 간격을 늘려 서버에도 부담을 덜 준다.
  var consecutiveFailures = 0;
  var MAX_BACKOFF_MS = 8000;
  // 긴급 정지 대기 경로는 4초 chunk를 기다리면 너무 늦다. 1초 녹음 + release 간격으로
  // 운용해 stop latency를 낮춘다.
  // 2026-07-18 (Antigravity 인수인계 후속): 이 간격이 250ms였을 때 ALSA/USB 오디오
  // 장치를 초당 거의 4회 열고 닫아 WSL usbip 드라이버가 가끔 응답 불가(hang) 상태로
  // 빠지는 원인 중 하나로 지목됐다(실측: 38분간 살아있던 arecord 좀비, 반복 재현된
  // device hang). 정지 감지는 항상 켜둔 채로(안전 속성 유지) 드라이버 부담만 줄이기
  // 위해 간격을 800ms로 늘렸다 — 전체 정지 인지 주기는 약 1.25s에서 약 1.8s로 늘지만
  // 화면의 물리 정지 버튼(즉시 반응)이 1차 경로이고 이 루프는 보조 경로다.
  var SUCCESS_DELAY_MS = 800;

  function nextDelayMs() {
    if (consecutiveFailures === 0) return SUCCESS_DELAY_MS;
    // 800 -> 1600 -> 3200 -> 6400 -> 8000(cap)
    return Math.min(MAX_BACKOFF_MS, SUCCESS_DELAY_MS * Math.pow(2, consecutiveFailures));
  }

  function onFetchFailure(message) {
    consecutiveFailures += 1;
    if (consecutiveFailures === 1) {
      // 연결이 끊긴 "그 순간"에만 로그를 남긴다 — 매 재시도마다 남기지 않는다.
      slog((lang === 'ko' ? '서버 음성 연결 끊김: ' : 'Server voice connection lost: ') + message, 's-log-err');
    }
  }

  function onFetchRecovered() {
    if (consecutiveFailures > 0) {
      slog(lang === 'ko' ? '서버 음성 연결 복구됨' : 'Server voice connection recovered', 's-log-ok');
    }
    consecutiveFailures = 0;
  }

  function listenOnce() {
    if (!state.serverVoiceTimer) return;
    fetch(BACKEND + '/api/server-voice-listen?seconds=1', { method: 'POST' })
      .then(function(res) { return res.json(); })
      .then(function(data) {
        if (!state.serverVoiceTimer) return;
        if (data.error) {
          // 서버는 응답했지만(네트워크는 살아 있음) 애플리케이션 레벨 오류(예: arecord
          // 실패) — 이것도 반복되면 스팸이 되므로 동일하게 dedup/backoff 대상으로 취급한다.
          onFetchFailure(data.error);
          return;
        }
        onFetchRecovered();
        if (data.success && data.voice) {
          var text = data.voice.text || '';
          if (data.action === 'stop') {
            document.getElementById('s-voice-input').value = text;
            state.estopActive = true;
            state.running = false;
            state.paused = false;
            updateExecuteBtn();
            updatePauseBtn();
            var estopBtn = document.getElementById('btn-estop');
            if (estopBtn) {
              estopBtn.textContent = t().estopReset;
              estopBtn.style.background = '#10b981';
              estopBtn.style.borderColor = '#059669';
            }
            slog(
              (lang === 'ko' ? '서버 음성 긴급 정지 감지: ' : 'Server voice emergency stop detected: ') + (text || data.action),
              's-log-err'
            );
          } else if (text) {
            slog(
              (lang === 'ko' ? '서버 음성 인식(정지 아님, 자동 실행 안 함): ' : 'Server voice recognized (non-stop, ignored): ') + text,
              's-log-info'
            );
          } else if (
            data.voice.error &&
            data.voice.error !== 'empty_transcript' &&
            data.voice.error !== 'low_microphone_signal' &&
            data.voice.error !== 'filtered_silence_hallucination' &&
            data.voice.error.indexOf('UnknownValue') === -1 &&
            data.voice.error.indexOf('Could not understand') === -1
          ) {
            slog((lang === 'ko' ? '서버 음성 인식 상태: ' : 'Server voice status: ') + data.voice.error, 's-log-info');
          }
        }
      })
      .catch(function(err) {
        onFetchFailure(err.message);
      })
      .finally(function() {
        if (state.serverVoiceTimer) {
          state.serverVoiceTimer = setTimeout(listenOnce, nextDelayMs());
        }
      });
  }

  state.serverVoiceTimer = setTimeout(listenOnce, 10);
  slog(lang === 'ko' ? '서버 측 음성 긴급정지 대기 시작' : 'Server-side voice E-stop waiting started', 's-log-ok');
}

function stopServerVoiceMonitor() {
  if (state.serverVoiceTimer) {
    clearTimeout(state.serverVoiceTimer);
    state.serverVoiceTimer = null;
  }
  var btn = document.getElementById('btn-voice-record');
  if (btn) {
    btn.disabled = !VOICE_RECOGNITION_ENABLED;
    btn.style.background = '#475569';
    btn.style.borderColor = '#334155';
    btn.innerHTML = VOICE_RECOGNITION_ENABLED
      ? ('🎙 ' + (lang === 'ko' ? '녹음' : 'Record'))
      : (lang === 'ko' ? '음성 중지' : 'Voice disabled');
  }
  updateTopVoiceCommandBtn(false);
  updateLlmVoiceModeStatus();
  setVoiceStatus(false, VOICE_RECOGNITION_ENABLED ? (lang === 'ko' ? '음성 대기' : 'Voice idle') : (lang === 'ko' ? '음성 중지' : 'Voice disabled'));
  if (VOICE_RECOGNITION_ENABLED) {
    slog(lang === 'ko' ? '서버 측 음성 정지' : 'Server-side voice stopped', 's-log-ok');
  }
}

function setVoiceStatus(active, text) {
  var wrap = document.getElementById('s-voice-status');
  var label = document.getElementById('s-voice-status-text');
  if (!wrap || !label) return;
  wrap.classList.toggle('active', !!active);
  label.textContent = text;
}

var _cameraStream = null;
var _serverCameraTimer = null;
window.switchVisionWorkTab = function(tabName) {
  ['move', 'color'].forEach(function(name) {
    var btn = document.getElementById('btn-visiontab-' + name);
    var content = document.getElementById('vision-tab-' + name + '-content');
    var active = (name === tabName);
    if (btn) {
      btn.style.background = active ? '#1e3a8a' : '#1e293b';
      btn.style.borderColor = active ? '#1d4ed8' : '#475569';
      btn.style.color = active ? '#fff' : '#94a3b8';
    }
    if (content) content.style.display = active ? 'block' : 'none';
  });
};

var _colorTrackingStatusTimer = null;

function refreshColorTrackingStatus() {
  // Tracking is not included in the public release.
  return;
}

function startColorTracking() {
  fetch(BACKEND + '/api/color-tracking/start', { method: 'POST' })
    .then(function(r) { return r.json().then(function(d) { d._status = r.status; return d; }); })
    .then(function(d) {
      if (d.success) {
        slog(lang === 'ko' ? '색상 추적을 시작했습니다. 추적 창에서 Space로 손을 동작시킬 수 있습니다.' : 'Color tracking started. Press Space in the tracker window to cycle the gripper.', 's-log-ok');
        startColorTrackingStatusPolling();
      } else {
        slog((lang === 'ko' ? '색상 추적 시작 실패: ' : 'Color tracking start failed: ') + (d.error || d.detail || d._status), 's-log-err');
      }
      refreshColorTrackingStatus();
    })
    .catch(function(err) { slog((lang === 'ko' ? '색상 추적 시작 오류: ' : 'Color tracking start error: ') + err.message, 's-log-err'); });
}

function stopColorTracking() {
  fetch(BACKEND + '/api/color-tracking/stop', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      slog(d.success ? (lang === 'ko' ? '색상 추적을 중지했습니다.' : 'Color tracking stopped.') : (d.error || 'Stop failed'), d.success ? 's-log-ok' : 's-log-err');
      refreshColorTrackingStatus();
    })
    .catch(function(err) { slog((lang === 'ko' ? '색상 추적 중지 오류: ' : 'Color tracking stop error: ') + err.message, 's-log-err'); });
}

function startColorTrackingStatusPolling() {
  // Tracking is not included in the public release.
  return;
}

function startWebcam() {
  var screen = document.getElementById('s-camera-screen');
  if (_cameraStream) return;
  
  var video = document.getElementById('s-webcam-video');
  if (!video) {
    video = document.createElement('video');
    video.id = 's-webcam-video';
    video.setAttribute('autoplay', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('muted', '');
    video.style.position = 'absolute';
    video.style.inset = '0';
    video.style.width = '100%';
    video.style.height = '100%';
    video.style.objectFit = 'cover';
    video.style.zIndex = '0';
    screen.appendChild(video);
  }
  
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    requestCameraStream()
      .then(function(stream) {
        _cameraStream = stream;
        video.srcObject = stream;
        video.style.display = 'block';
        var placeholder = document.getElementById('s-camera-placeholder');
        if (placeholder) placeholder.style.display = 'none';
        slog(lang === 'ko' ? '📷 모바일/태블릿 로컬 카메라 스트림 연결됨' : '📷 Local camera stream connected', 's-log-ok');
      })
      .catch(function(err) {
        console.warn('Camera stream blocked or not available:', err);
        slog(formatMediaErrorLog(err, 'camera'), 's-log-err');
        startServerCameraFallback();
      });
  } else {
    slog(lang === 'ko' ? '⚠️ 이 브라우저는 카메라 스트리밍을 지원하지 않습니다.' : '⚠️ Camera stream not supported on this browser.', 's-log-err');
    startServerCameraFallback();
  }
}

function requestCameraStream() {
  return navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } })
    .catch(function(err) {
      if (err && (err.name === 'NotFoundError' || err.name === 'OverconstrainedError')) {
        return navigator.mediaDevices.getUserMedia({ video: true });
      }
      throw err;
    });
}

function stopWebcam() {
  stopServerCameraFallback();
  if (_cameraStream) {
    _cameraStream.getTracks().forEach(function(track) {
      track.stop();
    });
    _cameraStream = null;
  }
  var video = document.getElementById('s-webcam-video');
  if (video) {
    video.style.display = 'none';
    video.srcObject = null;
  }
  var placeholder = document.getElementById('s-camera-placeholder');
  if (placeholder) placeholder.style.display = '';
}

function startServerCameraFallback() {
  var screen = document.getElementById('s-camera-screen');
  if (!screen) return;
  var img = document.getElementById('s-server-camera-img');
  if (!img) {
    img = document.createElement('img');
    img.id = 's-server-camera-img';
    img.alt = 'server camera';
    img.style.position = 'absolute';
    img.style.inset = '0';
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.objectFit = 'cover';
    img.style.zIndex = '0';
    screen.appendChild(img);
  }
  img.style.display = 'block';
  var placeholder = document.getElementById('s-camera-placeholder');
  if (placeholder) placeholder.style.display = 'none';
  function refresh() {
    img.src = BACKEND + '/api/server-camera-frame?t=' + Date.now();
  }
  refresh();
  if (_serverCameraTimer) clearInterval(_serverCameraTimer);
  _serverCameraTimer = setInterval(refresh, 700);
  slog(lang === 'ko' ? '📷 서버 측 WSL 카메라 화면 연결됨' : '📷 Server-side WSL camera connected', 's-log-ok');
}

function stopServerCameraFallback() {
  if (_serverCameraTimer) {
    clearInterval(_serverCameraTimer);
    _serverCameraTimer = null;
  }
  var img = document.getElementById('s-server-camera-img');
  if (img) {
    img.style.display = 'none';
    img.removeAttribute('src');
  }
}

function formatMediaErrorLog(err, scope) {
  var name = err && err.name ? err.name : 'UnknownError';
  if (name === 'NotFoundError') {
    return lang === 'ko'
      ? '⚠️ ' + scope + ': 입력 장치가 브라우저에 노출되지 않음 (NotFoundError)'
      : '⚠️ ' + scope + ': input devices are not exposed to the browser (NotFoundError)';
  }
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return lang === 'ko'
      ? '⚠️ ' + scope + ': 권한이 차단됨 (' + name + ')'
      : '⚠️ ' + scope + ': permission blocked (' + name + ')';
  }
  return (lang === 'ko' ? '⚠️ 장치 오류: ' : '⚠️ Device error: ') + name;
}

// ─── 목표물 추적 ─────────────────────────────────────────────────
// 화면은 추적을 하지 않는다. 상자를 어디에 끌었는지만 알려주고, 나머지는
// 런타임이 한다. 여기서 좌표를 **프레임 픽셀로 환산**하는 것이 유일한 계산이다 —
// 화면에 보이는 크기와 실제 프레임 크기가 다르기 때문이다.
var _trackTimer = null;
var _trackDrag = null;
var _trackRunning = false;

function _trackEl(id) { return document.getElementById(id); }

function startTargetTracking() {
  var follow = !!(_trackEl('track-follow') && _trackEl('track-follow').checked);
  if (!follow) return _trackStart(false);
  // 팔이 따라가는 것은 실제 로봇이 움직이는 일이다. 실행과 같은 확인을 받는다.
  showModal(function () { _trackStart(true); });
}

function _trackStart(follow) {
  fetch(BACKEND + '/api/target-tracking/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ follow: follow })
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.success) {
        slog((lang === 'ko' ? '추적 시작 실패: ' : 'Tracking start failed: ')
          + (d.error || d.reason || ''), 's-log-err');
        return;
      }
      _trackAttachView();
      slog(lang === 'ko'
        ? (follow ? '목표물 추적 시작 — 화면에서 목표를 끌어 고르세요. 팔이 따라갑니다.'
                  : '목표물 추적 시작 — 화면에서 목표를 끌어 고르세요. 보기만 합니다.')
        : 'Target tracking started — drag on the view to pick a target.',
        follow ? 's-log-err' : 's-log-ok');
      _trackPoll();
    })
    .catch(function (e) { slog('추적 시작 오류: ' + e.message, 's-log-err'); });
}

function stopTargetTracking() {
  fetch(BACKEND + '/api/target-tracking/stop', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function () {
      _trackDetachView();
      slog(lang === 'ko' ? '추적을 멈추고 팔을 그 자리에 세웠습니다.' : 'Tracking stopped; arm held in place.', 's-log-ok');
    });
}

function clearTargetTracking() {
  fetch(BACKEND + '/api/target-tracking/clear', { method: 'POST' });
}

// 영상 붙이기/떼기는 한 자리에서만 한다. 전에는 '시작'을 누른 그 순간에만
// 붙였기 때문에, **브라우저를 새로고침하면 이미 돌고 있는 추적의 영상이 안 붙었다.**
// 화면에는 빈 자리만 남고 끌 것이 없어서, 추적이 도는데도 목표를 고를 수 없었다.
function _trackAttachView() {
  var img = _trackEl('track-view');
  if (!img || img.getAttribute('src')) return;
  img.src = BACKEND + '/api/camera-stream?t=' + Date.now();
  img.style.display = 'block';
  _trackEl('track-placeholder').style.display = 'none';
}

function _trackDetachView() {
  var img = _trackEl('track-view');
  if (!img) return;
  img.style.display = 'none';
  img.removeAttribute('src');
  _trackEl('track-placeholder').style.display = 'flex';
}

// 돌아가는 중에 따라가기를 켜고 끈다. 전에는 시작할 때 정해진 것이 끝이라,
// 보다가 체크상자를 눌러도 아무 일도 안 일어나고 화면도 그 말을 안 했다.
function toggleTargetFollow() {
  var box = _trackEl('track-follow');
  if (!box) return;
  var on = box.checked;
  if (!_trackRunning) return;          // 아직 시작 전이면 '시작'이 이 값을 쓴다
  if (!on) return _trackSendFollow(false);
  box.checked = false;                 // 확인을 받기 전에는 켜진 것처럼 보이지 않게
  showModal(function () { box.checked = true; _trackSendFollow(true); });
}

function _trackSendFollow(on) {
  fetch(BACKEND + '/api/target-tracking/follow', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ on: on })
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.success) {
        _trackEl('track-follow').checked = false;
        slog((lang === 'ko' ? '따라가기를 켜지 못했습니다: ' : 'Could not enable follow: ')
          + (d.error || ''), 's-log-err');
        return;
      }
      slog(on ? (lang === 'ko' ? '따라가기를 켰습니다 — 팔이 움직이기 시작합니다.' : 'Follow on — the arm will start moving.')
              : (lang === 'ko' ? '따라가기를 껐습니다. 보기만 합니다.' : 'Follow off — observing only.'),
        on ? 's-log-err' : 's-log-ok');
    });
}

// 화면 좌표 → 프레임 픽셀. 보이는 크기가 줄어 있어도 상자는 제자리에 가야 한다.
function _trackToFramePx(img, clientX, clientY) {
  var box = img.getBoundingClientRect();
  var sx = (img.naturalWidth || box.width) / box.width;
  var sy = (img.naturalHeight || box.height) / box.height;
  return [Math.round((clientX - box.left) * sx), Math.round((clientY - box.top) * sy),
          clientX - box.left, clientY - box.top];
}

function _installTrackDrag() {
  var img = _trackEl('track-view');
  var ghost = _trackEl('track-drag');
  if (!img || !ghost) return;

  img.addEventListener('mousedown', function (ev) {
    ev.preventDefault();
    _trackDrag = { start: _trackToFramePx(img, ev.clientX, ev.clientY) };
    ghost.style.display = 'block';
    ghost.style.left = _trackDrag.start[2] + 'px';
    ghost.style.top = _trackDrag.start[3] + 'px';
    ghost.style.width = '0px';
    ghost.style.height = '0px';
  });

  window.addEventListener('mousemove', function (ev) {
    if (!_trackDrag) return;
    var now = _trackToFramePx(img, ev.clientX, ev.clientY);
    _trackDrag.end = now;
    ghost.style.left = Math.min(_trackDrag.start[2], now[2]) + 'px';
    ghost.style.top = Math.min(_trackDrag.start[3], now[3]) + 'px';
    ghost.style.width = Math.abs(now[2] - _trackDrag.start[2]) + 'px';
    ghost.style.height = Math.abs(now[3] - _trackDrag.start[3]) + 'px';
  });

  window.addEventListener('mouseup', function () {
    if (!_trackDrag) return;
    var drag = _trackDrag;
    _trackDrag = null;
    ghost.style.display = 'none';
    if (!drag.end) return;
    var x = Math.min(drag.start[0], drag.end[0]);
    var y = Math.min(drag.start[1], drag.end[1]);
    var w = Math.abs(drag.end[0] - drag.start[0]);
    var h = Math.abs(drag.end[1] - drag.start[1]);
    if (w < 8 || h < 8) {
      // 조용히 넘기지 않는다 — 사람은 골랐다고 생각하고 팔이 안 움직인다고 여긴다
      slog(lang === 'ko'
        ? '목표가 너무 작습니다 — 물체를 감싸도록 더 크게 끌어 주세요.'
        : 'Selection too small — drag a larger box around the object.', 's-log-err');
      return;
    }
    fetch(BACKEND + '/api/target-tracking/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox: [x, y, w, h] })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.success) slog((lang === 'ko' ? '목표 선택 실패: ' : 'Select failed: ') + (d.error || ''), 's-log-err');
      });
  });
}

function _trackPoll() {
  // Tracking is not included in the public release.
  return;
}

function refreshTargetTracking() {
  // Tracking is not included in the public release.
  return;
}

// ─── 초기화 ──────────────────────────────────────────────────────
applyI18n();
_installTrackDrag();
_trackPoll();
installSafetyLimitPreviewHandlers();
loadRobotJoints()
  .then(loadSafetyLimitsForUi)
  .then(loadCatalog)
  .then(function () {
    // 2026-07-22 (hangeul 실사용 중 발견): hangeul은 로봇을 고를 때마다
    // window.location.reload()로 페이지 전체를 새로 불러온다. 여기서 자동
    // read-pose가 401(접근 키 없음/오류)을 만나면 브라우저 네이티브
    // alertOrStyled()+prompt()가 뜨는데 — 이 둘은 완전히 동기/차단형이라 뜨는 동안
    // 페이지의 모든 JS(3초 폴링 포함)가 멈춘다. 로봇을 자주 바꾸는 hangeul
    // 워크플로우에서 이게 예측 불가능한 순간에 끼어들어 클릭 순서가 꼬이는
    // 원인이 됐다("로봇1 선택→저장했는데 로봇2에 저장됨" 등). dexter_grid는
    // 로봇을 자주 안 바꾸므로 그대로 자동 실행하고, hangeul만 끈다 — 필요하면
    // '🔄 현재값 읽기' 버튼으로 그때그때 명시적으로 읽으면 된다.
    if (!window.DEXTER_HANGEUL_MOCK) readCurrentPose();
  });
updateExecuteBtn();
toggleRepeatModeUI();
slog((lang === 'ko' ? '화면 준비 완료 · 화면 파일 2026-08-16 23:31' : 'Ready · screen build 2026-08-16 23:31'), 's-log-ok');

// 2026-07-05: 탭이 3개(range/temp/vel)가 되면서 if-else 2벌 → 목록 순회로 일반화.
window.switchAdminTab = function(tabName) {
  ['range', 'temp', 'vel', 'person'].forEach(function(name) {
    var btn = document.getElementById('btn-tab-' + name);
    var content = document.getElementById('tab-' + name + '-content');
    var active = (name === tabName);
    if (btn) {
      btn.style.background = active ? '#1e3a8a' : '#1e293b';
      btn.style.borderColor = active ? '#1d4ed8' : '#475569';
      btn.style.color = active ? '#fff' : '#94a3b8';
    }
    if (content) content.style.display = active ? 'block' : 'none';
  });
};

// 2026-07-23: 안전 범위 설정 4개 탭 — 저장 전엔 어느 탭에서 값을 바꿨는지
// 알 수 없었다(그리퍼처럼 위험한 값일수록 이게 아쉽다는 지적). 탭을 벗어나
// 있어도 "바뀐 탭" 표시(●)를 남긴다.
var _adminTabDirty = { range: false, temp: false, vel: false, person: false };

function resetAdminTabDirtyState() {
  Object.keys(_adminTabDirty).forEach(function(name) {
    _adminTabDirty[name] = false;
    var btn = document.getElementById('btn-tab-' + name);
    if (btn) btn.textContent = btn.textContent.replace(/\s*●$/, '');
  });
}

function markAdminTabDirty(tabName) {
  if (_adminTabDirty[tabName]) return;
  _adminTabDirty[tabName] = true;
  var btn = document.getElementById('btn-tab-' + tabName);
  if (btn && !/●$/.test(btn.textContent)) btn.textContent += ' ●';
}

(function installAdminTabDirtyTracking() {
  var modal = document.getElementById('s-admin-modal');
  if (!modal) return;
  ['input', 'change'].forEach(function(evtName) {
    modal.addEventListener(evtName, function(e) {
      var content = e.target.closest ? e.target.closest('[id^="tab-"][id$="-content"]') : null;
      if (!content) return;
      var tabName = content.id.replace(/^tab-/, '').replace(/-content$/, '');
      markAdminTabDirty(tabName);
    });
  });
})();

// ─── 보안 모니터링 모달 로직 ───────────────────────────────────────
var stateSecEvents = [];

window.openSecurityModal = function() {
  var modal = document.getElementById('s-security-modal');
  if (modal) modal.style.display = 'flex';
  loadSecurityLog();
};

window.closeSecurityModal = function() {
  var modal = document.getElementById('s-security-modal');
  if (modal) modal.style.display = 'none';
  var detailBox = document.getElementById('sec-detail-box');
  if (detailBox) detailBox.style.display = 'none';
};

function loadSecurityLog() {
  var container = document.getElementById('sec-log-container');
  if (!container) return;
  container.innerHTML = '<div style="color:#94a3b8; font-size:0.8rem; padding:10px;">Loading logs...</div>';

  fetch(BACKEND + '/api/security-log')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      stateSecEvents = data.events || [];
      renderSecurityLogs();
    })
    .catch(function(err) {
      container.innerHTML = '<div style="color:#ef4444; font-size:0.8rem; padding:10px;">Failed to load security logs.</div>';
    });
}

function renderSecurityLogs() {
  var container = document.getElementById('sec-log-container');
  if (!container) return;
  container.innerHTML = '';
  
  if (stateSecEvents.length === 0) {
    var emptyMsg = lang === 'ko' ? '감지된 보안 위협이 없습니다.' : 'No security threats detected.';
    container.innerHTML = '<div style="color:#94a3b8; font-size:0.8rem; padding:15px; text-align:center;">' + emptyMsg + '</div>';
    return;
  }
  
  stateSecEvents.forEach(function(evt, index) {
    var item = document.createElement('div');
    item.style.padding = '8px 10px';
    item.style.borderBottom = '1px solid #1e293b';
    item.style.cursor = 'pointer';
    item.style.display = 'flex';
    item.style.justifyContent = 'space-between';
    item.style.alignItems = 'center';
    item.style.transition = 'background 0.2s';
    
    item.addEventListener('mouseover', function() { item.style.background = '#1e293b'; });
    item.addEventListener('mouseout', function() { item.style.background = 'transparent'; });
    item.addEventListener('click', function() {
      showSecurityDetail(evt);
    });

    var leftSide = document.createElement('div');
    leftSide.style.display = 'flex';
    leftSide.style.flexDirection = 'column';
    leftSide.style.alignItems = 'flex-start';
    leftSide.style.gap = '2px';
    
    var timeSpan = document.createElement('span');
    timeSpan.style.fontSize = '0.7rem';
    timeSpan.style.color = '#64748b';
    timeSpan.textContent = evt.timestamp;
    leftSide.appendChild(timeSpan);
    
    var ruleSpan = document.createElement('span');
    ruleSpan.style.fontSize = '0.8rem';
    ruleSpan.style.fontWeight = '600';
    ruleSpan.style.color = '#cbd5e1';
    ruleSpan.textContent = evt.matched_rules.length > 0 ? evt.matched_rules.join(', ') : 'NORMAL_ACCESS';
    leftSide.appendChild(ruleSpan);

    var rightSide = document.createElement('div');
    rightSide.style.display = 'flex';
    rightSide.style.alignItems = 'center';
    rightSide.style.gap = '8px';

    var scoreSpan = document.createElement('span');
    scoreSpan.style.fontSize = '0.75rem';
    scoreSpan.style.fontWeight = '700';
    scoreSpan.style.color = evt.risk_score >= 70 ? '#ef4444' : (evt.risk_score >= 30 ? '#f59e0b' : '#10b981');
    scoreSpan.textContent = evt.risk_score + ' pts';
    rightSide.appendChild(scoreSpan);

    var badge = document.createElement('span');
    badge.style.fontSize = '0.7rem';
    badge.style.fontWeight = '700';
    badge.style.padding = '2px 6px';
    badge.style.borderRadius = '4px';
    
    var color = '#10b981';
    var bg = 'rgba(16, 185, 129, 0.15)';
    if (evt.severity === 'CRITICAL' || evt.severity === 'BLOCK') {
      color = '#ef4444';
      bg = 'rgba(239, 68, 68, 0.15)';
    } else if (evt.severity === 'WARN') {
      color = '#f59e0b';
      bg = 'rgba(245, 158, 11, 0.15)';
    } else if (evt.severity === 'WATCH') {
      color = '#3b82f6';
      bg = 'rgba(59, 130, 246, 0.15)';
    }
    badge.style.color = color;
    badge.style.background = bg;
    badge.style.border = '1px solid ' + color;
    badge.textContent = evt.severity;
    rightSide.appendChild(badge);

    item.appendChild(leftSide);
    item.appendChild(rightSide);
    container.appendChild(item);
  });
}

function showSecurityDetail(evt) {
  var detailBox = document.getElementById('sec-detail-box');
  var desc = document.getElementById('sec-detail-desc');
  var rec = document.getElementById('sec-detail-rec');
  var resolveBtn = document.getElementById('btn-sec-resolve');
  if (!detailBox || !desc || !rec) return;

  var noDescFallback = lang === 'ko' ? '특이 위협 사항이 없습니다.' : 'No notable threat found.';
  var noRecFallback = lang === 'ko' ? '조치가 필요하지 않습니다.' : 'No action required.';
  var descText = lang === 'ko' ? evt.description_ko : (evt.description_en || evt.description_ko);
  var recText = lang === 'ko' ? evt.recommendation_ko : (evt.recommendation_en || evt.recommendation_ko);
  desc.textContent = '🔍 ' + (descText || noDescFallback);
  rec.textContent = '💡 ' + (recText || noRecFallback);
  
  if (resolveBtn) {
    // Only display resolve button if there is actual risk matched
    resolveBtn.style.display = (evt.risk_score >= 30) ? 'block' : 'none';
  }
  
  detailBox.style.display = 'block';
}

function pollSecurityAlerts() {
  fetch(BACKEND + '/api/security-log')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var events = data.events || [];
      var alertEvents = events.filter(function(evt) {
        return evt.severity === 'CRITICAL' || evt.severity === 'BLOCK' || evt.severity === 'WARN';
      });
      var hasAlert = alertEvents.length > 0;

      var alertDot = document.getElementById('sec-alert-dot');
      if (alertDot) {
        alertDot.style.display = hasAlert ? 'inline-flex' : 'none';
        alertDot.textContent = hasAlert ? (alertEvents.length > 99 ? '99+' : String(alertEvents.length)) : '';
      }
      
      var indicator = document.getElementById('sec-indicator');
      if (indicator) {
        if (hasAlert) {
          indicator.style.background = '#ef4444';
          indicator.textContent = '🔴 WARNING / BLOCK';
        } else {
          indicator.style.background = '#10b981';
          indicator.textContent = '🟢 SECURE';
        }
      }

      // Dynamic color swap on header button depending on status
      var monitorBtn = document.getElementById('btn-sec-monitoring');
      if (monitorBtn) {
        if (hasAlert) {
          monitorBtn.style.background = '#ef4444';
          monitorBtn.style.borderColor = '#b91c1c';
          monitorBtn.style.color = '#fff';
          monitorBtn.style.animation = 'pulse 1.5s infinite';
        } else {
          monitorBtn.style.background = 'transparent';
          monitorBtn.style.borderColor = '#10b981';
          monitorBtn.style.color = '#10b981';
          monitorBtn.style.animation = 'none';
        }
      }
    })
    .catch(function() {});
}

window.resolveSecurityAlerts = function() {
  fetch(BACKEND + '/api/security-log/clear', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        slog(lang === 'ko' ? '보안 위협 경보가 모두 해제되었습니다.' : 'All security alerts resolved.', 's-log-ok');
        closeSecurityModal();
        pollSecurityAlerts();
      }
    });
};

// Start polling
setInterval(pollSecurityAlerts, 5000);
pollSecurityAlerts();

// ─── 부재 모드(Away Mode) — 최소 보안 방어 1순위 (2026-07-05) ─────────────
function setAwayModeButtonState(isAway) {
  var btn = document.getElementById('btn-away-mode');
  if (!btn) return;
  btn.title = (lang === 'ko'
    ? '자리를 비우거나 잠들기 전에 켜면, 켜져 있는 동안 로봇이 어떤 요청에도 움직이지 않습니다.'
    : 'Enable before you leave or sleep — while on, the robot will not move for any request.');
  if (isAway) {
    btn.style.background = '#1e3a8a';
    btn.style.borderColor = '#1d4ed8';
    btn.style.color = '#fff';
    btn.textContent = (lang === 'ko' ? '🔒 부재 모드 (동작 차단중)' : '🔒 Away Mode (blocked)');
  } else {
    btn.style.background = 'transparent';
    btn.style.borderColor = '#475569';
    btn.style.color = '#94a3b8';
    btn.textContent = (lang === 'ko' ? '🌙 부재 모드' : '🌙 Away Mode');
  }
}

function refreshAwayModeButton() {
  fetch(BACKEND + '/api/away-mode')
    .then(function(r) { return r.json(); })
    .then(function(d) { setAwayModeButtonState(!!d.away_mode); })
    .catch(function() {});
}

window.toggleAwayMode = function() {
  fetch(BACKEND + '/api/away-mode')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var next = !d.away_mode;
      var msg = next
        ? (lang === 'ko'
            ? '부재 모드를 켭니다. 켜져 있는 동안 로봇은 어떤 요청에도 움직이지 않습니다. 계속할까요?'
            : 'Enable Away Mode? While on, the robot will not move for any request. Continue?')
        : (lang === 'ko'
            ? '부재 모드를 끕니다. 로봇이 다시 실행 요청에 반응합니다. 계속할까요?'
            : 'Disable Away Mode? The robot will respond to execution requests again. Continue?');
      return confirmOrStyled(msg, lang === 'ko' ? '부재 모드' : 'Away Mode').then(function(confirmed) {
        if (!confirmed) return;
        return fetch(BACKEND + '/api/away-mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ away_mode: next })
        })
          .then(function(r) { return r.json(); })
          .then(function(res) {
            if (res.success) {
              setAwayModeButtonState(res.away_mode);
              slog(
                res.away_mode
                  ? (lang === 'ko' ? '부재 모드가 켜졌습니다 — 모든 실행이 차단됩니다.' : 'Away Mode enabled — all execution is blocked.')
                  : (lang === 'ko' ? '부재 모드가 꺼졌습니다.' : 'Away Mode disabled.'),
                's-log-ok'
              );
            } else {
              alertOrStyled(lang === 'ko' ? '부재 모드 변경 실패' : 'Failed to change away mode');
            }
          });
      });
    });
};

// ─── 야간 자동 부재모드 예약 (2026-07-23) ─────────────────────────────
// 대부분의 해킹 시도가 운영자 부재중(특히 밤사이)에 몰린다는 지적에 따라,
// 매번 수동으로 켜야 하는 부재모드의 "깜빡함" 취약점을 없애기 위한 기능.
// #s-settings-panel은 dexter_grid/dexter_hangeul 양쪽 index.html에 동일한
// id로 존재하므로, HTML을 두 번 고치지 않고 이 스크립트에서 UI를 주입한다.
function _ensureAwayScheduleUI() {
  var saveBtn = document.getElementById('away-schedule-save');
  if (saveBtn) {
    saveBtn.textContent = lang === 'ko' ? '야간 자동 저장' : 'Save schedule';
    return;
  }
  var awayBtn = document.getElementById('btn-away-mode');
  if (!awayBtn || !awayBtn.parentNode) return;
  var row = document.createElement('div');
  row.id = 's-away-schedule-row';
  row.className = 's-away-schedule-row';
  row.innerHTML =
    '<label style="display:flex; align-items:center; gap:4px; cursor:pointer;">' +
      '<input type="checkbox" id="away-schedule-enabled">' +
      '<span id="away-schedule-label">' + (lang === 'ko' ? '야간 자동' : 'Nightly auto') + '</span>' +
    '</label>' +
    // 시각 입력칸은 브라우저가 자기 지역 설정대로 그린다 — 영어 화면인데
    // '오전/오후'가 뜨는 이유다. lang을 붙여 24시간 표기를 요청한다.
    // (Firefox·Safari는 따르고, Chrome은 브라우저 언어를 우선한다 —
    //  거기서는 값 자체가 24시간이라 저장되는 값은 같다.)
    '<input type="time" lang="' + (lang === 'ko' ? 'ko' : 'en-GB') + '" id="away-schedule-start" style="width:84px; background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:4px;">' +
    '<span>~</span>' +
    '<input type="time" lang="' + (lang === 'ko' ? 'ko' : 'en-GB') + '" id="away-schedule-end" style="width:84px; background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:4px;">' +
    '<button id="away-schedule-save" class="s-settings-action" style="font-size:0.72rem; padding:3px 10px;">' +
      (lang === 'ko' ? '야간 자동 저장' : 'Save schedule') + '</button>';
  awayBtn.insertAdjacentElement('afterend', row);
  document.getElementById('away-schedule-save').addEventListener('click', window.saveAwayModeSchedule);
}

function refreshAwayModeSchedule() {
  fetch(BACKEND + '/api/away-mode-schedule')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      _ensureAwayScheduleUI();
      var chk = document.getElementById('away-schedule-enabled');
      var startEl = document.getElementById('away-schedule-start');
      var endEl = document.getElementById('away-schedule-end');
      var label = document.getElementById('away-schedule-label');
      if (chk) chk.checked = !!d.enabled;
      if (startEl) startEl.value = d.start || '22:00';
      if (endEl) endEl.value = d.end || '07:00';
      if (label) {
        label.textContent = (lang === 'ko' ? '야간 자동' : 'Nightly auto') +
          (d.enabled && d.active_now ? ' 🔒' : '');
      }
    })
    .catch(function() {});
}

window.saveAwayModeSchedule = function() {
  var chk = document.getElementById('away-schedule-enabled');
  var startEl = document.getElementById('away-schedule-start');
  var endEl = document.getElementById('away-schedule-end');
  if (!chk || !startEl || !endEl) return;
  fetch(BACKEND + '/api/away-mode-schedule', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: chk.checked, start: startEl.value, end: endEl.value })
  })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (res.success) {
        slog(lang === 'ko' ? '야간 자동 부재모드 예약이 저장되었습니다.' : 'Nightly away-mode schedule saved.', 's-log-ok');
        refreshAwayModeSchedule();
        refreshAwayModeButton();
      } else {
        alertOrStyled((lang === 'ko' ? '예약 저장 실패: ' : 'Failed to save schedule: ') + (res.error || ''));
      }
    });
};

function configureVoiceMatchingPanel() {
  var section = document.getElementById('s-voice-match-section');
  if (!section) return;
  section.style.display = IS_VOICE_MATCHING_PORT ? '' : 'none';
  if (!IS_VOICE_MATCHING_PORT) return;
  setVoiceStatus(false, lang === 'ko' ? '음성 매칭 대기' : 'Voice matching ready');
  renderVoiceMappings();
  populateActionSelect();
}

applyUiPreferences();
configureVoiceMatchingPanel();
startColorTrackingStatusPolling();
refreshAwayModeButton();
refreshAwayModeSchedule();
updateMicroMovePreview();
stopServerVoiceMonitor();
