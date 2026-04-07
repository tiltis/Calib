"""
batch_run.py — 여러 영상에 piza2 파이프라인 일괄 적용

흐름:
  1. samjung/ 하위 폴더 중 영상(.mp4)이 있는 폴더 탐색
  2. 폴더별로 mp4 파일 목록 출력 → 사용자가 번호 선택
  3. 선택한 영상으로 piza2.py main() 실행 (ROI 선택 등 대화형 유지)
  4. 캘리브 완료 후 ROI 좌표를 {dir}_roi.json에 저장
     → 같은 폴더 내 다음 영상은 저장된 ROI 재사용 여부 선택 가능

사용법:
  python batch_run.py
  python batch_run.py --dir Swell_20260120_UTC1007   # 특정 폴더만
  python batch_run.py --all                           # 모든 폴더 순서대로
"""

import os
import sys
import json
import argparse
import importlib.util

# ============================================================
# 경로
# ============================================================
VIDEO_BASE = r"C:\Users\tilti\OneDrive\samjung\data"
OUTPUT_DIR = r"C:\Users\tilti\OneDrive\samjung\output"
PIZA2_PATH = os.path.join(os.path.dirname(__file__), "piza5.py")

# ============================================================
# piza2 모듈 동적 로드
# ============================================================
def load_piza2():
    spec   = importlib.util.spec_from_file_location("piza2", os.path.abspath(PIZA2_PATH))
    mod    = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# 영상 있는 폴더 탐색
# ============================================================
def find_video_folders():
    """VIDEO_BASE 하위에서 .mp4 파일이 있는 폴더 반환 (폴더명, 파일 목록)"""
    results = []
    if not os.path.isdir(VIDEO_BASE):
        print(f"X 폴더 없음: {VIDEO_BASE}")
        return results
    for name in sorted(os.listdir(VIDEO_BASE)):
        folder = os.path.join(VIDEO_BASE, name)
        if not os.path.isdir(folder):
            continue
        mp4s = sorted(f for f in os.listdir(folder) if f.endswith(".mp4"))
        if mp4s:
            results.append((name, mp4s))
    return results


# ============================================================
# ROI 저장 / 로드
# ============================================================
def roi_save_path(dir_name):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f"{dir_name}_roi.json")


def save_roi(dir_name, roi):
    """roi = (x1, y1, x2, y2)"""
    path = roi_save_path(dir_name)
    with open(path, "w") as f:
        json.dump({"roi": list(roi)}, f)
    print(f"  [ROI 저장] {path}")


def load_roi(dir_name):
    """저장된 ROI 반환. 없으면 None."""
    path = roi_save_path(dir_name)
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return tuple(data["roi"])
    return None


# ============================================================
# 단일 영상 처리
# ============================================================
def process_one(video_path, piza2_mod, saved_roi=None):
    """
    piza2의 파이프라인을 직접 호출.
    saved_roi가 있으면 ROI 선택 단계를 스킵하고 재사용.
    결과로 사용된 ROI 좌표를 반환.
    """
    import cv2
    import numpy as np

    # piza2 함수들을 꺼내서 사용
    open_video          = piza2_mod.open_video
    detect_crests       = piza2_mod.detect_crests
    CrestTracker        = piza2_mod.CrestTracker
    build_velocity_scale_map = piza2_mod.build_velocity_scale_map
    build_remap_tables  = piza2_mod.build_remap_tables
    draw_scale_graph    = piza2_mod.draw_scale_graph
    draw_info           = piza2_mod.draw_info
    save_calib_json     = piza2_mod.save_calib_json
    load_weather_params = piza2_mod.load_weather_params
    calc_wave_params    = piza2_mod.calc_wave_params
    select_roi          = piza2_mod.select_roi
    roi_state           = piza2_mod.roi_state
    nothing             = piza2_mod.nothing
    XLSX_PATH           = piza2_mod.XLSX_PATH
    CALIB_SECONDS       = piza2_mod.CALIB_SECONDS
    G                   = piza2_mod.G

    dir_name = os.path.basename(os.path.dirname(video_path))

    # 기상 파라미터 로드
    weather = load_weather_params(XLSX_PATH, dir_name)
    if weather is None:
        print(f"  경고: '{dir_name}' xlsx에 없음 — 스킵")
        return None
    wave = calc_wave_params(weather)

    cap = open_video(video_path)
    if cap is None:
        return None

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ret, frame   = cap.read()
    if not ret:
        cap.release(); return None

    frame = cv2.resize(frame, (1024, 576))
    clone = frame.copy()

    print(f"\n  {'='*55}")
    print(f"  {os.path.basename(video_path)}")
    print(f"  SOG={weather['sog_knots']:.1f}kts  Enc={wave['enc_primary']:.2f}m/s ({wave['enc_label']})")
    print(f"  {total_frames}f / {total_frames/fps:.0f}s / {fps:.0f}fps")
    print(f"  {'='*55}")

    # ---- ROI 선택 또는 재사용 ----
    if saved_roi is not None:
        x1, y1, x2, y2 = saved_roi
        print(f"  저장된 ROI 재사용: ({x1},{y1})~({x2},{y2})")
        # 시각 확인
        disp = clone.copy()
        cv2.rectangle(disp, (x1,y1), (x2,y2), (0,255,0), 2)
        cv2.putText(disp, "저장된 ROI — Enter=사용 / r=다시선택",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        cv2.imshow("ROI 확인", disp)
        k = cv2.waitKey(0) & 0xFF
        cv2.destroyWindow("ROI 확인")
        if k == ord('r'):
            saved_roi = None   # 다시 선택
        elif k == ord('q'):
            cap.release(); return None

    if saved_roi is None:
        # 대화형 ROI 선택
        roi_state.update({"drawing":False,"start":None,"end":None,"selected":False})
        win = "Select ROI  (drag->Enter | r=redo | q=skip)"
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
            elif k == ord('q'): cap.release(); cv2.destroyAllWindows(); return None
        cv2.destroyWindow(win)
        x1 = min(roi_state["start"][0], roi_state["end"][0])
        y1 = min(roi_state["start"][1], roi_state["end"][1])
        x2 = max(roi_state["start"][0], roi_state["end"][0])
        y2 = max(roi_state["start"][1], roi_state["end"][1])

    roi_w, roi_h = x2-x1, y2-y1
    if roi_w < 50 or roi_h < 50:
        print("  X ROI 너무 작음"); cap.release(); return None

    used_roi = (x1, y1, x2, y2)

    # ---- Phase 1: 캘리브레이션 ----
    calib_n = int(fps * CALIB_SECONDS)
    tracker = CrestTracker(max_disp=int(roi_h * 0.1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    cw = f"Calibrating: {os.path.basename(video_path)}"
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
            pct = (fi+1)/calib_n
            cv2.rectangle(vis, (0,roi_h-6), (int(roi_w*pct),roi_h), (0,200,0), -1)
            cv2.putText(vis, f"{fi+1}/{calib_n} ({pct:.0%})",
                        (5,16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,0), 1)
            cv2.imshow(cw, vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release(); cv2.destroyAllWindows(); return used_roi

    cv2.destroyWindow(cw)

    # ---- 스케일 맵 ----
    vel_vs_y = tracker.get_velocity_vs_y(fps, min_frames=8)
    enc_used = wave["enc_primary"]
    y_full, mpp_map, r_sq = build_velocity_scale_map(vel_vs_y, roi_h, enc_used)

    if mpp_map is not None and mpp_map[0] > mpp_map[-1]:
        map_x, map_y, out_h, base_mpp = build_remap_tables(roi_w, roi_h, mpp_map)
        use_remap = True
    elif mpp_map is not None:
        ratio     = max(mpp_map[0]/mpp_map[-1] if mpp_map[-1]>0 else 1.5, 1.1)
        use_remap = False
        base_mpp  = float(np.mean(mpp_map))
        out_h     = int(roi_h * ratio)
    else:
        ratio     = 1.5
        use_remap = False
        base_mpp  = 0.0
        out_h     = int(roi_h * ratio)
        mpp_map   = None

    if not use_remap:
        shrink = (1.0 - 1.0/ratio) / 2.0
        mg     = int(roi_w * shrink)
        src    = np.float32([[x1+mg,y1],[x2-mg,y1],[x1,y2],[x2,y2]])
        dst    = np.float32([[0,0],[roi_w,0],[0,out_h],[roi_w,out_h]])
        fb_mat = cv2.getPerspectiveTransform(src, dst)

    # ---- JSON 저장 ----
    save_calib_json(
        OUTPUT_DIR, dir_name, video_path,
        roi_rect   = [x1,y1,x2,y2],
        r_sq       = r_sq,
        enc_speed  = enc_used,
        enc_label  = wave["enc_label"],
        base_mpp   = base_mpp,
        use_remap  = use_remap,
        out_size   = [roi_w, out_h],
        weather_params = weather,
        wave_params    = wave,
    )

    # ---- Phase 2: ortho 영상 저장 ----
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{dir_name}_ortho.mp4")
    fourcc   = cv2.VideoWriter_fourcc(*"mp4v")
    writer   = cv2.VideoWriter(out_path, fourcc, fps, (roi_w, out_h))

    sg  = draw_scale_graph(mpp_map, vel_vs_y, roi_h, enc_used)
    ov  = f"Overlay: {os.path.basename(video_path)}"
    cv2.imshow(ov, np.zeros((100,100,3),dtype=np.uint8)); cv2.waitKey(1)
    cv2.createTrackbar("alpha%", ov, 50, 100, nothing)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    dmax = 800

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.resize(frame, (1024, 576))
        roi   = frame[y1:y2, x1:x2]

        if use_remap:
            warped = cv2.remap(roi, map_x, map_y, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
        else:
            warped = cv2.warpPerspective(frame, fb_mat, (roi_w, out_h))

        writer.write(warped)

        # 표시
        wd = cv2.resize(warped, (int(warped.shape[1]*dmax/warped.shape[0]), dmax)) \
             if warped.shape[0] > dmax else warped.copy()
        f1 = frame.copy(); cv2.rectangle(f1,(x1,y1),(x2,y2),(0,255,0),2)
        a  = cv2.getTrackbarPos("alpha%", ov) / 100.0
        ovl = frame.copy()
        wr  = cv2.resize(warped, (roi_w, roi_h))
        ovl[y1:y2, x1:x2] = cv2.addWeighted(roi, 1-a, wr, a, 0)
        cv2.rectangle(ovl,(x1,y1),(x2,y2),(0,255,0),1)
        draw_info(ovl, [
            f"Enc={enc_used:.1f}m/s  base={base_mpp:.3f}m/px",
            f"R²={r_sq:.3f}" if r_sq else "",
            f"{'remap' if use_remap else 'homography'}  REC...",
        ])
        cv2.imshow("1 Original", f1)
        cv2.imshow("2 Ortho", wd)
        cv2.imshow("3 Scale Map", sg)
        cv2.imshow(ov, ovl)
        if cv2.waitKey(max(1, int(1000/fps))) & 0xFF == ord('q'):
            break

    writer.release()
    cap.release()
    cv2.destroyAllWindows()
    print(f"  [저장] {out_path}")
    return used_roi


# ============================================================
# 메인
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="piza2 배치 처리")
    parser.add_argument("--dir",  type=str, default=None, help="특정 폴더명만 처리")
    parser.add_argument("--all",  action="store_true",    help="모든 폴더 순서대로 처리")
    args = parser.parse_args()

    folders = find_video_folders()
    if not folders:
        print("X 처리할 영상 없음")
        return

    print("\n사용 가능한 영상 폴더:")
    for i, (name, files) in enumerate(folders):
        print(f"  [{i}] {name}  ({len(files)}개 mp4)")

    def parse_num(raw, max_val, default=0):
        """'1번', '2', '3.' 등에서 숫자만 추출. 범위 초과 시 default."""
        digits = ''.join(c for c in raw if c.isdigit())
        n = int(digits) if digits else default
        return n if 0 <= n <= max_val else default

    # 처리할 폴더 선택
    if args.dir:
        targets = [(n, f) for n, f in folders if n == args.dir]
        if not targets:
            print(f"X '{args.dir}' 폴더 없음"); return
    elif args.all:
        targets = folders
    else:
        raw = input("\n처리할 폴더 번호: ").strip()
        idx = parse_num(raw, len(folders) - 1, default=0)
        targets = [folders[idx]]

    piza2_mod = load_piza2()

    for dir_name, mp4_files in targets:
        print(f"\n\n{'='*60}")
        print(f"  폴더: {dir_name}")
        print(f"{'='*60}")

        # 파일 목록 출력 + 선택
        print("  영상 파일:")
        for j, f in enumerate(mp4_files):
            print(f"    [{j}] {f}")

        if len(mp4_files) == 1:
            # 파일이 1개면 자동 선택
            file_indices = [0]
            print("  → 자동 선택: [0]")
        else:
            raw_f = input(
                "  처리할 파일 번호 (엔터=전체 / 숫자=단일 / 2,3=복수): "
            ).strip()
            if raw_f == "":
                file_indices = list(range(len(mp4_files)))
            else:
                # 콤마/공백 구분으로 복수 선택 지원
                parts = raw_f.replace(",", " ").split()
                file_indices = []
                for p in parts:
                    n = parse_num(p, len(mp4_files) - 1, default=0)
                    if n not in file_indices:
                        file_indices.append(n)

        # 저장된 ROI 확인
        saved_roi = load_roi(dir_name)
        if saved_roi:
            print(f"  저장된 ROI 있음: {saved_roi}")

        for order, fi in enumerate(file_indices):
            fname      = mp4_files[fi]
            video_path = os.path.join(VIDEO_BASE, dir_name, fname)
            print(f"\n  [{order+1}/{len(file_indices)}] {fname}")

            result = process_one(video_path, piza2_mod, saved_roi=saved_roi)

            if result is not None and saved_roi is None:
                save_roi(dir_name, result)
                saved_roi = result

    print("\n\n배치 처리 완료.")


if __name__ == '__main__':
    main()
