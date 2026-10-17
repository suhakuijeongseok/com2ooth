# Pygame KBO 타이밍 배팅

웹 게임의 규칙을 Pygame으로 옮긴 독립 실행 버전입니다. 상위 폴더의
`output/pitchers.json`을 읽으며, 파일이 없으면 내장 샘플 투수로도 실행됩니다.
최신 Python/Windows에서도 바이너리 설치가 가능한 Pygame Community Edition을
사용하며 코드에서는 표준 `pygame` 모듈로 불러옵니다.

## 설치 및 실행

프로젝트 루트의 가상환경을 사용하는 경우:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\pygame_game\requirements.txt
.\pygame_game\run_game.ps1
```

또는 `pygame_game/run_game.cmd`를 더블클릭합니다.

## 조작

- 투수 선택: 마우스 클릭 또는 방향키와 Enter
- 투구 시작 / 스윙 / 다음 공: Space 또는 화면 하단 버튼 클릭
- 투수 선택 화면으로 돌아가기: Esc
- 15구 종료 후 같은 투수로 계속: Enter 또는 Space
- 게임 종료 후 투수 선택: Esc

## 규칙

- 실제 구사율에 따라 구종이 선택되고 구속에 따라 공의 도착 시간이 달라집니다.
- 각 라운드는 15구이며 일반 5구, 2배 4구, 3배 3구, 4배 2구, 감점 1구입니다.
- 성공한 타구는 120~200m 사이의 홈런 비거리가 무작위로 정해집니다.
- PERFECT는 기본 10,000점, HIT는 기본 7,500점이며 `기본 점수 × 비거리 ÷ 120`으로 비거리 점수를 계산합니다.
- 2·3·4배 공은 비거리 점수에 해당 배율을 적용합니다. 감점 공은 같은 방식으로 계산한 점수가 차감되며 놓치면 감점되지 않습니다.
