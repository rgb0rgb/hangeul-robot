# 등록된 로봇 (Registered robots)

이 폴더의 `*.json` 한 장이 로봇 한 대다. 여기에는 **부품 목록만** 적는다 —
관절 번호·단위·장치 이름은 `install/modules/`의 부품 기술서가 들고 있다.

Each `*.json` here is one robot: **a list of parts, nothing else.**
Joint ids, units and device names live in the part descriptors under `install/modules/`.

```
instance_id   내부 이름 (파일 이름과 같게)      internal id (match the file name)
display_name  화면에 보일 이름                 shown on screen
runtime_url   이 로봇의 런타임 주소             this robot's runtime
modules       꽂은 부품들                      the parts you plugged in
```

만드는 방법은 둘이다.

1. 콘솔 화면의 **로봇 추가** — 권장
2. `arm.example.json`을 복사해 이름을 바꾸고 고친다

Two ways: use **Add robot** in the console (recommended), or copy
`arm.example.json` and edit it.

이 폴더의 `*.json`은 git에 올리지 않는다. 등록된 로봇은 그 사람의 것이다.
Your `*.json` files are gitignored — a registered robot belongs to its owner.
