#!/usr/bin/env bash
# 윈도우 시작 메뉴(WSLg)에 'FR5 rviz (hangeul)'을 만든다 — 처음 한 번만.
#
#   sudo ./install/ros2/install_fr5_rviz_shortcut.sh
#
# WSLg는 /usr/share/applications 의 바로가기만 시작 메뉴(Ubuntu 폴더)에 올린다.
# 바로가기는 절대 경로를 써야 해서, 이 저장소가 있는 자리를 그때 적어 넣는다.
# 저장소를 옮겼으면 다시 실행한다.
set -eo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET=/usr/share/applications/hangeul-fr5-rviz.desktop
cat > "$TARGET" <<DESKTOP
[Desktop Entry]
Type=Application
Name=FR5 rviz (hangeul)
Comment=FAIRINO FR5 시뮬레이션 화면 (rviz)
Exec=$HERE/fr5_rviz.sh
Icon=/opt/ros/jazzy/share/rviz_common/icons/package.png
Terminal=false
Categories=Development;
DESKTOP
echo "만들었습니다: $TARGET → $HERE/fr5_rviz.sh"
echo "윈도우 시작 메뉴의 Ubuntu 폴더에 'FR5 rviz (hangeul)'이 생깁니다(몇 초 걸릴 수 있음)."
