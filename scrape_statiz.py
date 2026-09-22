from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = "https://www.statiz.co.kr/player/?m=analysis&p_no={player_id}"
LEAGUE_URL = "https://mykbo.statiz.co.kr/league/"
PITCH_WORDS = ("구종", "구사", "투구", "pitch", "직구", "포심", "슬라이더", "커브", "체인지업")
RATE_WORDS = ("구사율", "비율", "rate", "%")
VELOCITY_WORDS = ("구속", "평균속도", "평균 구속", "velocity", "speed")

# Statiz 상세분석 표에서 사용하는 구종 약어. JSON에는 게임에서 읽기 쉬운
# 한글 이름을 저장하되 원본 약어도 함께 보존한다.
PITCH_COLUMNS = {
    "2seam": "투심",
    "4seam": "포심",
    "cutt": "커터",
    "curv": "커브",
    "slid": "슬라이더",
    "chan": "체인지업",
    "sink": "싱커",
    "fork": "포크볼",
    "knuc": "너클볼",
    "other": "기타",
}


@dataclass
class Pitch:
    pitch_type: str
    statiz_code: str
    ratio: float | None = None
    velocity_kmh: float | None = None
    count: int | None = None


class RateLimitedError(RuntimeError):
    pass


def flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    copy = frame.copy()
    columns = []
    for column in copy.columns:
        if isinstance(column, tuple):
            parts = [str(part).strip() for part in column if not str(part).startswith("Unnamed")]
            columns.append(" ".join(dict.fromkeys(parts)))
        else:
            columns.append(str(column).strip())
    copy.columns = columns
    return copy


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value)).lower()


def table_score(frame: pd.DataFrame) -> int:
    sample = " ".join(map(str, frame.columns)) + " " + frame.head(10).to_string(index=False)
    compact = normalized_text(sample)
    score = sum(3 for word in PITCH_WORDS if normalized_text(word) in compact)
    score += sum(2 for word in RATE_WORDS if normalized_text(word) in compact)
    score += sum(1 for word in VELOCITY_WORDS if normalized_text(word) in compact)
    return score


def find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in frame.columns:
        compact = normalized_text(column)
        if any(normalized_text(candidate) in compact for candidate in candidates):
            return str(column)
    return None


def parse_number(value: Any) -> float | None:
    if pd.isna(value):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def convert_pitch_table(frame: pd.DataFrame) -> list[Pitch]:
    pitch_column = find_column(frame, ("구종", "구종명", "pitch type", "pitch"))
    rate_column = find_column(frame, RATE_WORDS)
    velocity_column = find_column(frame, VELOCITY_WORDS)
    count_column = find_column(frame, ("투구수", "개수", "count", "구수"))

    if pitch_column is None:
        # 일부 표는 첫 번째 열의 헤더가 비어 있다.
        pitch_column = str(frame.columns[0]) if len(frame.columns) else None
    if pitch_column is None:
        return []

    pitches: list[Pitch] = []
    for _, row in frame.iterrows():
        pitch_type = str(row[pitch_column]).strip()
        if not pitch_type or pitch_type.lower() == "nan" or pitch_type in ("합계", "Total", "전체"):
            continue

        ratio = parse_number(row[rate_column]) if rate_column else None
        if ratio is not None and ratio > 1:
            ratio /= 100.0

        velocity = parse_number(row[velocity_column]) if velocity_column else None
        count_number = parse_number(row[count_column]) if count_column else None
        pitches.append(
            Pitch(
                pitch_type=pitch_type,
                statiz_code=pitch_type,
                ratio=ratio,
                velocity_kmh=velocity,
                count=int(count_number) if count_number is not None else None,
            )
        )

    # 비율 열이 없고 투구 수가 있으면 투구 수로 구사율을 계산한다.
    total_count = sum(p.count or 0 for p in pitches)
    if total_count and all(p.ratio is None for p in pitches):
        for pitch in pitches:
            pitch.ratio = (pitch.count or 0) / total_count
    return pitches


def find_pitch_wide_table(html: str) -> pd.DataFrame:
    """상세분석의 '구종이 열인 표'를 찾아 반환한다."""
    try:
        tables = [flatten_columns(table) for table in pd.read_html(StringIO(html))]
    except ValueError as error:
        raise ValueError("페이지에서 HTML 표를 찾지 못했습니다.") from error

    candidates: list[tuple[int, pd.DataFrame]] = []
    for table in tables:
        compact_columns = {normalized_text(column) for column in table.columns}
        pitch_column_count = len(compact_columns.intersection(PITCH_COLUMNS))
        if pitch_column_count:
            candidates.append((pitch_column_count, table))

    if not candidates:
        raise ValueError("2Seam/4Seam/Cutt 등의 구종 열을 가진 표를 찾지 못했습니다.")
    return max(candidates, key=lambda item: item[0])[1]


def extract_season_metric(html: str) -> tuple[dict[str, float], pd.DataFrame]:
    """구사율/평균 구속 표의 첫 '종합' 행을 구종별 값으로 변환한다."""
    table = find_pitch_wide_table(html)
    aggregate = None

    # 정상 페이지에서는 두 번째 열이 상대팀이고 값이 '종합'이다.
    for _, row in table.iterrows():
        values = {normalized_text(value) for value in row.iloc[:3]}
        if "종합" in values:
            aggregate = row
            break

    # 표 구조가 조금 바뀌어도 첫 행은 시즌 전체 집계 행이다.
    if aggregate is None and not table.empty:
        aggregate = table.iloc[0]
    if aggregate is None:
        raise ValueError("구종 표에 시즌 종합 행이 없습니다.")

    metrics: dict[str, float] = {}
    for column in table.columns:
        code = normalized_text(column)
        if code not in PITCH_COLUMNS:
            continue
        number = parse_number(aggregate[column])
        if number is not None:
            metrics[code] = number
    return metrics, table


def analysis_url(player_id: str, year: str, metric: int) -> str:
    query = urlencode({
        "m": "analysis",
        "p_no": player_id,
        "pos": "pitching",
        "year": year,
        "si1": "1",       # 날짜 & 구종
        "si2": str(metric),
    })
    return f"https://www.statiz.co.kr/player/?{query}"


def current_year(driver: webdriver.Chrome) -> str:
    elements = driver.find_elements(By.ID, "year")
    if elements:
        value = elements[0].get_attribute("value")
        if value and value.isdigit():
            return value
    return str(datetime.now().year)


def read_player_ids(path: Path) -> list[str]:
    ids = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        match = re.search(r"(?:p_no=)?(\d+)", value)
        if not match:
            raise ValueError(f"선수 번호를 해석할 수 없습니다: {line}")
        ids.append(match.group(1))
    return list(dict.fromkeys(ids))


def discover_pitcher_ids(driver: webdriver.Chrome, year: str, output_dir: Path) -> list[str]:
    """해당 시즌 기록실의 모든 투수 페이지를 돌며 p_no를 수집한다."""
    discovered: list[str] = []
    seen: set[str] = set()

    for page in range(1, 101):
        query = urlencode({
            "m": "stat",
            "period": "S001",
            "pos": "P",
            "season": year,
            "sort": "G DESC,totalPoint DESC",
            "t_code": "",
            "terms": "S",
            "page": page,
        })
        driver.get(f"{LEAGUE_URL}?{query}")
        wait_for_page(driver)

        page_ids = re.findall(r"showPlayerInfo\(\s*(\d+)\s*,", driver.page_source)
        new_ids = [player_id for player_id in page_ids if player_id not in seen]
        if not new_ids:
            break
        discovered.extend(new_ids)
        seen.update(new_ids)
        print(f"  선수 목록 {page}페이지: {len(new_ids)}명 (누적 {len(discovered)}명)")
        time.sleep(1.0)

    if not discovered:
        raise RuntimeError(f"{year} 시즌 투수 목록을 찾지 못했습니다.")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "discovered_pitchers.txt").write_text(
        "\n".join(discovered) + "\n", encoding="utf-8"
    )
    (output_dir / f"discovered_pitchers_{year}.txt").write_text(
        "\n".join(discovered) + "\n", encoding="utf-8"
    )
    return discovered


def load_discovered_ids(output_dir: Path, year: str) -> list[str]:
    for path in (
        output_dir / f"discovered_pitchers_{year}.txt",
        output_dir / "discovered_pitchers.txt",
    ):
        if path.exists():
            ids = read_player_ids(path)
            if ids:
                return ids
    return []


def load_completed_results(output_dir: Path, year: str) -> dict[str, dict[str, Any]]:
    path = output_dir / "pitchers.json"
    if not path.exists():
        return {}
    try:
        players = json.loads(path.read_text(encoding="utf-8")).get("players", [])
    except (json.JSONDecodeError, OSError):
        return {}

    completed = {}
    for player in players:
        pitches = player.get("pitches", [])
        has_ratio = any(pitch.get("ratio") is not None for pitch in pitches)
        has_velocity = any(pitch.get("velocity_kmh") is not None for pitch in pitches)
        if str(player.get("season")) == str(year) and has_ratio and has_velocity:
            completed[str(player["player_id"])] = player
    return completed


def make_driver(profile_dir: Path) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Chrome(options=options)


def wait_for_page(driver: webdriver.Chrome, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    WebDriverWait(driver, timeout).until(
        lambda browser: browser.execute_script("return document.readyState") == "complete"
    )
    time.sleep(2)


def reject_rate_limit(html: str) -> None:
    compact = normalized_text(html)
    if "403forbidden" in compact or "과도한요청으로차단" in compact:
        raise RateLimitedError("Statiz가 과도한 요청으로 일시 차단했습니다.")


def collect_player(
    driver: webdriver.Chrome,
    player_id: str,
    raw_dir: Path,
    requested_year: str | None = None,
) -> dict[str, Any]:
    url = BASE_URL.format(player_id=player_id)
    driver.get(url)
    wait_for_page(driver)

    if "member" in driver.current_url and "login" in driver.current_url:
        raise RuntimeError("LOGIN_REQUIRED")

    year = requested_year or current_year(driver)
    player_raw_dir = raw_dir / player_id
    player_raw_dir.mkdir(parents=True, exist_ok=True)

    # 2=구사율, 3=평균 구속. 두 페이지의 시즌 종합 행을 구종 코드로 병합한다.
    driver.get(analysis_url(player_id, year, metric=2))
    wait_for_page(driver)
    ratio_html = driver.page_source
    (player_raw_dir / "usage_rate.html").write_text(ratio_html, encoding="utf-8")
    reject_rate_limit(ratio_html)
    ratios, ratio_table = extract_season_metric(ratio_html)
    ratio_table.to_csv(player_raw_dir / "usage_rate.csv", index=False, encoding="utf-8-sig")

    driver.get(analysis_url(player_id, year, metric=3))
    wait_for_page(driver)
    velocity_html = driver.page_source
    (player_raw_dir / "average_velocity.html").write_text(velocity_html, encoding="utf-8")
    reject_rate_limit(velocity_html)
    velocities, velocity_table = extract_season_metric(velocity_html)
    velocity_table.to_csv(player_raw_dir / "average_velocity.csv", index=False, encoding="utf-8-sig")

    pitches = []
    for code, korean_name in PITCH_COLUMNS.items():
        ratio_percent = ratios.get(code)
        velocity = velocities.get(code)
        # 실제로 구사하지 않는 구종은 게임 데이터에서 제외한다.
        if ratio_percent is None or ratio_percent <= 0:
            continue
        pitches.append(Pitch(
            pitch_type=korean_name,
            statiz_code=code,
            ratio=ratio_percent / 100.0,
            velocity_kmh=velocity if velocity and velocity > 0 else None,
        ))

    title = driver.title
    heading = ""
    for selector in ("h1", "h2", ".player_name", ".name"):
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements and elements[0].text.strip():
            heading = elements[0].text.strip()
            break

    title_parts = [part.strip() for part in title.split("-")]
    title_name = title_parts[1] if len(title_parts) >= 3 else title

    return {
        "player_id": player_id,
        "name": title_name or heading,
        "season": year,
        "source_url": url,
        "pitches": [asdict(pitch) for pitch in pitches],
    }


def collect_with_backoff(
    driver: webdriver.Chrome,
    player_id: str,
    raw_dir: Path,
    year: str,
    cooldown: int,
    max_rate_limit_retries: int = 6,
) -> dict[str, Any]:
    for attempt in range(max_rate_limit_retries + 1):
        try:
            return collect_player(driver, player_id, raw_dir, year)
        except RateLimitedError:
            if attempt >= max_rate_limit_retries:
                raise
            print(
                f"  요청 제한 감지: {cooldown}초 후 같은 선수부터 재시도 "
                f"({attempt + 1}/{max_rate_limit_retries})"
            )
            remaining = cooldown
            while remaining > 0:
                wait_seconds = min(30, remaining)
                time.sleep(wait_seconds)
                remaining -= wait_seconds
                if remaining and remaining % 60 == 0:
                    print(f"  재시도까지 {remaining}초...")
    raise RuntimeError("요청 제한 재시도 횟수를 초과했습니다.")


def save_results(results: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "players": results,
    }
    (output_dir / "pitchers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with (output_dir / "pitches.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "player_id", "name", "pitch_type", "statiz_code", "ratio",
                "velocity_kmh", "count", "source_url",
            ),
        )
        writer.writeheader()
        for player in results:
            for pitch in player["pitches"]:
                writer.writerow({
                    "player_id": player["player_id"],
                    "name": player["name"],
                    "source_url": player["source_url"],
                    **pitch,
                })


def main() -> None:
    parser = argparse.ArgumentParser(description="로그인 세션을 이용해 Statiz 투구 분석 표를 수집합니다.")
    parser.add_argument("--players", type=Path, default=Path("player_ids.txt"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--year", help="수집 시즌(예: 2026). 생략하면 페이지 기본 시즌")
    parser.add_argument(
        "--all-pitchers",
        action="store_true",
        help="지정 시즌 기록실에 등판 기록이 있는 모든 투수를 자동 수집",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="기존 완료 데이터를 이어받지 않고 처음부터 다시 수집",
    )
    parser.add_argument("--delay", type=float, default=3.0, help="선수별 최소 요청 간격(초)")
    parser.add_argument(
        "--cooldown", type=int, default=300,
        help="요청 제한(403) 감지 시 재시도 대기 시간(초, 기본 300)",
    )
    args = parser.parse_args()

    player_ids = [] if args.all_pitchers else read_player_ids(args.players)
    if not args.all_pitchers and not player_ids:
        raise SystemExit("player_ids.txt에 선수 번호를 입력하거나 --all-pitchers를 사용하세요.")

    profile_dir = Path(".statiz_chrome_profile")
    raw_dir = args.output / "raw"
    driver = make_driver(profile_dir)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    try:
        login_probe_id = "13061" if args.all_pitchers else player_ids[0]
        driver.get(BASE_URL.format(player_id=login_probe_id))
        print("\n브라우저에서 Statiz에 직접 로그인하세요. 계정 정보는 이 프로그램이 읽거나 저장하지 않습니다.")
        input("로그인 후 선수 분석 페이지가 보이면 여기서 Enter를 누르세요: ")

        collection_year = args.year or current_year(driver)
        if args.all_pitchers:
            player_ids = load_discovered_ids(args.output, collection_year)
            if player_ids:
                print(f"\n저장된 {collection_year} 시즌 투수 목록 {len(player_ids)}명을 재사용합니다.")
            else:
                print(f"\n{collection_year} 시즌 전체 투수 목록을 찾는 중...")
                player_ids = discover_pitcher_ids(driver, collection_year, args.output)
                print(f"총 {len(player_ids)}명을 찾았습니다.")

        completed = {} if args.restart else load_completed_results(args.output, collection_year)
        results = [completed[player_id] for player_id in player_ids if player_id in completed]
        if completed:
            print(f"완료된 {len(results)}명은 건너뛰고 이어서 수집합니다.")

        for position, player_id in enumerate(player_ids, start=1):
            if player_id in completed:
                continue
            print(f"[{position}/{len(player_ids)}] 선수 {player_id} 수집 중...")
            try:
                result = collect_with_backoff(
                    driver, player_id, raw_dir, collection_year, args.cooldown
                )
            except RuntimeError as error:
                if str(error) == "LOGIN_REQUIRED":
                    print("로그인 세션이 만료되었습니다. 브라우저에서 다시 로그인하세요.")
                    input("로그인 완료 후 Enter: ")
                    try:
                        result = collect_with_backoff(
                            driver, player_id, raw_dir, collection_year, args.cooldown
                        )
                    except (TimeoutException, ValueError, RuntimeError) as retry_error:
                        message = str(retry_error) or type(retry_error).__name__
                        print(f"  재시도 실패: {message}")
                        failures.append({"player_id": player_id, "error": message})
                        (args.output / "failures.json").write_text(
                            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        continue
                else:
                    message = str(error) or type(error).__name__
                    print(f"  수집 실패: {message}")
                    failures.append({"player_id": player_id, "error": message})
                    (args.output / "failures.json").write_text(
                        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    continue
            except (TimeoutException, ValueError) as error:
                message = str(error) or type(error).__name__
                print(f"  수집 실패: {message}")
                failures.append({"player_id": player_id, "error": message})
                (args.output / "failures.json").write_text(
                    json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                continue

            results.append(result)
            print(f"  {result['season']} 시즌, 구종 {len(result['pitches'])}개 감지")
            save_results(results, args.output)  # 중간 실패에도 앞선 결과를 보존
            if position < len(player_ids):
                time.sleep(max(args.delay, 1.0) + random.uniform(0.2, 1.0))
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(f"\n완료: {args.output / 'pitchers.json'}")
    print(f"완료: {args.output / 'pitches.csv'}")
    if failures:
        print(f"실패 {len(failures)}명: {args.output / 'failures.json'}")


if __name__ == "__main__":
    main()
