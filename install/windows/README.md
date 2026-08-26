# 윈도우 설치 — C14

같은 소스, 같은 계약. 화면과 기능은 동일하다. 다른 것은 두 가지뿐이다.

| | WSL | 윈도우 |
|---|---|---|
| 실행 | `run.sh` | `run.bat` |
| 장치 | `/dev/ttyUSB0` | `COM3` |

부품 기술서에서 장치 이름만 바꾸면 된다. 콘솔 코드는 손대지 않는다.

## 윈도우에서 WSL의 것을 띄울 때 — `run_wsl.bat`

탐색기에서 `\\wsl.localhost\Ubuntu\root\hangeul_robot`을 열고 `run.sh`를 두 번 눌러도
**아무 일도 일어나지 않는다.** `run.sh`는 리눅스 스크립트여서 윈도우가 실행하지 못한다.
같은 폴더의 `run.bat`을 눌러도 안 된다 — `\\wsl.localhost\...`는 UNC 경로이고, cmd는
UNC를 현재 폴더로 쓰지 못해 `UNC 경로는 지원되지 않습니다`를 내고 멈춘다.

그 자리에서 두 번 눌러 띄우려면 `run_wsl.bat`을 쓴다. 자기 폴더를 쓰지 않고 WSL의
절대 경로(`/root/hangeul_robot`)만 쓰므로 UNC 문제를 겪지 않는다.

    wsl.exe -d Ubuntu -- bash -lc "cd /root/hangeul_robot && ./run.sh"

배포판 이름이 `Ubuntu`가 아니면(`wsl -l -q`로 확인) 파일 안의 `DISTRO` 값을 바꾼다.

WSL 터미널에서 직접 띄우는 것도 같다.

    cd /root/hangeul_robot && ./run.sh

## 팔이 안 붙을 때 (`장치 /dev/ttyUSB0 없음 — 건너뜀`)

콘솔은 떴는데 이 줄이 나오면, 화면은 뜨지만 로봇은 없는 상태다. WSL 안에서는 USB
직렬 장치가 **윈도우에서 붙여줘야** 보인다. 윈도우 관리자 명령 프롬프트에서

    usbipd list                      REM 팔의 BUSID를 찾는다 (OMX는 0403:6014 FTDI)
    usbipd attach --wsl --busid 1-5  REM 그 BUSID를 WSL에 붙인다

붙이면 WSL 쪽에 `/dev/ttyUSB0`이 생기고, 그 다음 `run.sh`가 런타임까지 띄운다.
**붙이는 동안 그 장치는 윈도우에서 사라진다** — 같은 팔을 윈도우 네이티브 프로그램
(Beom 등)에서 쓰고 있다면 한쪽만 가질 수 있다.
