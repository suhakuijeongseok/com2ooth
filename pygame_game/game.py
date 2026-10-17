from __future__ import annotations

import json
import math
import random
import sys
from array import array
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pygame


WIDTH, HEIGHT = 1280, 720
FPS = 60
PITCHES_PER_ROUND = 15
PERFECT_WINDOW_MS = 50
HIT_WINDOW_MS = 115
CONTACT_PROGRESS = 0.91
BASE_PERFECT_SCORE = 10_000
BASE_GOOD_SCORE = 7_500
WINDUP_MS = 850
RESULT_MS = 850
HIT_FLIGHT_MS = 1050

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DATA_FILE = PROJECT_ROOT / "output" / "pitchers.json"
ASSET_DIR = PROJECT_ROOT / "game" / "assets"
STADIUM_FILE = ASSET_DIR / "night-stadium.png"
PITCHER_SHEET_FILE = ASSET_DIR / "pitcher-right-overhand-30-normalized.png"
HIT_SOUND_FILE = ROOT / "17090^BaseballBat.mp3"
SOUND_DIR = ROOT / "야구 소리"
TITLE_MUSIC_FILE = ROOT / "title_theme.ogg"
FONT_DIR = Path("C:/Windows/Fonts")
REGULAR_FONT_FILE = FONT_DIR / "NotoSansKR-VF.ttf"
BOLD_FONT_FILE = FONT_DIR / "NanumGothic-Bold.ttf"

NAVY = (3, 12, 31)
BLUE = (13, 112, 235)
CYAN = (90, 210, 255)
WHITE = (244, 249, 255)
MUTED = (155, 180, 211)
GOLD = (255, 220, 83)
RED = (255, 83, 105)
GREEN = (103, 255, 180)

MOVEMENTS = {
    "4seam": (0, -7, .38), "2seam": (-42, 14, .25), "cutt": (34, 5, .34),
    "slid": (78, 28, .22), "curv": (-18, 62, .18), "chan": (-45, 36, .24),
    "fork": (6, 70, .32), "splt": (5, 66, .32), "sinker": (-52, 44, .22),
    "other": (0, 12, .30),
}
UNDER_MOVEMENTS = {
    "4seam": (-10, 55, .18), "2seam": (-18, 64, .16), "cutt": (34, -18, .24),
    "slid": (58, -36, .20), "curv": (28, -20, .18), "chan": (-22, 58, .20),
    "fork": (0, 78, .25), "splt": (0, 74, .25), "sinker": (-14, 70, .15),
    "other": (0, 38, .20),
}
PROFILES = {
    "16108": ("left", "over"), "13167": ("right", "over"), "16568": ("right", "over"),
    "14616": ("left", "over"), "14156": ("right", "over"), "11126": ("right", "over"),
    "14816": ("right", "under"), "14108": ("right", "over"), "14106": ("left", "over"),
    "11489": ("right", "over"), "10783": ("right", "over"), "11411": ("left", "over"),
}
BALL_INFO = {
    "normal": ("일반 공", WHITE), "x2": ("2배 점수 공", GREEN),
    "x3": ("3배 점수 공", CYAN), "x4": ("4배 점수 공", GOLD),
    "penalty": ("감점 공", RED),
}


def usable_pitches(player: dict) -> list[dict]:
    return [p for p in player.get("pitches", []) if float(p.get("ratio") or 0) > 0 and p.get("pitch_type") != "기타"]


def flight_duration_ms(velocity_kmh) -> float:
    velocity = max(80.0, float(velocity_kmh or 135))
    physical = 18.44 / (velocity / 3.6) * 1000
    emphasis = (145 / velocity) ** .65
    return min(850, max(500, physical * 1.22 * emphasis))


def make_ball_order() -> list[str]:
    balls = ["normal"] * 5 + ["x2"] * 4 + ["x3"] * 3 + ["x4"] * 2 + ["penalty"]
    random.shuffle(balls)
    return balls


def score_for(ball_type: str, base: int, distance_m: int = 120) -> int:
    """Scale the timing score by home-run distance, then apply ball bonuses."""
    distance_score = round((base * distance_m / 120) / 100) * 100
    if ball_type == "penalty":
        return -distance_score
    return distance_score * {"normal": 1, "x2": 2, "x3": 3, "x4": 4}.get(ball_type, 1)


def load_players() -> list[dict]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        players = [p for p in data.get("players", []) if usable_pitches(p)]
        if players:
            return players
    except (OSError, ValueError):
        pass
    return [{"player_id": "sample", "name": "샘플 투수", "season": "2026", "pitches": [
        {"pitch_type": "포심", "statiz_code": "4seam", "ratio": .55, "velocity_kmh": 147.0},
        {"pitch_type": "슬라이더", "statiz_code": "slid", "ratio": .30, "velocity_kmh": 133.0},
        {"pitch_type": "체인지업", "statiz_code": "chan", "ratio": .15, "velocity_kmh": 129.0},
    ]}]


@lru_cache(maxsize=96)
def font(size: int, bold: bool = False) -> pygame.font.Font:
    """Use a softer Korean typeface and cache sizes used every frame."""
    preferred = BOLD_FONT_FILE if bold else REGULAR_FONT_FILE
    if preferred.exists():
        return pygame.font.Font(str(preferred), size)
    name = pygame.font.match_font("notosanskr,nanumgothic,malgungothic,arial", bold=bold)
    return pygame.font.Font(name, size)


def text(surface, value, size, color, pos, *, center=False, right=False, bold=False,
         max_width=None, min_size=10, clip_rect=None):
    """Draw text, shrinking and clipping it when it belongs inside a UI box."""
    value = str(value)
    fitted_size = size
    image = font(fitted_size, bold).render(value, True, color)
    while max_width and image.get_width() > max_width and fitted_size > min_size:
        fitted_size -= 1
        image = font(fitted_size, bold).render(value, True, color)
    if center:
        rect = image.get_rect(center=pos)
    elif right:
        rect = image.get_rect(topright=pos)
    else:
        rect = image.get_rect(topleft=pos)
    previous_clip = surface.get_clip()
    if clip_rect is not None:
        surface.set_clip(clip_rect)
    surface.blit(image, rect)
    if clip_rect is not None:
        surface.set_clip(previous_clip)
    return rect


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    return t * t * (3 - 2 * t)


def make_bat_crack_sound() -> pygame.mixer.Sound | None:
    """Synthesize a short, punchy wooden-bat crack without an external asset."""
    mixer_info = pygame.mixer.get_init()
    if not mixer_info:
        return None
    sample_rate, sample_format, channels = mixer_info
    if sample_format != -16:
        return None

    rng = random.Random(42)
    duration = .24
    samples = array("h")
    for index in range(int(sample_rate * duration)):
        t = index / sample_rate
        # Sharp contact transient followed by two woody resonances.
        crack = rng.uniform(-1, 1) * math.exp(-t * 92)
        body = math.sin(2 * math.pi * 185 * t) * math.exp(-t * 22)
        knock = math.sin(2 * math.pi * 415 * t + .45) * math.exp(-t * 35)
        snap = math.sin(2 * math.pi * 1180 * t) * math.exp(-t * 62)
        attack = min(1.0, t / .0015)
        value = attack * (crack * .72 + body * .68 + knock * .34 + snap * .18)
        value = int(max(-1.0, min(1.0, value)) * 27500)
        for _ in range(channels):
            samples.append(value)
    if sys.byteorder == "big":
        samples.byteswap()
    return pygame.mixer.Sound(buffer=samples.tobytes())


@dataclass
class State:
    screen: str = "title"
    phase: str = "idle"
    player: dict | None = None
    profile: tuple[str, str] = ("right", "over")
    pitch: dict | None = None
    selected: int = 0
    phase_started: int = 0
    flight_started: int = 0
    duration: float = 600
    target: tuple[float, float] = (0, 0)
    ball_pos: tuple[float, float] = (WIDTH / 2, 320)
    ball_scale: float = .4
    trail: list[tuple[float, float, float]] = field(default_factory=list)
    hits: int = 0
    misses: int = 0
    streak: int = 0
    best: int = 0
    thrown: int = 0
    round_no: int = 1
    round_score: int = 0
    total_score: int = 0
    order: list[str] = field(default_factory=make_ball_order)
    ball_type: str = "normal"
    message: str = "투수를 선택하세요"
    detail: str = ""
    result_color: tuple[int, int, int] = WHITE
    result_started: int = 0
    hit_started: int = 0
    hit_origin: tuple[float, float] = (WIDTH / 2, 500)
    hit_target: tuple[float, float] = (WIDTH / 2, 170)
    hit_duration: float = HIT_FLIGHT_MS
    home_run_distance: int = 120
    pending_result: tuple[str, int, tuple[int, int, int]] | None = None


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("KBO 타이밍 배팅 - Pygame")
        self.surface = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.canvas = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.players = load_players()
        self.state = State()
        self.action_rect = pygame.Rect(520, 626, 240, 64)
        self.start_rect = pygame.Rect(490, 620, 300, 64)
        self.stadium = self.load_stadium()
        self.pitcher_frames = self.load_pitcher_frames()
        self.sounds = self.load_sounds()
        self.setup_audio_channels()
        self.play_title_music()

    def play_title_music(self):
        if not pygame.mixer.get_init() or not TITLE_MUSIC_FILE.exists():
            return
        try:
            pygame.mixer.music.load(str(TITLE_MUSIC_FILE))
            pygame.mixer.music.set_volume(.62)
            pygame.mixer.music.play(loops=-1, fade_ms=700)
        except pygame.error:
            pass

    def start_game_menu(self):
        self.state.screen = "select"

    def load_sound_group(self, pattern):
        if not pygame.mixer.get_init() or not SOUND_DIR.exists():
            return []
        sounds = []
        for path in sorted(SOUND_DIR.glob(pattern)):
            try:
                sounds.append(pygame.mixer.Sound(str(path)))
            except pygame.error:
                pass
        return sounds

    def load_sounds(self):
        sounds = {
            "ambient": self.load_sound_group("*Crowd_Normal_*.wav"),
            "release": self.load_sound_group("*Pitch_Release*.wav*"),
            "swing_miss": self.load_sound_group("*Hit_Miss_*.wav"),
            "catch": self.load_sound_group("*Catch_*.wav"),
            "cheer": self.load_sound_group("*Crowd_Cheer_*.wav"),
            "disappointed": self.load_sound_group("*Crowd_Disappointed_*.wav"),
            "boo": self.load_sound_group("*Crowd_Booing.wav"),
            "landing": self.load_sound_group("*Ball_LandingEtc_*.wav"),
        }
        try:
            sounds["hit"] = (
                pygame.mixer.Sound(str(HIT_SOUND_FILE))
                if pygame.mixer.get_init() and HIT_SOUND_FILE.exists()
                else make_bat_crack_sound()
            )
        except pygame.error:
            sounds["hit"] = make_bat_crack_sound()
        return sounds

    def setup_audio_channels(self):
        self.ambient_channel = self.effect_channel = self.crowd_channel = None
        if not pygame.mixer.get_init():
            return
        pygame.mixer.set_num_channels(max(12, pygame.mixer.get_num_channels()))
        self.ambient_channel = pygame.mixer.Channel(0)
        self.effect_channel = pygame.mixer.Channel(1)
        self.crowd_channel = pygame.mixer.Channel(2)
        self.ambient_channel.set_volume(.14)
        self.effect_channel.set_volume(.9)
        self.crowd_channel.set_volume(.34)

    def play_effect(self, group, *, volume=None):
        choices = self.sounds.get(group, [])
        if not self.effect_channel or not choices:
            return
        self.effect_channel.set_volume(.9 if volume is None else volume)
        self.effect_channel.play(random.choice(choices))

    def play_crowd(self, group, *, queued=False):
        choices = self.sounds.get(group, [])
        if not self.crowd_channel or not choices:
            return
        sound = random.choice(choices)
        if queued and self.crowd_channel.get_busy():
            self.crowd_channel.queue(sound)
        else:
            self.crowd_channel.play(sound, fade_ms=80)

    def load_stadium(self):
        try:
            image = pygame.image.load(STADIUM_FILE).convert()
            return pygame.transform.smoothscale(image, (WIDTH, HEIGHT))
        except (pygame.error, OSError):
            return None

    def load_pitcher_frames(self):
        """Split the 6 x 5 transparent sprite sheet into animation frames."""
        try:
            sheet = pygame.image.load(PITCHER_SHEET_FILE).convert_alpha()
        except (pygame.error, OSError):
            return []
        cell_w, cell_h = sheet.get_width() // 6, sheet.get_height() // 5
        frames = []
        for row in range(5):
            for col in range(6):
                frame = sheet.subsurface((col * cell_w, row * cell_h, cell_w, cell_h)).copy()
                frames.append(pygame.transform.smoothscale(frame, (183, 183)))
        return frames

    def profile_for(self, player):
        return PROFILES.get(str(player.get("player_id")), (player.get("throw_hand", "right"), player.get("pitching_form", "over")))

    def select_player(self):
        s = self.state
        if pygame.mixer.get_init():
            pygame.mixer.music.fadeout(500)
        if self.ambient_channel and self.sounds["ambient"] and not self.ambient_channel.get_busy():
            self.ambient_channel.play(random.choice(self.sounds["ambient"]), loops=-1, fade_ms=700)
        s.player = self.players[s.selected]
        s.profile = self.profile_for(s.player)
        s.screen, s.hits, s.misses, s.streak, s.best = "game", 0, 0, 0, 0
        s.round_no, s.total_score = 1, 0
        self.prepare_round()
        self.reset_pitch("준비되면 투구를 시작하세요")

    def prepare_round(self):
        s = self.state
        s.thrown, s.round_score, s.order = 0, 0, make_ball_order()

    def weighted_pitch(self):
        pitches = usable_pitches(self.state.player)
        return random.choices(pitches, weights=[float(p["ratio"]) for p in pitches], k=1)[0]

    def reset_pitch(self, message="다음 공을 준비하세요"):
        s = self.state
        s.phase, s.message, s.detail = "idle", message, "SPACE 또는 버튼을 누르세요"
        s.target = (random.uniform(-70, 70), random.uniform(-18, 18))
        s.trail.clear()

    def begin_pitch(self):
        s = self.state
        s.ball_type = s.order[s.thrown]
        s.pitch = self.weighted_pitch()
        s.duration = flight_duration_ms(s.pitch.get("velocity_kmh"))
        s.phase, s.phase_started = "windup", pygame.time.get_ticks()
        label = BALL_INFO[s.ball_type][0]
        s.message, s.detail = "투수 와인드업", f"{label} · 공의 색을 확인하세요"
        s.trail.clear()

    def release(self, now):
        s = self.state
        hand, form = s.profile
        release_x = WIDTH / 2 + (-22 if hand == "right" else 22)
        release_y = 340 if form == "under" else 292
        s.phase, s.flight_started = "pitching", now
        s.ball_pos, s.ball_scale = (release_x, release_y), .38
        s.message = "스윙!"
        self.play_effect("release", volume=.58)

    def swing(self, now):
        s = self.state
        if s.phase != "pitching":
            return
        elapsed = now - s.flight_started
        error = elapsed - s.duration * CONTACT_PROGRESS
        if abs(error) <= PERFECT_WINDOW_MS:
            self.start_hit_flight(now, "PERFECT!", BASE_PERFECT_SCORE, GOLD)
        elif abs(error) <= HIT_WINDOW_MS:
            self.start_hit_flight(now, "HIT!", BASE_GOOD_SCORE, CYAN)
        else:
            self.resolve_miss("너무 빨랐습니다" if error < 0 else "너무 늦었습니다")

    def start_hit_flight(self, now, label, base, color):
        """Turn the pitched ball around and send it deep into the stadium."""
        s = self.state
        hit_sound = self.sounds.get("hit")
        if self.effect_channel and hit_sound:
            self.effect_channel.set_volume(.92)
            self.effect_channel.play(hit_sound)
        reaction = "boo" if s.ball_type == "penalty" else "cheer"
        self.play_crowd(reaction)
        s.phase = "hit_flight"
        s.hit_started = now
        s.hit_origin = s.ball_pos
        s.home_run_distance = random.randint(120, 200)
        distance_progress = (s.home_run_distance - 120) / 80
        s.hit_duration = lerp(850, 1300, distance_progress)
        horizontal = max(-1.0, min(1.0, s.target[0] / 70.0))
        target_y = lerp(225, 105, distance_progress)
        s.hit_target = (WIDTH / 2 + horizontal * 310 + random.uniform(-45, 45), target_y)
        s.pending_result = (label, base, color)
        s.message = label
        s.detail = ""
        s.result_color = color
        s.trail.clear()

    def resolve_hit(self, label, base, color):
        s = self.state
        awarded = score_for(s.ball_type, base, s.home_run_distance)
        s.hits += 1
        s.streak += 1
        s.best = max(s.best, s.streak)
        s.round_score += awarded
        s.total_score += awarded
        prefix = "감점" if awarded < 0 else label
        self.finish_pitch(
            f"{prefix} · {s.home_run_distance}m  {awarded:+,}점",
            color if awarded >= 0 else RED,
        )

    def resolve_miss(self, message="루킹", *, swung=True):
        s = self.state
        self.play_effect("swing_miss" if swung else "catch", volume=.68)
        if random.random() < .45:
            self.play_crowd("disappointed")
        s.misses += 1
        s.streak = 0
        self.finish_pitch(message, RED)

    def finish_pitch(self, message, color):
        s = self.state
        s.phase = "result"
        s.thrown += 1
        s.message, s.result_color = message, color
        velocity = s.pitch.get("velocity_kmh")
        distance_info = f"홈런 {s.home_run_distance}m · " if color != RED or "m" in message else ""
        s.detail = f"{distance_info}{s.pitch['pitch_type']} · {velocity:.1f} km/h · 구사율 {float(s.pitch['ratio']) * 100:.1f}% · {s.thrown}/15구"
        s.result_started = pygame.time.get_ticks()

    def continue_after_result(self):
        if self.state.thrown >= PITCHES_PER_ROUND:
            self.state.phase = "summary"
        else:
            self.reset_pitch()

    def update(self, now):
        s = self.state
        if s.screen != "game":
            return
        if s.phase == "windup" and now - s.phase_started >= WINDUP_MS:
            self.release(now)
        elif s.phase == "pitching":
            raw = min(1.0, (now - s.flight_started) / s.duration)
            depth = smooth(raw)
            hand, form = s.profile
            movement = (UNDER_MOVEMENTS if form == "under" else MOVEMENTS).get(s.pitch.get("statiz_code"), MOVEMENTS["other"])
            mx, my, onset = movement
            mirror = -1 if hand == "left" else 1
            br = smooth(max(0, (raw - onset) / (1 - onset)))
            release_x = WIDTH / 2 + (-22 if hand == "right" else 22)
            release_y = 340 if form == "under" else 292
            end_x = WIDTH / 2 + s.target[0]
            end_y = 500 + s.target[1]
            x = lerp(release_x, end_x, depth) + mx * 1.2 * mirror * br
            y = lerp(release_y, end_y, depth) - 15 * math.sin(math.pi * raw) + my * .105 * br
            s.ball_scale = .38 + raw ** 2.15 * 3.05
            s.ball_pos = (x, y)
            s.trail.insert(0, (x, y, s.ball_scale))
            del s.trail[6:]
            if raw >= 1:
                self.resolve_miss("루킹", swung=False)
        elif s.phase == "hit_flight":
            raw = min(1.0, (now - s.hit_started) / s.hit_duration)
            eased = 1 - (1 - raw) ** 2
            x0, y0 = s.hit_origin
            x1, y1 = s.hit_target
            x = lerp(x0, x1, eased)
            y = lerp(y0, y1, eased) - math.sin(math.pi * raw) * 155
            s.ball_scale = max(.24, 3.15 * (1 - eased) + .24)
            s.ball_pos = (x, y)
            s.trail.insert(0, (x, y, s.ball_scale))
            del s.trail[10:]
            if raw >= 1 and s.pending_result:
                label, base, color = s.pending_result
                s.pending_result = None
                self.play_effect("landing", volume=.42)
                self.resolve_hit(label, base, color)

    def action(self):
        s = self.state
        now = pygame.time.get_ticks()
        if s.phase == "idle": self.begin_pitch()
        elif s.phase == "pitching": self.swing(now)
        elif s.phase == "result": self.continue_after_result()
        elif s.phase == "summary":
            s.round_no += 1
            self.prepare_round()
            self.reset_pitch(f"ROUND {s.round_no} · 새 15구를 준비하세요")

    def handle_event(self, event):
        s = self.state
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if s.screen == "game": s.screen, s.phase = "select", "idle"
                else: return False
            elif s.screen == "title":
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.start_game_menu()
            elif s.screen == "select":
                cols = 3
                if event.key == pygame.K_LEFT: s.selected = (s.selected - 1) % len(self.players)
                elif event.key == pygame.K_RIGHT: s.selected = (s.selected + 1) % len(self.players)
                elif event.key == pygame.K_UP: s.selected = (s.selected - cols) % len(self.players)
                elif event.key == pygame.K_DOWN: s.selected = (s.selected + cols) % len(self.players)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE): self.select_player()
            elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.action()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = self.to_canvas(event.pos)
            if s.screen == "title" and self.start_rect.collidepoint(x, y):
                self.start_game_menu()
            elif s.screen == "select":
                for i, rect in enumerate(self.card_rects()):
                    if rect.collidepoint(x, y): s.selected = i; self.select_player(); break
            elif self.action_rect.collidepoint(x, y):
                self.action()
        return True

    def to_canvas(self, pos):
        sw, sh = self.surface.get_size()
        scale = min(sw / WIDTH, sh / HEIGHT)
        ox, oy = (sw - WIDTH * scale) / 2, (sh - HEIGHT * scale) / 2
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def card_rects(self):
        rects = []
        for i in range(len(self.players)):
            row, col = divmod(i, 3)
            rects.append(pygame.Rect(130 + col * 350, 180 + row * 112, 320, 92))
        return rects

    def draw_title(self, now):
        c = self.canvas
        if self.stadium:
            c.blit(self.stadium, (0, 0))
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((0, 8, 28, 105))
            c.blit(veil, (0, 0))
        else:
            c.fill(NAVY)

        text(c, "THE REAL HOMERUN RACE", 58, WHITE, (WIDTH // 2, 245), center=True, bold=True,
             max_width=1040)
        text(c, "KBO TIMING BATTING", 20, CYAN, (WIDTH // 2, 310), center=True, bold=True)
        text(c, "나만의 타이밍으로 담장을 넘겨라", 19, (210, 225, 242),
             (WIDTH // 2, 355), center=True, max_width=700)

        bottom_shade = pygame.Surface((WIDTH, 150), pygame.SRCALPHA)
        bottom_shade.fill((0, 7, 22, 150))
        c.blit(bottom_shade, (0, HEIGHT - 150))
        pulse = int(12 * (math.sin(now / 350) + 1) / 2)
        pygame.draw.rect(c, (20 + pulse, 120 + pulse, 235), self.start_rect, border_radius=30)
        pygame.draw.rect(c, (150, 225, 255), self.start_rect, 2, border_radius=30)
        text(c, "게임 시작", 27, WHITE, self.start_rect.center, center=True, bold=True,
             max_width=self.start_rect.width - 40, clip_rect=self.start_rect)

    def draw_background(self):
        if self.stadium:
            self.canvas.blit(self.stadium, (0, 0))
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 8, 24, 38))
            self.canvas.blit(shade, (0, 0))
            return
        self.canvas.fill(NAVY)
        pygame.draw.circle(self.canvas, (10, 53, 111), (WIDTH // 2, 190), 510)
        pygame.draw.ellipse(self.canvas, (26, 86, 54), (-100, 350, WIDTH + 200, 500))
        pygame.draw.polygon(self.canvas, (136, 91, 52), [(430, 720), (850, 720), (690, 390), (590, 390)])
        pygame.draw.polygon(self.canvas, (224, 224, 208), [(535, 720), (745, 720), (677, 510), (603, 510)], 4)

    def draw_select(self):
        c, s = self.canvas, self.state
        c.fill((2, 9, 24))
        pygame.draw.circle(c, (7, 43, 94), (WIDTH // 2, 160), 610)
        text(c, "KBO TIMING BATTING", 18, CYAN, (130, 58), bold=True)
        text(c, "상대 투수를 선택하세요", 42, WHITE, (130, 93), bold=True)
        for i, (player, rect) in enumerate(zip(self.players, self.card_rects())):
            active = i == s.selected
            pygame.draw.rect(c, (7, 37, 79) if active else (5, 23, 51), rect, border_radius=8)
            pygame.draw.rect(c, CYAN if active else (43, 82, 126), rect, 3 if active else 1, border_radius=8)
            pitches = usable_pitches(player)
            primary = max(pitches, key=lambda p: p["ratio"])
            hand, form = self.profile_for(player)
            profile = ("좌완" if hand == "left" else "우완") + " " + ("언더핸드" if form == "under" else "오버핸드")
            text(c, f"{i + 1:02}", 28, (55, 94, 138), (rect.x + 15, rect.y + 12), bold=True)
            text(c, player["name"], 24, WHITE, (rect.x + 70, rect.y + 11), bold=True,
                 max_width=rect.width - 86, clip_rect=rect)
            text(c, f"{profile} · {primary['pitch_type']} {primary['ratio'] * 100:.1f}%", 15, MUTED,
                 (rect.x + 70, rect.y + 51), max_width=rect.width - 86, clip_rect=rect)
        text(c, "방향키로 이동 · ENTER로 선택 · 마우스 클릭 가능", 16, MUTED, (WIDTH // 2, 675), center=True)

    def draw_pitcher(self, now):
        c, s = self.canvas, self.state
        if self.pitcher_frames:
            if s.phase == "windup":
                progress = min(1.0, (now - s.phase_started) / WINDUP_MS)
                index = min(27, int(progress * 27))
            elif s.phase in ("pitching", "hit_flight", "result"):
                elapsed = max(0, now - s.flight_started)
                index = min(29, 27 + int(elapsed / 90))
            else:
                index = 0
            frame = self.pitcher_frames[index]
            if s.profile[0] == "left":
                frame = pygame.transform.flip(frame, True, False)
            rect = frame.get_rect(midbottom=(WIDTH // 2, 414))
            shadow = pygame.Surface((130, 22), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 105), shadow.get_rect())
            c.blit(shadow, shadow.get_rect(center=(WIDTH // 2, 405)))
            c.blit(frame, rect)
            return
        windup = 0
        if s.phase == "windup": windup = min(1, (now - s.phase_started) / WINDUP_MS)
        x, y = WIDTH // 2, 300
        pygame.draw.ellipse(c, (0, 0, 0, 100), (x - 45, y + 82, 90, 18))
        pygame.draw.circle(c, (218, 169, 126), (x, y), 18)
        pygame.draw.rect(c, (230, 241, 252), (x - 25, y + 18, 50, 72), border_radius=10)
        pygame.draw.rect(c, BLUE, (x - 20, y - 15, 40, 13), border_radius=6)
        arm_angle = -100 * math.sin(windup * math.pi)
        end = (x + math.cos(math.radians(arm_angle)) * 50, y + 37 + math.sin(math.radians(arm_angle)) * 50)
        pygame.draw.line(c, (218, 169, 126), (x, y + 35), end, 13)
        pygame.draw.line(c, WHITE, (x - 12, y + 85), (x - 20, y + 132), 13)
        pygame.draw.line(c, WHITE, (x + 12, y + 85), (x + 22, y + 132), 13)

    def draw_ball(self):
        s, c = self.state, self.canvas
        if s.phase not in ("pitching", "hit_flight"): return
        _, color = BALL_INFO[s.ball_type]
        for i, (x, y, scale) in enumerate(reversed(s.trail)):
            radius = max(2, int(3 * scale))
            pygame.draw.circle(c, (*color, 50), (int(x), int(y)), radius)
        radius = max(3 if s.phase == "hit_flight" else 6, int(7 * s.ball_scale))
        pygame.draw.circle(c, color, (int(s.ball_pos[0]), int(s.ball_pos[1])), radius + 5)
        pygame.draw.circle(c, WHITE if s.ball_type != "penalty" else RED, (int(s.ball_pos[0]), int(s.ball_pos[1])), radius)
        pygame.draw.arc(c, RED, (s.ball_pos[0]-radius*.7, s.ball_pos[1]-radius, radius*1.4, radius*2), -1.2, 1.2, 2)

    def draw_game(self, now):
        c, s = self.canvas, self.state
        self.draw_background()
        text(c, "ESC", 14, MUTED, (24, 22), bold=True)
        text(c, s.player["name"], 25, WHITE, (78, 15), bold=True, max_width=300)
        text(c, f"ROUND {s.round_no}", 14, CYAN, (80, 46), bold=True)
        # Keep the current pitch number on screen until the player advances.
        visible_pitch = s.thrown if s.phase in ("result", "summary") else s.thrown + 1
        stats = [("HIT", s.hits), ("MISS", s.misses), ("BEST", s.best),
                 ("PITCH", f"{min(max(visible_pitch, 1), PITCHES_PER_ROUND)}/{PITCHES_PER_ROUND}"),
                 ("TOTAL", f"{s.total_score:,}")]
        for i, (label, value) in enumerate(stats):
            x = 800 + i * 92
            text(c, label, 11, MUTED, (x, 15), bold=True)
            text(c, value, 20, GOLD if label == "TOTAL" else WHITE, (x, 34), bold=True,
                 max_width=82, min_size=9, clip_rect=pygame.Rect(x, 30, 86, 34))
        self.draw_pitcher(now)
        pygame.draw.rect(c, (160, 224, 255), (WIDTH//2-70, 425, 140, 170), 2)
        for i in (1, 2):
            pygame.draw.line(c, (100, 170, 210), (WIDTH//2-70+i*46, 425), (WIDTH//2-70+i*46, 595), 1)
            pygame.draw.line(c, (100, 170, 210), (WIDTH//2-70, 425+i*56), (WIDTH//2+70, 425+i*56), 1)
        self.draw_ball()
        if s.phase in ("windup", "pitching"):
            label, color = BALL_INFO[s.ball_type]
            text(c, label, 22, color, (WIDTH // 2, 92), center=True, bold=True)
        # Timing feedback belongs beside the plate, not on top of the strike zone.
        panel = pygame.Rect(32, 470, 390, 122)
        panel_surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_surface, (2, 12, 31, 205), panel_surface.get_rect(), border_radius=12)
        pygame.draw.rect(panel_surface, (90, 210, 255, 90), panel_surface.get_rect(), 1, border_radius=12)
        c.blit(panel_surface, panel)
        message_color = s.result_color if s.phase in ("result", "hit_flight") else WHITE
        text(c, s.message, 27, message_color, (panel.centerx, panel.y + 34), center=True, bold=True,
             max_width=panel.width - 32, clip_rect=panel)
        text(c, s.detail, 14, MUTED, (panel.centerx, panel.y + 79), center=True,
             max_width=panel.width - 32, clip_rect=panel)
        pygame.draw.rect(c, BLUE, self.action_rect, border_radius=28)
        if s.phase == "result" and s.thrown >= PITCHES_PER_ROUND:
            label = "결과 보기"
        else:
            label = {"idle": "투구 시작", "windup": "준비", "pitching": "스윙!",
                     "hit_flight": "타구 비행 중", "result": "다음 투구",
                     "summary": "다음 라운드"}.get(s.phase, "SPACE")
        text(c, label, 22, WHITE, self.action_rect.center, center=True, bold=True,
             max_width=self.action_rect.width - 30, clip_rect=self.action_rect)
        if s.phase == "summary": self.draw_summary()

    def draw_summary(self):
        c, s = self.canvas, self.state
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); veil.fill((0, 5, 18, 220)); c.blit(veil, (0, 0))
        rect = pygame.Rect(390, 170, 500, 350)
        pygame.draw.rect(c, (7, 31, 68), rect, border_radius=12); pygame.draw.rect(c, CYAN, rect, 2, border_radius=12)
        inner_width = rect.width - 70
        text(c, f"ROUND {s.round_no} COMPLETE", 16, CYAN, (WIDTH//2, 210), center=True, bold=True,
             max_width=inner_width, clip_rect=rect)
        text(c, "15구 종료!", 38, WHITE, (WIDTH//2, 258), center=True, bold=True,
             max_width=inner_width, clip_rect=rect)
        text(c, s.player["name"], 18, MUTED, (WIDTH//2, 302), center=True,
             max_width=inner_width, clip_rect=rect)
        text(c, "이번 라운드", 18, MUTED, (460, 355), max_width=145, clip_rect=rect)
        text(c, f"{s.round_score:,}점", 27, GOLD, (820, 350), right=True, bold=True,
             max_width=215, clip_rect=rect)
        text(c, "누적 점수", 18, MUTED, (460, 405), max_width=145, clip_rect=rect)
        text(c, f"{s.total_score:,}점", 27, CYAN, (820, 400), right=True, bold=True,
             max_width=215, clip_rect=rect)
        text(c, "SPACE/ENTER: 같은 투수로 계속  ·  ESC: 투수 선택", 15, WHITE,
             (WIDTH//2, 475), center=True, max_width=inner_width, clip_rect=rect)

    def present(self):
        sw, sh = self.surface.get_size()
        scale = min(sw / WIDTH, sh / HEIGHT)
        size = (max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale)))
        frame = pygame.transform.smoothscale(self.canvas, size)
        self.surface.fill((0, 0, 0)); self.surface.blit(frame, ((sw-size[0])//2, (sh-size[1])//2)); pygame.display.flip()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get(): running = self.handle_event(event) and running
            now = pygame.time.get_ticks(); self.update(now)
            if self.state.screen == "title":
                self.draw_title(now)
            elif self.state.screen == "select":
                self.draw_select()
            else:
                self.draw_game(now)
            self.present(); self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    try:
        Game().run()
    except ModuleNotFoundError as error:
        if error.name == "pygame":
            print("pygame이 설치되지 않았습니다. requirements.txt를 설치해 주세요.")
        raise
