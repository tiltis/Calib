"""
Wave Orthorectification v12

v11 → v12 변경사항:
  v11 전체 포함 (2차 회귀, cumsum fix, 단조성, out_h 상한, 코덱)
  + 신규:
  6. Relief Displacement 보정 (파고 기반 3D 보정)
     · 파도의 높이(crest +Hs/2, trough -Hs/2)로 인한 원근 변위를 프레임별 보정
     · 카메라 높이 H_CAMERA (기본 30m) + 파고 Hs로 계산
     · 수식: d_true = d_apparent × (H - h) / H
     · 파봉 검출 → sinusoidal 높이 프로파일 보간 → Δy 보정 remap 적용
  7. 보정 강도 슬라이더 (relief%) — 실시간 조절 가능
"""

import cv2
import numpy as np
import os
import json
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
import openpyxl

# ============================================================
# 경로 상수
# ============================================================
G            = 9.81
CALIB_SECONDS = 20
H_CAMERA     = 30.0    # 카메라 해수면 위 높이 [m] (선박 스펙에 맞게 조정)
XLSX_PATH    = r"C:\Users\tilti\OneDrive\samjung\Weather_Info.xlsx"
OUTPUT_DIR   = r"C:\Users\tilti\OneDrive\samjung\output"

# ============================================================
# xlsx 로딩
# ============================================================
def load_weather_params(xlsx_path, dir_name):
    """
    기상 파라미터 로드. 우선순위:
      1. weather_cache.json (xlsx 잠금 문제 방지)
      2. xlsx 임시 복사본
    """
    import json, shutil, tempfile

    # 1차: JSON 캐시 (xlsx가 Excel에 열려있어도 항상 읽힘)
    # piza3.py가 하위 폴더에 있을 수 있으므로 현재 폴더 + 상위 폴더 모두 탐색
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = None
    for _d in [_script_dir, os.path.dirname(_script_dir)]:
        _c = os.path.join(_d, "weather_cache.json")
        if os.path.exists(_c):
            cache_path = _c
            break
    if cache_path:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        if dir_name in cache:
            return cache[dir_name]

    # 2차: xlsx 직접 읽기 (임시 복사)
    try:
        tmp = os.path.join(tempfile.gettempdir(), "_weather_tmp.xlsx")
        shutil.copy2(xlsx_path, tmp)
        wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
        ws = wb.active
        headers = None
        result = None
        for row in ws.iter_rows(values_only=True):
            if headers is None:
                headers = row; continue
            if str(row[0]) == dir_name:
                p = dict(zip(headers, row))
                result = {
                    "sog_knots":   float(p["SOG[knots]"]),
                    "heading_deg": float(p["Heading"]),
                    "wind_hs":     float(p["significant_height_of_wind_waves"]),
                    "wind_dir":    float(p["mean_direction_of_wind_waves"]),
                    "wind_tp":     float(p["mean_period_of_wind_waves"]),
                    "swell_hs":    float(p["significant_height_of_total_swell"]),
                    "swell_dir":   float(p["mean_direction_of_total_swell"]),
                    "swell_tp":    float(p["mean_period_of_total_swell"]),
                }
                break
        wb.close()
        return result
    except Exception as e:
        print(f"  xlsx 읽기 실패: {e}")
        return None


def calc_wave_params(p):
    """
    기상 파라미터 딕셔너리로부터 파속, encounter speed 계산.

    encounter speed 선택 전략:
      dominance > 0.7  → swell enc (너울 지배)
      dominance < 0.3  → wind enc  (풍랑 지배)
      0.3 ~ 0.7        → weighted (혼합)
    """
    sog_ms   = p["sog_knots"] * 0.5144
    swell_wl = G * p["swell_tp"]**2 / (2 * np.pi)
    wind_wl  = G * p["wind_tp"]**2  / (2 * np.pi)
    swell_c  = swell_wl / p["swell_tp"]
    wind_c   = wind_wl  / p["wind_tp"]

    enc_swell = swell_c + sog_ms * np.cos(np.radians(p["swell_dir"] - p["heading_deg"]))
    enc_wind  = wind_c  + sog_ms * np.cos(np.radians(p["wind_dir"]  - p["heading_deg"]))

    dominance = (p["swell_hs"] / (p["swell_hs"] + p["wind_hs"])
                 if (p["swell_hs"] + p["wind_hs"]) > 0 else 0.5)

    # 지배 파계에 따라 1차 encounter speed 결정
    if dominance > 0.7:
        enc_primary = enc_swell
        enc_label   = f"swell (dom={dominance:.0%})"
    elif dominance < 0.3:
        enc_primary = enc_wind
        enc_label   = f"wind  (dom={dominance:.0%})"
    else:
        enc_primary = dominance * enc_swell + (1 - dominance) * enc_wind
        enc_label   = f"weighted (dom={dominance:.0%})"

    return {
        "sog_ms":      sog_ms,
        "swell_wl":    swell_wl,
        "wind_wl":     wind_wl,
        "swell_c":     swell_c,
        "wind_c":      wind_c,
        "enc_swell":   enc_swell,
        "enc_wind":    enc_wind,
        "enc_primary": enc_primary,
        "enc_label":   enc_label,
        "dominance":   dominance,
    }


# ============================================================
# ROI 선택
# ============================================================
roi_state = {"drawing": False, "start": None, "end": None, "selected": False}

def select_roi(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        roi_state.update({"drawing": True, "start": (x,y), "end": (x,y), "selected": False})
    elif event == cv2.EVENT_MOUSEMOVE and roi_state["drawing"]:
        roi_state["end"] = (x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        roi_state.update({"drawing": False, "end": (x,y), "selected": True})

def nothing(x): pass


# ============================================================
# 영상 열기
# ============================================================
def open_video(path):
    if not os.path.isfile(path):
        print(f"X not found: {path}"); return None
    for b, n in [(cv2.CAP_FFMPEG,"FFMPEG"),(cv2.CAP_MSMF,"MSMF"),
                  (cv2.CAP_DSHOW,"DSHOW"),(cv2.CAP_ANY,"ANY")]:
        c = cv2.VideoCapture(path, b)
        if c.isOpened():
            r, _ = c.read()
            if r: c.set(cv2.CAP_PROP_POS_FRAMES, 0); print(f"  [{n}] OK"); return c
            c.release()
        else: c.release()
    print("X all backends failed"); return None


# ============================================================
# 마루 검출
# ============================================================
def detect_crests(gray, min_dist=8):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enh   = clahe.apply(gray)
    sob   = np.abs(cv2.Sobel(enh, cv2.CV_64F, 0, 1, ksize=3))
    prof  = gaussian_filter1d(np.mean(sob, axis=1), sigma=2)
    std   = np.std(prof)
    peaks, _ = find_peaks(prof, distance=min_dist, prominence=max(std * 0.4, 1.0))
    return peaks, prof


# ============================================================
# 마루 추적기
# ============================================================
class CrestTracker:
    def __init__(self, max_disp=25):
        self.tracks   = {}
        self.prev     = {}
        self.nid      = 0
        self.max_disp = max_disp

    def update(self, fi, crests):
        mn, mo = set(), set()
        for tid, py in list(self.prev.items()):
            bi, bd = None, self.max_disp + 1
            for i, y in enumerate(crests):
                if i in mn: continue
                dy = y - py
                if -3 < dy <= self.max_disp and abs(dy) < bd:
                    bd = abs(dy); bi = i
            if bi is not None:
                self.tracks[tid].append((fi, crests[bi]))
                self.prev[tid] = crests[bi]
                mn.add(bi); mo.add(tid)
        for tid in set(self.prev) - mo:
            del self.prev[tid]
        for i, y in enumerate(crests):
            if i not in mn:
                self.tracks[self.nid] = [(fi, y)]
                self.prev[self.nid] = y
                self.nid += 1

    def get_velocity_vs_y(self, fps, min_frames=8):
        """각 트랙에서 슬라이딩 윈도우로 (y위치, px/sec) 추출"""
        results = []
        for tid, pts in self.tracks.items():
            if len(pts) < min_frames: continue
            arr = np.array(pts, dtype=np.float64)
            win = max(min_frames, len(arr) // 4)
            for start in range(0, len(arr) - win + 1, win // 2):
                chunk = arr[start:start + win]
                dt = (chunk[-1, 0] - chunk[0, 0]) / fps
                if dt < 0.2: continue
                vel = (chunk[-1, 1] - chunk[0, 1]) / dt
                if vel > 1:  # 아래 방향 이동만
                    results.append((np.mean(chunk[:, 1]), vel))
        return results

    def get_long_tracks(self, min_len=10):
        return [np.array(p) for p in self.tracks.values() if len(p) >= min_len]


# ============================================================
# 속도 기반 스케일 맵
# ============================================================
def build_velocity_scale_map(vel_vs_y, roi_h, encounter_speed):
    """
    (y, px/sec) 데이터로 m/pixel(y) = encounter_speed / velocity(y) 산출.
    1차/2차 다항식 중 R² 개선폭 기반 자동 선택.
    mpp 단조성 강제 (상단 ≥ 하단).
    """
    if len(vel_vs_y) < 20:
        return None, None, None

    data = np.array(vel_vs_y)
    ys, vels = data[:, 0], data[:, 1]

    # IQR 이상치 제거
    q1, q3 = np.percentile(vels, [25, 75])
    iqr  = q3 - q1
    mask = (vels > q1 - 1.5*iqr) & (vels < q3 + 1.5*iqr) & (vels > 1)
    ys, vels = ys[mask], vels[mask]
    if len(ys) < 20:
        return None, None, None

    def fit_and_score(degree):
        c = np.polyfit(ys, vels, degree)
        p = np.poly1d(c)
        pred = p(ys)
        ss_res = np.sum((vels - pred)**2)
        ss_tot = np.sum((vels - np.mean(vels))**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        return c, p, r2

    c1, p1, r1 = fit_and_score(1)
    c2, p2, r2 = fit_and_score(2)

    # 2차가 R²를 0.02 이상 개선하면 채택, 아니면 1차 유지
    if r2 - r1 >= 0.02:
        coeffs, poly, r_sq, deg = c2, p2, r2, 2
        print(f"   2차 회귀 채택 (R² {r1:.3f} → {r2:.3f}, +{r2-r1:.3f})")
    else:
        coeffs, poly, r_sq, deg = c1, p1, r1, 1
        print(f"   1차 회귀 유지 (2차 R² 개선 미미: +{r2-r1:.3f})")

    y_full    = np.arange(roi_h, dtype=np.float64)
    vel_full  = np.clip(poly(y_full), 1.0, None)
    mpp       = encounter_speed / vel_full

    # 단조성 강제: mpp는 위(먼곳)→아래(가까운곳) 감소해야 함
    # 누적 max를 뒤집어서 적용 → 위에서 아래로 비증가(non-increasing) 보장
    mpp = np.maximum.accumulate(mpp[::-1])[::-1]

    coeff_str = " + ".join(f"{c:.4f}*y^{deg-i}" if deg-i > 0 else f"{c:.2f}"
                           for i, c in enumerate(coeffs))
    print(f"   회귀(deg={deg}): vel(y) = {coeff_str}  R²={r_sq:.3f}")
    print(f"   속도 범위: {vel_full[0]:.1f}(상단) ~ {vel_full[-1]:.1f} px/s(하단)")
    print(f"   m/px 범위: {mpp[0]:.3f}(상단) ~ {mpp[-1]:.3f}(하단)")
    print(f"   스케일 비율: {mpp[0]/mpp[-1]:.2f}x")

    return y_full, mpp, r_sq


MAX_EXPAND = 3  # 출력 높이 상한 = roi_h × MAX_EXPAND

def build_remap_tables(roi_w, roi_h, mpp_map):
    """
    등거리 remap 테이블 생성 — XY 동시 보정 (v11)

    v10 대비 변경:
      - cumsum 앞에 0 삽입 → 상단 평탄 구간 제거
      - out_h 상한 = roi_h × MAX_EXPAND (과도한 확장 방지)
    """
    base_mpp   = mpp_map[-1]  # 하단 기준 (가장 가까운 곳, 가장 정밀)

    # 누적 거리: [0, mpp[0], mpp[0]+mpp[1], ...] — 0부터 시작
    cumulative = np.concatenate([[0], np.cumsum(mpp_map)])  # (roi_h+1,)
    row_centers = np.arange(roi_h + 1, dtype=np.float64) - 0.5
    row_centers[0] = 0  # 첫 원소 클램프

    total_dist = cumulative[-1]
    out_h      = max(int(total_dist / base_mpp), roi_h)
    out_h      = min(out_h, int(roi_h * MAX_EXPAND))  # 상한 제한

    out_dist = np.linspace(0, total_dist, out_h)
    src_y    = np.interp(out_dist, cumulative, row_centers)
    src_y    = np.clip(src_y, 0, roi_h - 1)

    # 각 출력 행의 m/pixel → 수평 스케일 팩터
    mpp_at_row = np.interp(src_y, np.arange(roi_h, dtype=np.float64), mpp_map)
    scale_x    = (mpp_at_row / base_mpp).astype(np.float32)  # (out_h,)

    # map_y: 세로 보정 (vectorized)
    map_y = np.tile(src_y.astype(np.float32).reshape(-1, 1), (1, roi_w))

    # map_x: 가로 보정 — cx 기준으로 scale_x만큼 압축
    cx    = roi_w / 2.0
    cols  = np.arange(roi_w, dtype=np.float32) - cx
    map_x = (cx + np.outer(1.0 / scale_x, cols)).astype(np.float32)

    return map_x, map_y, out_h, base_mpp


# ============================================================
# Relief Displacement 보정 (v12 신규)
# ============================================================
def build_height_profile(gray_roi, hs_total, roi_h):
    """
    프레임의 ROI에서 파봉/파곡 높이 프로파일 h(y) 생성.
    파봉 = +Hs/2, 파곡 = -Hs/2, 사이는 코사인 보간.
    반환: (roi_h,) 배열, 단위=m
    """
    amplitude = hs_total / 2.0

    crests, _ = detect_crests(gray_roi)
    if len(crests) < 2:
        return np.zeros(roi_h, dtype=np.float64)

    # 파봉=+A, 파곡(파봉 중간)=-A, 나머지는 코사인 보간
    h = np.zeros(roi_h, dtype=np.float64)
    for i in range(len(crests) - 1):
        y0, y1 = int(crests[i]), int(crests[i + 1])
        if y1 <= y0:
            continue
        # 코사인 프로파일: crest(+A) → trough(-A) → crest(+A)
        t = np.linspace(0, 2 * np.pi, y1 - y0, endpoint=False)
        h[y0:y1] = amplitude * np.cos(t)

    # 첫 파봉 위, 마지막 파봉 아래: 가장 가까운 파봉값으로 확장
    if crests[0] > 0:
        h[:int(crests[0])] = amplitude
    if crests[-1] < roi_h - 1:
        last = int(crests[-1])
        h[last:] = amplitude  # 파봉 위치이므로 +A

    return h


def compute_relief_delta_y(h_profile, mpp_map, H_cam, roi_h):
    """
    높이 프로파일 h(y)로부터 각 행의 y 보정량 Δy 계산.

    원리:
      d(y) = 누적 물리 거리 (하단=0 기준)
      파봉(h>0)은 카메라에 가까워 보임 → 실제보다 먼 행에 표시됨 → 아래로 이동 필요
      d_true = d_apparent × (H - h) / H
      Δy = y(d_true) - y (음수 = 위로, 양수 = 아래로)
    """
    # 누적 거리 (하단=0, 상단=total)
    mpp_flip = mpp_map[::-1]  # 하단→상단 순서
    cum_flip = np.concatenate([[0], np.cumsum(mpp_flip)])
    # y_indices: 하단(roi_h-1) → 상단(0)
    y_flip = np.arange(roi_h, -1, -1, dtype=np.float64)  # roi_h, ..., 0

    # 상단 기준 누적 거리로 변환
    cum_from_top = np.concatenate([[0], np.cumsum(mpp_map)])
    y_from_top = np.arange(roi_h + 1, dtype=np.float64)

    delta_y = np.zeros(roi_h, dtype=np.float64)
    for y in range(roi_h):
        d_apparent = cum_from_top[y + 1]  # 상단→y까지 누적 거리
        h = h_profile[y]
        if abs(h) < 0.01 or H_cam <= abs(h):
            continue
        d_true = d_apparent * (H_cam - h) / H_cam
        # d_true에 해당하는 소스 y 역산
        y_true = np.interp(d_true, cum_from_top, y_from_top)
        delta_y[y] = y_true - y

    return delta_y


def apply_relief_to_remap(map_y_static, delta_y_src, src_y_mapping, relief_strength=1.0):
    """
    정적 map_y에 relief delta를 더해 보정된 map_y 반환.
    delta_y_src: 소스 ROI 좌표계의 Δy (roi_h,)
    src_y_mapping: 각 출력 행이 참조하는 소스 y (out_h,)
    relief_strength: 보정 강도 (0~1, 슬라이더)
    """
    # 출력 행 → 소스 y → 해당 소스 y의 Δy 보간
    delta_out = np.interp(src_y_mapping, np.arange(len(delta_y_src)), delta_y_src)
    delta_out *= relief_strength

    # map_y에 delta 추가 (broadcast: delta_out은 (out_h,), map_y는 (out_h, roi_w))
    corrected = map_y_static + delta_out.astype(np.float32).reshape(-1, 1)
    return corrected


# ============================================================
# 시각화
# ============================================================
def draw_scale_graph(mpp_map, vel_raw, roi_h, enc_speed, width=350):
    """스케일 맵 그래프 (흰선=회귀, 초록점=측정값)"""
    canvas = np.zeros((roi_h, width, 3), dtype=np.uint8)
    if mpp_map is not None:
        mpp = mpp_map[:roi_h]
        mn, mx = mpp.min(), mpp.max()
        margin = (mx - mn) * 0.1 + 0.001
        mn -= margin; mx += margin
        norm = (mpp - mn) / (mx - mn) * (width - 40) + 20
        for i in range(1, len(norm)):
            cv2.line(canvas, (int(norm[i-1]), i-1), (int(norm[i]), i), (255,255,255), 2)
        for y_pos, vel in vel_raw:
            if 0 <= y_pos < roi_h and vel > 0:
                mpp_pt = enc_speed / vel
                x = int(np.clip((mpp_pt - mn) / (mx - mn) * (width-40) + 20, 2, width-2))
                cv2.circle(canvas, (x, int(y_pos)), 2, (0,180,0), -1)
        cv2.putText(canvas, f"{mpp_map[0]:.3f} m/px (far)",  (5,20),  cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)
        cv2.putText(canvas, f"{mpp_map[-1]:.3f} m/px (near)",(5,roi_h-8), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)
    cv2.putText(canvas, "m/pixel vs y (velocity)", (5,12),      cv2.FONT_HERSHEY_SIMPLEX, 0.32, (100,200,255), 1)
    cv2.putText(canvas, "white=fit  green=raw",    (5,roi_h-22),cv2.FONT_HERSHEY_SIMPLEX, 0.28, (150,150,150), 1)
    return canvas


def draw_info(img, lines, y0=20):
    for i, l in enumerate(lines):
        cv2.putText(img, l, (10, y0+i*20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,0), 1)


# ============================================================
# output 저장
# ============================================================
def save_calib_json(output_dir, dir_name, video_path, roi_rect,
                    r_sq, enc_speed, enc_label, base_mpp, use_remap,
                    out_size, weather_params, wave_params):
    """캘리브레이션 결과를 JSON으로 저장"""
    os.makedirs(output_dir, exist_ok=True)
    data = {
        "dir_name":   dir_name,
        "video":      os.path.basename(video_path),
        "roi":        list(roi_rect),
        "r_sq":       round(float(r_sq), 4) if r_sq is not None else None,
        "enc_speed":  round(float(enc_speed), 3),
        "enc_label":  enc_label,
        "base_mpp":   round(float(base_mpp), 4),
        "use_remap":  use_remap,
        "out_size":   list(out_size),
        "weather":    {k: round(float(v), 4) for k, v in weather_params.items()},
        "wave":       {k: (round(float(v), 4) if isinstance(v, float) else v)
                       for k, v in wave_params.items()},
    }
    out_path = os.path.join(output_dir, f"{dir_name}_calib.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [저장] 캘리브레이션 JSON → {out_path}")
    return out_path


# ============================================================
# 메인
# ============================================================
def main():
    video_path = r"C:\Users\tilti\OneDrive\samjung\data\Swell_20260120_UTC1007\Swell_FWD_20260120_UTC1007.mp4"

    # ---- 영상 폴더명으로 xlsx 파라미터 자동 로드 ----
    dir_name = os.path.basename(os.path.dirname(video_path))
    print(f"\n  Dir: {dir_name}")

    weather = load_weather_params(XLSX_PATH, dir_name)
    if weather is None:
        print(f"  경고: '{dir_name}'을 Weather_Info.xlsx에서 찾지 못했습니다.")
        print("  하드코딩 폴백값으로 진행합니다.")
        # 폴백: Swell_20260120_UTC1007 기본값
        weather = {
            "sog_knots": 18.555, "heading_deg": 141.455,
            "wind_hs": 0.867,    "wind_dir": 128.615, "wind_tp": 3.993,
            "swell_hs": 2.485,   "swell_dir": 150.179, "swell_tp": 8.561,
        }
    else:
        print(f"  SOG={weather['sog_knots']:.1f}kts  HDG={weather['heading_deg']:.1f}°"
              f"  Swell Hs={weather['swell_hs']:.2f}m Tp={weather['swell_tp']:.2f}s"
              f"  Wind Hs={weather['wind_hs']:.2f}m Tp={weather['wind_tp']:.2f}s")

    wave = calc_wave_params(weather)

    # ---- 영상 열기 ----
    cap = open_video(video_path)
    if cap is None: return

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret, frame = cap.read()
    if not ret: print("X 첫 프레임 읽기 실패"); return
    frame = cv2.resize(frame, (1024, 576))
    clone = frame.copy()

    print("\n" + "=" * 60)
    print(f"  Swell: λ={wave['swell_wl']:.1f}m  c={wave['swell_c']:.1f}m/s  Enc={wave['enc_swell']:.1f}m/s")
    print(f"  Wind:  λ={wave['wind_wl']:.1f}m   c={wave['wind_c']:.1f}m/s   Enc={wave['enc_wind']:.1f}m/s")
    print(f"  사용 Enc: {wave['enc_primary']:.2f}m/s  ({wave['enc_label']})")
    print(f"  SOG={wave['sog_ms']:.1f}m/s  Video={total_frames}f {total_frames/fps:.0f}s {fps:.0f}fps")
    print("=" * 60)

    # ---- ROI 선택 ----
    win = "Select ROI  (drag -> Enter | r=redo | q=quit)"
    cv2.imshow(win, clone); cv2.waitKey(1)
    cv2.setMouseCallback(win, select_roi)

    while True:
        d = clone.copy()
        if roi_state["start"] and roi_state["end"]:
            cv2.rectangle(d, roi_state["start"], roi_state["end"], (0,255,0), 2)
        cv2.imshow(win, d)
        k = cv2.waitKey(1) & 0xFF
        if k == 13 and roi_state["selected"]: break
        elif k == ord('r'): roi_state.update({"start":None,"end":None,"selected":False})
        elif k == ord('q'): cap.release(); cv2.destroyAllWindows(); return
    cv2.destroyWindow(win)

    x1 = min(roi_state["start"][0], roi_state["end"][0])
    y1 = min(roi_state["start"][1], roi_state["end"][1])
    x2 = max(roi_state["start"][0], roi_state["end"][0])
    y2 = max(roi_state["start"][1], roi_state["end"][1])
    roi_w, roi_h = x2 - x1, y2 - y1
    if roi_w < 50 or roi_h < 50:
        print("X ROI가 너무 작음"); return

    # ============================================================
    # Phase 1: 캘리브레이션 — 마루 추적 → 속도 측정
    # ============================================================
    calib_n = int(fps * CALIB_SECONDS)
    tracker = CrestTracker(max_disp=int(roi_h * 0.1))

    print(f"\n  Phase 1: {CALIB_SECONDS}s 마루 추적 ({calib_n} frames)...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    cw = "Calibrating..."
    cv2.imshow(cw, np.zeros((roi_h, roi_w, 3), dtype=np.uint8)); cv2.waitKey(1)

    for fi in range(calib_n):
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (1024, 576))
        gray  = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

        crests, _ = detect_crests(gray)
        tracker.update(fi, crests)

        if fi % 5 == 0:
            vis = frame[y1:y2, x1:x2].copy()
            for cy in crests:
                cv2.line(vis, (0,cy), (roi_w,cy), (0,255,255), 1)
            for trk in tracker.get_long_tracks(5):
                for j in range(1, len(trk)):
                    py, cy2 = int(trk[j-1,1]), int(trk[j,1])
                    cv2.line(vis, (roi_w//2-3,py), (roi_w//2+3,cy2), (255,100,0), 1)
            pct = (fi+1) / calib_n
            cv2.rectangle(vis, (0,roi_h-6), (int(roi_w*pct),roi_h), (0,200,0), -1)
            nt = len(tracker.get_long_tracks(8))
            cv2.putText(vis, f"{fi+1}/{calib_n} ({pct:.0%}) tracks={nt}",
                        (5,16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1)
            cv2.imshow(cw, vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release(); cv2.destroyAllWindows(); return

    cv2.destroyWindow(cw)

    # ============================================================
    # 속도 기반 스케일 맵 구축
    # ============================================================
    print("\n  스케일 맵 구축 중...")
    vel_vs_y = tracker.get_velocity_vs_y(fps, min_frames=8)
    print(f"   속도 샘플 수: {len(vel_vs_y)}")

    # 지배 파계 기반 encounter speed로 1차 시도
    enc_used  = wave["enc_primary"]
    enc_label = wave["enc_label"]
    y_full, mpp_map, r_sq = build_velocity_scale_map(vel_vs_y, roi_h, enc_used)

    # R² < 0.3이면 다른 enc speed로 재시도 (swell/wind 중 아직 안 쓴 것)
    # 주의: R²는 enc speed와 무관하므로 재시도해도 R²는 같음
    # → enc_speed만 바꿔서 m/pixel 절대값 재계산 (R² 기준이 아닌 dominance 기반)
    if r_sq is not None and r_sq < 0.3:
        print(f"   경고: R²={r_sq:.3f} 낮음. 파봉 추적 품질 확인 필요.")

    if mpp_map is not None and mpp_map[0] > mpp_map[-1]:
        # 정상: 상단(먼쪽) m/px > 하단(가까운쪽)
        map_x, map_y, out_h, base_mpp = build_remap_tables(roi_w, roi_h, mpp_map)
        use_remap = True
        print(f"\n  Remap 준비 완료: {roi_w}x{out_h} (원본 {roi_w}x{roi_h})")
        print(f"  세로 {out_h/roi_h:.1f}배 확장, 기준 해상도: {base_mpp:.3f} m/px")
    elif mpp_map is not None:
        # 비정상 (상하 반전) → homography fallback
        print("   경고: m/px 상하 반전. Homography fallback으로 전환.")
        ratio     = max(mpp_map[0] / mpp_map[-1] if mpp_map[-1] > 0 else 1.5, 1.1)
        use_remap = False
        base_mpp  = float(np.mean(mpp_map))
    else:
        # 샘플 부족 → fallback
        print("   FAIL: 샘플 부족 → homography fallback (ratio=1.5)")
        ratio     = 1.5
        use_remap = False
        base_mpp  = 0.0
        mpp_map   = None

    # Homography fallback 행렬 계산
    if not use_remap:
        shrink = (1.0 - 1.0 / ratio) / 2.0
        mg     = int(roi_w * shrink)
        out_h  = int(roi_h * ratio)
        src    = np.float32([[x1+mg,y1],[x2-mg,y1],[x1,y2],[x2,y2]])
        dst    = np.float32([[0,0],[roi_w,0],[0,out_h],[roi_w,out_h]])
        fb_mat = cv2.getPerspectiveTransform(src, dst)
        print(f"   Homography fallback: ratio={ratio:.2f} out={roi_w}x{out_h}")

    # ---- 캘리브레이션 결과 JSON 저장 ----
    save_calib_json(
        OUTPUT_DIR, dir_name, video_path,
        roi_rect  = [x1, y1, x2, y2],
        r_sq      = r_sq,
        enc_speed = enc_used,
        enc_label = enc_label,
        base_mpp  = base_mpp,
        use_remap = use_remap,
        out_size  = [roi_w, out_h],
        weather_params = weather,
        wave_params    = wave,
    )

    # 스케일 그래프 (정적, 1회 생성)
    sg = draw_scale_graph(mpp_map, vel_vs_y, roi_h, enc_used)

    # ---- Relief displacement 준비 (v12) ----
    # 합성 Hs = sqrt(swell_hs² + wind_hs²)
    hs_total = np.sqrt(weather["swell_hs"]**2 + weather["wind_hs"]**2)
    relief_enabled = use_remap and mpp_map is not None and hs_total > 0.1
    if relief_enabled:
        # src_y 매핑 (build_remap_tables에서 이미 계산된 것을 재구성)
        cumulative_r = np.concatenate([[0], np.cumsum(mpp_map)])
        row_centers_r = np.arange(roi_h + 1, dtype=np.float64) - 0.5
        row_centers_r[0] = 0
        total_dist_r = cumulative_r[-1]
        out_dist_r = np.linspace(0, total_dist_r, out_h)
        src_y_mapping = np.interp(out_dist_r, cumulative_r, row_centers_r)
        src_y_mapping = np.clip(src_y_mapping, 0, roi_h - 1)

        # 정적 map_y 보존 (relief 적용 전 원본)
        map_y_static = map_y.copy()
        print(f"\n  Relief Displacement 활성: Hs={hs_total:.2f}m, H_cam={H_CAMERA:.0f}m")
        print(f"  예상 최대 변위: ~{hs_total/2 * 100 / H_CAMERA:.0f}m ({hs_total/2 * 100 / (H_CAMERA * base_mpp):.0f}px)")
    else:
        map_y_static = None
        if use_remap:
            print(f"\n  Relief Displacement 비활성 (Hs={hs_total:.2f}m 미미)")

    # ============================================================
    # Phase 2: 전체 재생 + 영상 저장
    # ============================================================
    print(f"\n  Phase 2: 재생 중  (q=종료 | s=저장 토글)\n")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    ov = "Overlay"
    cv2.imshow(ov, np.zeros((100,100,3), dtype=np.uint8)); cv2.waitKey(1)
    cv2.createTrackbar("alpha%", ov, 50, 100, nothing)
    if relief_enabled:
        cv2.createTrackbar("relief%", ov, 100, 100, nothing)

    # 영상 저장 설정 — H264 우선, 실패 시 mp4v 폴백
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_video_path = os.path.join(OUTPUT_DIR, f"{dir_name}_ortho.mp4")
    writer = None
    for codec in ["avc1", "H264", "X264", "mp4v"]:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(out_video_path, fourcc, fps, (roi_w, out_h))
        if writer.isOpened():
            print(f"  [코덱] {codec} 사용")
            break
        writer.release()
        writer = None
    if writer is None:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_video_path, fourcc, fps, (roi_w, out_h))
        print(f"  [코덱] mp4v 폴백")
    is_saving = True   # 기본 저장 ON
    print(f"  [저장] 등거리 투영 영상 → {out_video_path}")

    dmax = 800

    while True:
        ret, frame = cap.read()
        if not ret: print("  완료."); break
        frame = cv2.resize(frame, (1024, 576))
        roi   = frame[y1:y2, x1:x2]

        # 등거리 투영 + relief displacement 보정
        if use_remap:
            if relief_enabled:
                relief_pct = cv2.getTrackbarPos("relief%", ov) / 100.0
                gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                h_profile = build_height_profile(gray_roi, hs_total, roi_h)
                delta_y = compute_relief_delta_y(h_profile, mpp_map, H_CAMERA, roi_h)
                map_y_corrected = apply_relief_to_remap(
                    map_y_static, delta_y, src_y_mapping, relief_pct)
                warped = cv2.remap(roi, map_x, map_y_corrected, cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
            else:
                warped = cv2.remap(roi, map_x, map_y, cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
        else:
            warped = cv2.warpPerspective(frame, fb_mat, (roi_w, out_h))

        # 영상 저장
        if is_saving and writer is not None:
            writer.write(warped)

        # --- 1. 원본 ---
        f1 = frame.copy()
        cv2.rectangle(f1, (x1,y1), (x2,y2), (0,255,0), 2)

        # --- 2. 등거리 투영 (표시용 리사이즈) ---
        if warped.shape[0] > dmax:
            ds = dmax / warped.shape[0]
            wd = cv2.resize(warped, (int(warped.shape[1]*ds), dmax))
        else:
            wd = warped.copy()
            ds = 1.0

        if base_mpp > 0 and wd.shape[0] > 50:
            bpx = min(int(50 / base_mpp * ds), wd.shape[1] - 20)
            bh  = wd.shape[0]
            cv2.line(wd, (10,bh-20), (10+bpx,bh-20), (0,255,0), 2)
            cv2.putText(wd, "50m", (10,bh-30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

        # --- 3. Overlay ---
        a   = cv2.getTrackbarPos("alpha%", ov) / 100.0
        ovl = frame.copy()
        if warped.shape[0] > 0:
            wr = cv2.resize(warped, (roi_w, roi_h))
            ovl[y1:y2, x1:x2] = cv2.addWeighted(roi, 1-a, wr, a, 0)
        cv2.rectangle(ovl, (x1,y1), (x2,y2), (0,255,0), 1)

        # 저장 상태 표시
        save_tag = "REC" if is_saving else "---"
        relief_info = ""
        if relief_enabled:
            rp = cv2.getTrackbarPos("relief%", ov)
            relief_info = f"  relief={rp}% Hs={hs_total:.1f}m H={H_CAMERA:.0f}m"
        draw_info(ovl, [
            f"Swell λ={wave['swell_wl']:.0f}m Hs={weather['swell_hs']:.1f}m",
            f"Enc={enc_used:.1f}m/s  base={base_mpp:.3f}m/px",
            (f"{'remap' if use_remap else 'homography'}  R²={r_sq:.3f}"
             if r_sq is not None else f"{'remap' if use_remap else 'homography'}")
            + relief_info,
            f"[{save_tag}] s=저장토글",
        ])

        cv2.imshow("1 Original", f1)
        cv2.imshow("2 Ortho (equal m/px)", wd)
        cv2.imshow("3 Scale Map", sg)
        cv2.imshow(ov, ovl)

        k = cv2.waitKey(max(1, int(1000/fps))) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('s'):
            is_saving = not is_saving
            print(f"  저장 {'ON' if is_saving else 'OFF'}")

    if writer is not None:
        writer.release()
        if is_saving:
            print(f"  [완료] {out_video_path}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
