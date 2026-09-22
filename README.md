# Statiz 투구 데이터 수집기

비밀번호를 코드에 넣지 않고, 사용자가 열린 Chrome 창에서 직접 로그인한 뒤 선수 분석 표를 JSON/CSV로 저장합니다.

## 설치 및 실행

PowerShell에서 다음 명령을 실행합니다.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scrape_statiz.py
```

특정 시즌을 지정하려면 다음처럼 실행합니다.

```powershell
python scrape_statiz.py --year 2026
```

해당 시즌에 등판 기록이 있는 모든 투수를 한 번에 수집하려면 다음처럼 실행합니다.

```powershell
python scrape_statiz.py --all-pitchers --year 2026
```

실행 중 중단되어도 같은 명령을 다시 실행하면 정상 완료된 선수는 건너뛰고 이어서 수집합니다. 전부 새로 받고 싶을 때만 `--restart`를 추가합니다.

사이트가 과도한 요청으로 403을 반환하면 해당 선수를 실패 처리하지 않고 기본 5분간 대기한 후 같은 선수부터 재시도합니다. 대기 시간은 `--cooldown 600`처럼 조절할 수 있습니다.

Chrome이 열리면 직접 로그인하고, 분석 페이지가 보인 뒤 터미널에서 Enter를 누릅니다. 로그인 상태는 프로젝트 안의 `.statiz_chrome_profile`에 저장되며 아이디와 비밀번호를 코드가 직접 읽지 않습니다.

여러 선수를 수집하려면 `player_ids.txt`에 선수 번호 또는 URL을 한 줄씩 추가합니다.

```text
13061
https://www.statiz.co.kr/player/?m=analysis&p_no=12345
```

결과 파일은 다음 위치에 생성됩니다.

- `output/pitchers.json`: pygame에서 사용하기 좋은 중첩 데이터
- `output/pitches.csv`: 엑셀 등에서 확인하기 쉬운 데이터
- `output/raw/<선수번호>/usage_rate.csv`: 시즌 구사율 원본 표
- `output/raw/<선수번호>/average_velocity.csv`: 시즌 평균 구속 원본 표
- `output/discovered_pitchers.txt`: 자동 발견한 전체 투수 번호
- `output/failures.json`: 데이터가 없거나 수집에 실패한 선수 목록

JSON의 `ratio`는 게임에서 바로 가중치로 쓸 수 있도록 0~1 값으로 저장됩니다. 예를 들어 Statiz의 43.7%는 `0.437`입니다. `velocity_kmh`에는 평균 구속이 저장됩니다.

## pygame에서 구종 선택

```python
import json
import random

with open("output/pitchers.json", encoding="utf-8") as file:
    player = json.load(file)["players"][0]

pitches = [pitch for pitch in player["pitches"] if pitch["ratio"] is not None]
selected = random.choices(pitches, weights=[p["ratio"] for p in pitches], k=1)[0]
print(selected)
```

사이트에 부담을 주지 않도록 기본 요청 간격은 3초 이상이며, 개인적인 범위에서 이용약관을 확인하고 사용하세요.
