"""
Wave Orthorectification v4 - 사다리꼴→직사각형 변환 시각화 추가

변경점 (v3 → v4):
  - 6번 창: 원본 위에 사다리꼴(빨강) + 직사각형(초록) 매핑을 시각적으로 보여줌
  - 변환 전후 꼭짓점 번호, 화살표로 어떻게 펴지는지 표현
"""

import cv2
import numpy as np
import os
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d

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
ENCOUNTER_ANGLE_DEG = SWELL_DIR - HEADING_DEG
SOG_MS = SOG_KNOTS * 0.5144

roi_state = {
    "drawing": False,
    "start": None,
    "end": None,
    "selected": False
}


def select_roi(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        roi_state["drawing"] = True
        roi_state["start"] = (x, y)
        roi_state["end"] = (x, y)
        roi_state["selected"] = False
    elif event == cv2.EVENT_MOUSEMOVE:
        if roi_state["drawing"]:
            roi_state["end"] = (x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        roi_state["drawing"] = False
        roi_state["end"] = (x, y)
        roi_state["selected"] = True


def nothing(x):
    pass


def open_video(video_path):
    if not os.path.isfile(video_path):
        print(f"❌ 파일이 존재하지 않습니다: {video_path}")
        return None
    backends = [
        (cv2.CAP_FFMPEG, "FFMPEG"),
        (cv2.CAP_MSMF, "MSMF"),
        (cv2.CAP_DSHOW, "DSHOW"),
        (cv2.CAP_ANY, "ANY"),
    ]
    for backend, name in backends:
        cap = cv2.VideoCapture(video_path, backend)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                print(f"✅ [{name}] 백엔드로 영상 열기 성공!")
                return cap
            cap.release()
        else:
            cap.release()
        print(f"⚠️ [{name}] 백엔드 실패...")
    print("❌ 모든 백엔드 실패.")
    return None


def detect_crests_sobel(gray_strip, min_distance=12):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_strip)
    sobel_y = cv2.Sobel(enhanced, cv2.CV_64F, 0, 1, ksize=3)
    sobel_abs = np.abs(sobel_y)
    profile = np.mean(sobel_abs, axis=1)
    profile_smooth = gaussian_filter1d(profile, sigma=2)
    std = np.std(profile_smooth)
    prominence = max(std * 0.5, 1.0)
    peaks, _ = find_peaks(profile_smooth, distance=min_distance, prominence=prominence)
    return peaks, profile_smooth, enhanced


def estimate_pixel_scale(crests_top, crests_bot):
    if len(crests_top) < 2 or len(crests_bot) < 2:
        return None, None, None
    gaps_top = np.diff(crests_top)
    gaps_bot = np.diff(crests_bot)
    mean_gap_top = np.median(gaps_top)
    mean_gap_bot = np.median(gaps_bot)
    if mean_gap_top < 1:
        return None, None, None
    ratio = mean_gap_bot / mean_gap_top
    return mean_gap_top, mean_gap_bot, ratio


def compute_ortho_matrix_isometric(x1, y1, x2, y2, roi_w, roi_h, scale_ratio):
    shrink = (1.0 - 1.0 / scale_ratio) / 2.0
    margin = int(roi_w * shrink)
    out_h = int(roi_h * scale_ratio)
    out_w = roi_w

    src_pts = np.float32([
        [x1 + margin, y1],
        [x2 - margin, y1],
        [x1, y2],
        [x2, y2]
    ])
    dst_pts = np.float32([
        [0, 0],
        [out_w, 0],
        [0, out_h],
        [out_w, out_h]
    ])

    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return matrix, margin, out_w, out_h, src_pts, dst_pts


def draw_transform_diagram(frame, src_pts, roi_rect, scale_ratio, margin, out_w, out_h):
    """
    사다리꼴(src) → 직사각형(dst) 변환 과정을 한 이미지에 시각화.
    왼쪽: 원본 + 사다리꼴(빨강) + ROI(초록점선)
    오른쪽: 펼쳐진 직사각형(초록)
    가운데: 화살표로 매핑 표시
    """
    h_frame, w_frame = frame.shape[:2]
    x1, y1, x2, y2 = roi_rect

    # 캔버스: 원본 프레임 2개 나란히 + 중간 여백
    gap = 80
    canvas_w = w_frame * 2 + gap
    canvas_h = max(h_frame, out_h + 40) + 60  # 여유 공간
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8) + 30  # 어두운 배경

    # ===== 왼쪽: 원본 프레임 =====
    left_x = 0
    left_y = 30
    canvas[left_y:left_y + h_frame, left_x:left_x + w_frame] = frame

    # ROI 직사각형 (초록 점선 효과 - 실선으로 대체)
    cv2.rectangle(canvas,
                  (left_x + x1, left_y + y1),
                  (left_x + x2, left_y + y2),
                  (0, 255, 0), 1)
    cv2.putText(canvas, "ROI (user drag)", (left_x + x1, left_y + y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    # 사다리꼴 (빨강, 두껍게)
    trap_pts = []
    for pt in src_pts:
        trap_pts.append([int(left_x + pt[0]), int(left_y + pt[1])])
    trap_pts_np = np.array(trap_pts, dtype=np.int32)

    # 사다리꼴 순서: 0=좌상, 1=우상, 2=좌하, 3=우하 → 폴리곤으로 연결
    poly_order = [0, 1, 3, 2]  # 시계방향
    poly = trap_pts_np[poly_order].reshape((-1, 1, 2))
    cv2.polylines(canvas, [poly], True, (0, 0, 255), 2)

    # 반투명 사다리꼴 채우기
    overlay = canvas.copy()
    cv2.fillPoly(overlay, [poly], (0, 0, 120))
    cv2.addWeighted(overlay, 0.3, canvas, 0.7, 0, canvas)

    # 꼭짓점 번호 표시
    labels_src = ["1:LT(far)", "2:RT(far)", "3:LB(near)", "4:RB(near)"]
    colors_src = [(100, 100, 255)] * 4
    for i, (pt, label) in enumerate(zip(trap_pts, labels_src)):
        cv2.circle(canvas, tuple(pt), 6, colors_src[i], -1)
        offset_x = -70 if i % 2 == 0 else 10
        offset_y = -10 if i < 2 else 20
        cv2.putText(canvas, label, (pt[0] + offset_x, pt[1] + offset_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, colors_src[i], 1)

    # 마진 화살표 (상단 좌우에서 안쪽으로 margin만큼)
    if margin > 5:
        # 좌상단 마진 표시
        arr_y = left_y + y1 + 15
        cv2.arrowedLine(canvas,
                        (left_x + x1, arr_y),
                        (left_x + x1 + margin, arr_y),
                        (0, 200, 255), 1, tipLength=0.3)
        cv2.putText(canvas, f"{margin}px", (left_x + x1 + 2, arr_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 200, 255), 1)
        # 우상단 마진 표시
        cv2.arrowedLine(canvas,
                        (left_x + x2, arr_y),
                        (left_x + x2 - margin, arr_y),
                        (0, 200, 255), 1, tipLength=0.3)
        cv2.putText(canvas, f"{margin}px", (left_x + x2 - margin - 30, arr_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 200, 255), 1)

    cv2.putText(canvas, "ORIGINAL (trapezoid = src)", (left_x + 10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1)

    # ===== 오른쪽: 등거리 직사각형 =====
    right_x = w_frame + gap
    right_y = 30

    # 직사각형 영역 (초록)
    # 출력 크기가 클 수 있으니 스케일 조정
    disp_scale = min(1.0, (canvas_h - 80) / out_h, w_frame / out_w)
    disp_w = int(out_w * disp_scale)
    disp_h = int(out_h * disp_scale)

    cv2.rectangle(canvas,
                  (right_x, right_y),
                  (right_x + disp_w, right_y + disp_h),
                  (0, 255, 0), 2)

    # 반투명 초록 채우기
    overlay2 = canvas.copy()
    cv2.rectangle(overlay2, (right_x, right_y),
                  (right_x + disp_w, right_y + disp_h), (0, 80, 0), -1)
    cv2.addWeighted(overlay2, 0.2, canvas, 0.8, 0, canvas)

    # 꼭짓점 번호 (직사각형)
    dst_disp = [
        (right_x, right_y),
        (right_x + disp_w, right_y),
        (right_x, right_y + disp_h),
        (right_x + disp_w, right_y + disp_h)
    ]
    labels_dst = ["1'", "2'", "3'", "4'"]
    for i, (pt, label) in enumerate(zip(dst_disp, labels_dst)):
        cv2.circle(canvas, pt, 6, (0, 255, 0), -1)
        cv2.putText(canvas, label, (pt[0] + 8, pt[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    # 크기 표시
    cv2.putText(canvas, f"{out_w}px", (right_x + disp_w // 2 - 20, right_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
    cv2.putText(canvas, f"{out_h}px", (right_x + disp_w + 5, right_y + disp_h // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
    cv2.putText(canvas, f"(x{scale_ratio:.2f} tall)", (right_x + disp_w + 5, right_y + disp_h // 2 + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

    cv2.putText(canvas, "ORTHO (rectangle = dst)", (right_x, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)

    # ===== 가운데: 매핑 화살표 =====
    arrow_color = (255, 255, 100)
    for i in range(4):
        src_pt = trap_pts[i]
        dst_pt = dst_disp[i]
        # 화살표 시작/끝
        start = (min(src_pt[0] + 20, w_frame - 5), src_pt[1])
        end = (max(dst_pt[0] - 20, w_frame + gap + 5), dst_pt[1])
        cv2.arrowedLine(canvas, start, end, arrow_color, 1, tipLength=0.05)

    cv2.putText(canvas, "Homography", (w_frame + 5, canvas_h // 2 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, arrow_color, 1)
    cv2.putText(canvas, "Transform", (w_frame + 5, canvas_h // 2 + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, arrow_color, 1)

    # ===== 하단: 설명 텍스트 =====
    txt_y = canvas_h - 35
    cv2.putText(canvas,
                f"Red trapezoid: camera sees far side narrower (margin={margin}px each side)",
                (10, txt_y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    cv2.putText(canvas,
                f"Green rect: stretched to equal m/pixel everywhere (ratio={scale_ratio:.2f})",
                (10, txt_y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

    return canvas


def draw_profile_image(profile, peaks, width=200, height=None, label=""):
    if height is None:
        height = len(profile)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    p = profile.copy()
    p_min, p_max = p.min(), p.max()
    if p_max - p_min > 0:
        p_norm = (p - p_min) / (p_max - p_min) * (width - 20) + 10
    else:
        p_norm = np.ones_like(p) * (width // 2)
    for i in range(1, len(p_norm)):
        cv2.line(canvas, (int(p_norm[i-1]), i-1), (int(p_norm[i]), i), (200, 200, 200), 1)
    for pk in peaks:
        if pk < height:
            cv2.circle(canvas, (int(p_norm[pk]), pk), 4, (0, 0, 255), -1)
            cv2.line(canvas, (0, pk), (width, pk), (0, 100, 255), 1)
    if label:
        cv2.putText(canvas, label, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    return canvas


def draw_info_panel(img, info_dict, start_y=20):
    y = start_y
    for key, val in info_dict.items():
        cv2.putText(img, f"{key}: {val}", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        y += 22
    return img


def main():
    video_path = r"C:\Users\tilti\OneDrive\samjung\Swell_20260120_UTC1007\Swell_FWD_20260120_UTC1007.mp4"

    cap = open_video(video_path)
    if cap is None:
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    ret, frame = cap.read()
    if not ret:
        print("❌ 첫 프레임을 읽을 수 없습니다.")
        return

    frame = cv2.resize(frame, (1024, 576))
    clone = frame.copy()

    print("\n" + "=" * 60)
    print(f"🌊 너울 파장: {SWELL_WAVELENGTH:.1f} m (T={SWELL_TP:.2f}s)")
    print(f"🚢 SOG: {SOG_KNOTS:.1f} kn | Heading: {HEADING_DEG:.1f}°")
    print(f"📐 입사각: {ENCOUNTER_ANGLE_DEG:.1f}°")
    print("=" * 60)

    # ============================================================
    # ROI 선택
    # ============================================================
    window_name = "Drag to select sea area, then press Enter"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, select_roi)
    print("\n🖱️ 해수면 드래그 → Enter | r: 다시 | q: 종료\n")

    while True:
        display = clone.copy()
        if roi_state["start"] is not None and roi_state["end"] is not None:
            cv2.rectangle(display, roi_state["start"], roi_state["end"], (0, 255, 0), 2)
            w_show = abs(roi_state["end"][0] - roi_state["start"][0])
            h_show = abs(roi_state["end"][1] - roi_state["start"][1])
            lbl = (min(roi_state["start"][0], roi_state["end"][0]),
                   min(roi_state["start"][1], roi_state["end"][1]) - 10)
            cv2.putText(display, f"{w_show}x{h_show}", lbl,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow(window_name, display)
        key = cv2.waitKey(1) & 0xFF
        if key == 13 and roi_state["selected"]:
            break
        elif key == ord('r'):
            roi_state["start"] = None
            roi_state["end"] = None
            roi_state["selected"] = False
        elif key == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            return

    cv2.destroyWindow(window_name)

    x1 = min(roi_state["start"][0], roi_state["end"][0])
    y1 = min(roi_state["start"][1], roi_state["end"][1])
    x2 = max(roi_state["start"][0], roi_state["end"][0])
    y2 = max(roi_state["start"][1], roi_state["end"][1])
    roi_w = x2 - x1
    roi_h = y2 - y1

    if roi_w < 30 or roi_h < 30:
        print("❌ 영역이 너무 작습니다.")
        return

    # ============================================================
    # 마루 검출 → 원근 비율 → 호모그래피
    # ============================================================
    gray_roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    half_h = roi_h // 2

    crests_top, _, _ = detect_crests_sobel(gray_roi[:half_h, :])
    crests_bot, _, _ = detect_crests_sobel(gray_roi[half_h:, :])

    print(f"\n🔍 마루: 상단 {len(crests_top)}개, 하단 {len(crests_bot)}개")

    mean_gap_top, mean_gap_bot, scale_ratio = estimate_pixel_scale(crests_top, crests_bot)

    if scale_ratio is None or scale_ratio < 1.05 or scale_ratio > 5.0:
        print(f"⚠️ 불확실 (ratio={scale_ratio}) → 기본 1.5")
        scale_ratio = 1.5
        mean_gap_top = mean_gap_top or 0
        mean_gap_bot = mean_gap_bot or 0
    else:
        print(f"✅ 간격: 상단 {mean_gap_top:.1f}px / 하단 {mean_gap_bot:.1f}px")
        print(f"✅ 원근 비율: {scale_ratio:.2f}")

    m_per_pixel = SWELL_WAVELENGTH / mean_gap_bot if mean_gap_bot and mean_gap_bot > 0 else 0

    matrix, margin, out_w, out_h, src_pts, dst_pts = compute_ortho_matrix_isometric(
        x1, y1, x2, y2, roi_w, roi_h, scale_ratio
    )

    print(f"📐 출력: {out_w}x{out_h} (세로 {scale_ratio:.2f}배)")

    # ============================================================
    # 6번 창: 변환 다이어그램 (정적, 한 번만 생성)
    # ============================================================
    diagram = draw_transform_diagram(
        frame, src_pts, (x1, y1, x2, y2), scale_ratio, margin, out_w, out_h
    )
    # 다이어그램이 너무 크면 리사이즈
    max_diag_w = 1400
    if diagram.shape[1] > max_diag_w:
        s = max_diag_w / diagram.shape[1]
        diagram = cv2.resize(diagram, (max_diag_w, int(diagram.shape[0] * s)))

    cv2.imshow("6. Transform Diagram (trapezoid -> rectangle)", diagram)

    print(f"\n🌊 재생 중... (q: 종료)\n")

    # ============================================================
    # 실시간 재생
    # ============================================================
    overlay_win = "5. Overlay (alpha)"
    cv2.namedWindow(overlay_win)
    cv2.createTrackbar("alpha %", overlay_win, 50, 100, nothing)

    # 오버레이용 행렬 (원본 크기)
    shrink_ov = (1.0 - 1.0 / scale_ratio) / 2.0
    mg_ov = int(roi_w * shrink_ov)
    src_ov = np.float32([[x1+mg_ov, y1], [x2-mg_ov, y1], [x1, y2], [x2, y2]])
    dst_ov = np.float32([[0, 0], [roi_w, 0], [0, roi_h], [roi_w, roi_h]])
    mat_ov = cv2.getPerspectiveTransform(src_ov, dst_ov)
    mat_ov_inv = np.linalg.inv(mat_ov)

    h_full, w_full = 576, 1024

    while True:
        ret, frame = cap.read()
        if not ret:
            print("✅ 영상 끝.")
            break

        frame = cv2.resize(frame, (1024, 576))
        roi_frame = frame[y1:y2, x1:x2]

        # --- 등거리 와핑 ---
        warped = cv2.warpPerspective(frame, matrix, (out_w, out_h))

        # --- 마루 검출 ---
        gray_cur = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
        cr_t, pf_t, _ = detect_crests_sobel(gray_cur[:half_h, :])
        cr_b, pf_b, _ = detect_crests_sobel(gray_cur[half_h:, :])

        crest_vis = roi_frame.copy()
        for cy in cr_t:
            cv2.line(crest_vis, (0, cy), (roi_w, cy), (255, 100, 0), 1)
        for cy in cr_b:
            cv2.line(crest_vis, (0, half_h + cy), (roi_w, half_h + cy), (0, 0, 255), 1)
        cv2.line(crest_vis, (0, half_h), (roi_w, half_h), (0, 255, 255), 1)
        cv2.putText(crest_vis, f"TOP:{len(cr_t)} BOT:{len(cr_b)}", (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        # 프로파일
        prof_t = draw_profile_image(pf_t, cr_t, width=200, height=half_h, label="TOP")
        prof_b = draw_profile_image(pf_b, cr_b, width=200, height=roi_h - half_h, label="BOT")
        prof_combined = np.vstack((prof_t, prof_b))

        # --- 오버레이 ---
        warped_ov = cv2.warpPerspective(frame, mat_ov, (roi_w, roi_h))
        warped_back = cv2.warpPerspective(warped_ov, mat_ov_inv, (w_full, h_full))
        mask_white = np.ones((roi_h, roi_w, 3), dtype=np.uint8) * 255
        mask = cv2.warpPerspective(mask_white, mat_ov_inv, (w_full, h_full))
        mask_bin = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY) > 127

        alpha_pct = cv2.getTrackbarPos("alpha %", overlay_win)
        alpha = alpha_pct / 100.0
        overlay = frame.copy()
        blended = cv2.addWeighted(frame, 1.0 - alpha, warped_back, alpha, 0)
        overlay[mask_bin] = blended[mask_bin]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 1)

        info = {
            "Swell": f"L={SWELL_WAVELENGTH:.0f}m T={SWELL_TP:.1f}s",
            "Scale": f"{scale_ratio:.2f}x margin=+/-{margin}px",
            "Res": f"{m_per_pixel:.2f} m/px" if m_per_pixel > 0 else "N/A",
        }
        draw_info_panel(overlay, info)

        # --- 창 표시 ---
        frame_disp = frame.copy()
        cv2.rectangle(frame_disp, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Ortho: 세로 확장, 최대 높이 제한
        display_max_h = 800
        if out_h > display_max_h:
            ds = display_max_h / out_h
            warped_disp = cv2.resize(warped, (int(out_w * ds), display_max_h))
        else:
            warped_disp = warped.copy()

        # 스케일바
        if m_per_pixel > 0:
            bar_m = 50
            bar_px = int(bar_m / m_per_pixel)
            if out_h > display_max_h:
                bar_px = int(bar_px * ds)
            bh = warped_disp.shape[0]
            cv2.line(warped_disp, (10, bh - 20), (10 + bar_px, bh - 20), (0, 255, 0), 2)
            cv2.putText(warped_disp, f"{bar_m}m", (10, bh - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        cv2.imshow("1. Full Frame", frame_disp)
        cv2.imshow("2. Ortho (isometric)", warped_disp)
        cv2.imshow("3. Crest Detection", crest_vis)
        cv2.imshow("4. Sobel Profile", prof_combined)
        cv2.imshow(overlay_win, overlay)
        # 6번은 정적이라 이미 표시됨

        delay = max(1, int(1000 / fps))
        if cv2.waitKey(delay) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()