"""
Wave Orthorectification v8

핵심 전략 변경:
  v7까지: 마루 간격(파장) 기반으로 m/pixel 추정 → 너울/풍랑 구분 실패
  v8: 마루 이동속도 기반으로 m/pixel 추정 (primary)

이유:
  - 이동속도 방식은 마루가 너울이든 풍랑이든 상관없음
  - 마루 하나를 추적해서 "y좌표별 이동속도(px/sec)"를 측정하면,
    encounter_speed(m/s) / velocity(px/s) = m/pixel
  - 이건 파장을 몰라도, 너울/풍랑을 구분 못해도 성립
  - 필요한 가정: encounter speed가 일정 (SOG, 파도방향 일정)

파장 기반은 교차검증용으로만 사용.
"""

import cv2
import numpy as np
import os
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
from collections import defaultdict

# ============================================================
# 메타데이터
# ============================================================
SOG_KNOTS = 18.555
HEADING_DEG = 141.455
SWELL_HS = 2.485
SWELL_DIR = 150.179
SWELL_TP = 8.561
WIND_HS = 0.867
WIND_DIR = 128.615
WIND_TP = 3.993
G = 9.81

SWELL_WAVELENGTH = G * SWELL_TP**2 / (2 * np.pi)
WIND_WAVELENGTH = G * WIND_TP**2 / (2 * np.pi)
SWELL_PHASE_SPEED = SWELL_WAVELENGTH / SWELL_TP
WIND_PHASE_SPEED = WIND_WAVELENGTH / WIND_TP
ENCOUNTER_ANGLE_RAD = np.radians(SWELL_DIR - HEADING_DEG)
SOG_MS = SOG_KNOTS * 0.5144

# encounter speed: 너울 기준 (지배적이므로)
ENCOUNTER_SPEED_SWELL = SWELL_PHASE_SPEED + SOG_MS * np.cos(ENCOUNTER_ANGLE_RAD)
# 풍랑 기준
ENCOUNTER_SPEED_WIND = WIND_PHASE_SPEED + SOG_MS * np.cos(np.radians(WIND_DIR - HEADING_DEG))

SWELL_DOMINANCE = SWELL_HS / (SWELL_HS + WIND_HS)

CALIB_SECONDS = 20

# ============================================================
# ROI
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
    enh = clahe.apply(gray)
    sob = np.abs(cv2.Sobel(enh, cv2.CV_64F, 0, 1, ksize=3))
    prof = gaussian_filter1d(np.mean(sob, axis=1), sigma=2)
    std = np.std(prof)
    peaks, props = find_peaks(prof, distance=min_dist, prominence=max(std * 0.4, 1.0))
    return peaks, prof


# ============================================================
# 마루 추적기 (v8: 속도 측정에 특화)
# ============================================================
class CrestTracker:
    def __init__(self, max_disp=25):
        self.tracks = {}
        self.prev = {}
        self.nid = 0
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
        """
        각 트랙에서 구간별 속도를 추출.
        트랙이 길면 여러 구간으로 나눠서 (y, velocity) 데이터를 밀도 있게 수집.
        """
        results = []  # (y_position, px_per_sec)
        for tid, pts in self.tracks.items():
            if len(pts) < min_frames:
                continue
            arr = np.array(pts, dtype=np.float64)
            # 슬라이딩 윈도우로 국소 속도 측정
            win = max(min_frames, len(arr) // 4)
            for start in range(0, len(arr) - win + 1, win // 2):
                chunk = arr[start:start + win]
                dt = (chunk[-1, 0] - chunk[0, 0]) / fps
                if dt < 0.2:
                    continue
                dy = chunk[-1, 1] - chunk[0, 1]
                vel = dy / dt
                if vel > 1:  # 아래로 이동만
                    mean_y = np.mean(chunk[:, 1])
                    results.append((mean_y, vel))
        return results

    def get_long_tracks(self, min_len=10):
        return [np.array(p) for p in self.tracks.values() if len(p) >= min_len]


# ============================================================
# 속도 기반 스케일 맵
# ============================================================
def build_velocity_scale_map(vel_vs_y, roi_h, encounter_speed):
    """
    (y, px_per_sec) 데이터로부터 m/pixel(y) = encounter_speed / velocity(y)

    선형 회귀: velocity = a*y + b  (위쪽은 느리게, 아래쪽은 빠르게 이동)
    → m/pixel = encounter_speed / (a*y + b)
    """
    if len(vel_vs_y) < 20:
        return None, None, None

    data = np.array(vel_vs_y)
    ys, vels = data[:, 0], data[:, 1]

    # 이상치 제거
    q1, q3 = np.percentile(vels, [25, 75])
    iqr = q3 - q1
    mask = (vels > q1 - 1.5 * iqr) & (vels < q3 + 1.5 * iqr) & (vels > 1)
    ys, vels = ys[mask], vels[mask]

    if len(ys) < 20:
        return None, None, None

    # 선형 회귀: velocity(y) = a*y + b
    coeffs = np.polyfit(ys, vels, 1)
    poly = np.poly1d(coeffs)

    # R²
    pred = poly(ys)
    ss_res = np.sum((vels - pred)**2)
    ss_tot = np.sum((vels - np.mean(vels))**2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # 전체 y에 대한 velocity, m/pixel
    y_full = np.arange(roi_h, dtype=np.float64)
    vel_full = poly(y_full)
    vel_full = np.clip(vel_full, 1.0, None)  # 최소 1 px/s

    m_per_pixel = encounter_speed / vel_full

    print(f"   Linear fit: vel(y) = {coeffs[0]:.4f}*y + {coeffs[1]:.2f}  R2={r_sq:.3f}")
    print(f"   vel range: {vel_full[0]:.1f} (top) ~ {vel_full[-1]:.1f} px/s (bot)")
    print(f"   m/px range: {m_per_pixel[0]:.3f} (top) ~ {m_per_pixel[-1]:.3f} (bot)")
    print(f"   scale ratio: {m_per_pixel[0] / m_per_pixel[-1]:.2f}x")

    return y_full, m_per_pixel, r_sq


def build_remap_tables(roi_w, roi_h, m_per_pixel_map):
    """등거리 remap: 세로만 y좌표별 스케일 보정, 가로는 그대로 → 직사각형 출력"""
    base_mpp = m_per_pixel_map[-1]  # 하단 기준 (가장 정밀)

    cumulative = np.cumsum(m_per_pixel_map)
    total_dist = cumulative[-1]
    out_h = max(int(total_dist / base_mpp), roi_h)

    out_dist = np.linspace(0, total_dist, out_h)
    src_y = np.interp(out_dist, cumulative, np.arange(roi_h, dtype=np.float64))

    # map_x: 가로는 원본 그대로 (왜곡 없음)
    # map_y: 세로만 등거리 보정
    map_x = np.tile(np.arange(roi_w, dtype=np.float32), (out_h, 1))
    map_y = np.zeros((out_h, roi_w), dtype=np.float32)
    for row in range(out_h):
        map_y[row, :] = src_y[row]

    return map_x, map_y, out_h, base_mpp


# ============================================================
# 시각화
# ============================================================
def draw_scale_graph(m_per_pixel, vel_raw, roi_h, enc_speed, width=350):
    """스케일 맵 그래프: 흰선=회귀 결과, 초록점=개별 측정"""
    canvas = np.zeros((roi_h, width, 3), dtype=np.uint8)

    if m_per_pixel is not None:
        mpp = m_per_pixel[:roi_h]
        mn, mx = mpp.min(), mpp.max()
        margin = (mx - mn) * 0.1 + 0.001
        mn -= margin; mx += margin

        # 회귀 곡선 (흰색)
        norm = (mpp - mn) / (mx - mn) * (width - 40) + 20
        for i in range(1, len(norm)):
            cv2.line(canvas, (int(norm[i-1]), i-1), (int(norm[i]), i), (255,255,255), 2)

        # 개별 측정점 (초록)
        for y_pos, vel in vel_raw:
            if 0 <= y_pos < roi_h and vel > 0:
                mpp_pt = enc_speed / vel
                x = int((mpp_pt - mn) / (mx - mn) * (width - 40) + 20)
                x = int(np.clip(x, 2, width - 2))
                cv2.circle(canvas, (x, int(y_pos)), 2, (0, 180, 0), -1)

        cv2.putText(canvas, f"{m_per_pixel[0]:.3f} m/px (far)", (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)
        cv2.putText(canvas, f"{m_per_pixel[-1]:.3f} m/px (near)", (5, roi_h-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)

    cv2.putText(canvas, "m/pixel vs y (velocity-based)", (5, 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.32, (100,200,255), 1)
    cv2.putText(canvas, "white=fit  green=raw", (5, roi_h-22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.28, (150,150,150), 1)
    return canvas


def draw_info(img, lines, y0=20):
    for i, l in enumerate(lines):
        cv2.putText(img, l, (10, y0+i*20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,0), 1)


# ============================================================
# 메인
# ============================================================
def main():
    video_path = r"C:\Users\tilti\OneDrive\samjung\Swell_20260120_UTC1007\Swell_FWD_20260120_UTC1007.mp4"

    cap = open_video(video_path)
    if cap is None: return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ret, frame = cap.read()
    if not ret: print("X"); return
    frame = cv2.resize(frame, (1024, 576))
    clone = frame.copy()

    print("\n" + "=" * 60)
    print(f"  Swell: L={SWELL_WAVELENGTH:.1f}m T={SWELL_TP:.1f}s Hs={SWELL_HS:.1f}m c={SWELL_PHASE_SPEED:.1f}m/s")
    print(f"  Wind:  L={WIND_WAVELENGTH:.1f}m Hs={WIND_HS:.1f}m dom={SWELL_DOMINANCE:.0%}")
    print(f"  Ship:  SOG={SOG_MS:.1f}m/s  Enc(swell)={ENCOUNTER_SPEED_SWELL:.1f}m/s  Enc(wind)={ENCOUNTER_SPEED_WIND:.1f}m/s")
    print(f"  Video: {total_frames}f {total_frames/fps:.0f}s {fps:.0f}fps")
    print("=" * 60)

    # ---- ROI 선택 ----
    win = "Select ROI"
    cv2.imshow(win, clone); cv2.waitKey(1)
    cv2.setMouseCallback(win, select_roi)
    print("\n  Drag -> Enter | r=redo | q=quit\n")

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
    roi_w, roi_h = x2-x1, y2-y1
    if roi_w < 50 or roi_h < 50:
        print("X too small"); return

    # ============================================================
    # Phase 1: 캘리브레이션 - 마루 추적 → 속도 측정
    # ============================================================
    calib_n = int(fps * CALIB_SECONDS)
    tracker = CrestTracker(max_disp=int(roi_h * 0.1))

    print(f"\n  Phase 1: Tracking crests for {CALIB_SECONDS}s ({calib_n} frames)...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    cw = "Calibrating"
    cv2.imshow(cw, np.zeros((roi_h, roi_w, 3), dtype=np.uint8)); cv2.waitKey(1)

    for fi in range(calib_n):
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (1024, 576))
        gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

        crests, prof = detect_crests(gray)
        tracker.update(fi, crests)

        if fi % 5 == 0:
            vis = frame[y1:y2, x1:x2].copy()
            for cy in crests:
                cv2.line(vis, (0, cy), (roi_w, cy), (0,255,255), 1)
            # 긴 트랙 시각화
            for trk in tracker.get_long_tracks(5):
                for j in range(1, len(trk)):
                    py, cy2 = int(trk[j-1,1]), int(trk[j,1])
                    cv2.line(vis, (roi_w//2-3, py), (roi_w//2+3, cy2), (255,100,0), 1)
            pct = (fi+1)/calib_n
            cv2.rectangle(vis, (0,roi_h-6), (int(roi_w*pct), roi_h), (0,200,0), -1)
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
    print("\n  Building velocity-based scale map...")

    vel_vs_y = tracker.get_velocity_vs_y(fps, min_frames=8)
    print(f"   Velocity samples: {len(vel_vs_y)}")

    # 너울 encounter speed로 1차 시도
    y_full, mpp_map, r_sq = build_velocity_scale_map(
        vel_vs_y, roi_h, ENCOUNTER_SPEED_SWELL)

    # R²가 낮으면 풍랑 encounter speed로도 시도해서 비교
    if r_sq is not None and r_sq < 0.3:
        print(f"\n   R2={r_sq:.3f} low with swell enc. Trying wind enc...")
        y2_f, mpp2, r2_sq = build_velocity_scale_map(
            vel_vs_y, roi_h, ENCOUNTER_SPEED_WIND)
        if r2_sq is not None and r2_sq > r_sq:
            print(f"   Wind enc R2={r2_sq:.3f} > swell R2={r_sq:.3f} -> using wind encounter speed")
            y_full, mpp_map, r_sq = y2_f, mpp2, r2_sq
        else:
            print(f"   Wind enc not better. Keeping swell.")

    if mpp_map is not None and mpp_map[0] > mpp_map[-1]:
        # 정상: 상단(먼곳) > 하단(가까운곳)
        map_x, map_y, out_h, base_mpp = build_remap_tables(roi_w, roi_h, mpp_map)
        use_remap = True
        print(f"\n   Remap ready: {roi_w}x{out_h} (from {roi_w}x{roi_h})")
        print(f"   Output is {out_h/roi_h:.1f}x taller (equal m/pixel everywhere)")
        print(f"   Base resolution: {base_mpp:.3f} m/px")
    elif mpp_map is not None:
        print(f"\n   WARNING: m/px inverted (top < bottom). Data may be unreliable.")
        print(f"   Falling back to homography with measured ratio.")
        ratio = mpp_map[0] / mpp_map[-1] if mpp_map[-1] > 0 else 1.5
        ratio = max(ratio, 1.1)
        use_remap = False
        base_mpp = np.mean(mpp_map)
    else:
        print("   FAIL: not enough data -> homography fallback ratio=1.5")
        ratio = 1.5
        use_remap = False
        base_mpp = 0
        mpp_map = None

    # fallback 호모그래피
    if not use_remap:
        shrink = (1.0 - 1.0 / ratio) / 2.0
        mg = int(roi_w * shrink)
        out_h = int(roi_h * ratio)
        src = np.float32([[x1+mg,y1],[x2-mg,y1],[x1,y2],[x2,y2]])
        dst = np.float32([[0,0],[roi_w,0],[0,out_h],[roi_w,out_h]])
        fb_mat = cv2.getPerspectiveTransform(src, dst)
        print(f"   Homography fallback: ratio={ratio:.2f} out={roi_w}x{out_h}")

    # 스케일 그래프 (한 번)
    sg = draw_scale_graph(mpp_map, vel_vs_y, roi_h, ENCOUNTER_SPEED_SWELL)

    # ============================================================
    # Phase 2: 전체 재생 (remap만)
    # ============================================================
    print(f"\n  Phase 2: Playing back (q=quit)\n")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    ov = "Overlay"
    cv2.imshow(ov, np.zeros((100,100,3), dtype=np.uint8)); cv2.waitKey(1)
    cv2.createTrackbar("alpha%", ov, 50, 100, nothing)

    dmax = 800

    while True:
        ret, frame = cap.read()
        if not ret: print("  Done."); break
        frame = cv2.resize(frame, (1024, 576))
        roi = frame[y1:y2, x1:x2]

        if use_remap:
            warped = cv2.remap(roi, map_x, map_y, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
        else:
            warped = cv2.warpPerspective(frame, fb_mat, (roi_w, out_h))

        # 1. Original
        f1 = frame.copy()
        cv2.rectangle(f1, (x1,y1), (x2,y2), (0,255,0), 2)

        # 2. Ortho (세로로 길어진 등거리)
        if warped.shape[0] > dmax:
            ds = dmax / warped.shape[0]
            wd = cv2.resize(warped, (int(warped.shape[1]*ds), dmax))
        else:
            wd = warped.copy()
            ds = 1.0

        if base_mpp > 0 and wd.shape[0] > 50:
            bpx = int(50 / base_mpp * ds)
            bpx = min(bpx, wd.shape[1]-20)
            bh = wd.shape[0]
            cv2.line(wd, (10,bh-20), (10+bpx,bh-20), (0,255,0), 2)
            cv2.putText(wd, "50m", (10,bh-30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

        # 3. Overlay
        a = cv2.getTrackbarPos("alpha%", ov) / 100.0
        ovl = frame.copy()
        if warped.shape[0] > 0:
            wr = cv2.resize(warped, (roi_w, roi_h))
            ovl[y1:y2, x1:x2] = cv2.addWeighted(roi, 1-a, wr, a, 0)
        cv2.rectangle(ovl, (x1,y1), (x2,y2), (0,255,0), 1)
        draw_info(ovl, [
            f"Swell L={SWELL_WAVELENGTH:.0f}m Hs={SWELL_HS:.1f}m",
            f"Enc={ENCOUNTER_SPEED_SWELL:.1f}m/s  base={base_mpp:.3f}m/px",
            f"{'remap' if use_remap else 'homography'}  out={roi_w}x{out_h}",
        ])

        cv2.imshow("1 Original", f1)
        cv2.imshow("2 Ortho (equal m/px)", wd)
        cv2.imshow("3 Scale Map", sg)
        cv2.imshow(ov, ovl)

        if cv2.waitKey(max(1, int(1000/fps))) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()