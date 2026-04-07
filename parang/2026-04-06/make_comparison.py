"""
make_comparison.py — 보정 전/후 좌우 비교 영상 생성

출력: output/clips/{dir}_compare.mp4
  왼쪽: 원본 (ROI 크롭)
  오른쪽: ortho (등거리 투영)
  15초, 960px 폭
"""

import cv2
import numpy as np
import os
import json
import glob

OUTPUT_DIR = r"C:\Users\tilti\OneDrive\samjung\output"
VIDEO_BASE = r"C:\Users\tilti\OneDrive\samjung\data"
CLIP_DIR   = os.path.join(OUTPUT_DIR, "clips")
CLIP_SEC   = 15
TARGET_H   = 540   # 비교 영상 각 패널 높이


def make_compare(calib):
    """보정 전/후 좌우 비교 영상 생성"""
    dir_name = calib["dir_name"]
    video_file = calib["video"]
    roi = calib["roi"]  # [x1, y1, x2, y2]
    x1, y1, x2, y2 = roi
    roi_w, roi_h = x2 - x1, y2 - y1

    orig_path  = os.path.join(VIDEO_BASE, dir_name, video_file)
    ortho_path = os.path.join(OUTPUT_DIR, f"{dir_name}_ortho.mp4")
    out_path   = os.path.join(CLIP_DIR, f"{dir_name}_compare.mp4")

    if not os.path.exists(orig_path):
        print(f"  [스킵] 원본 없음: {orig_path}")
        return None
    if not os.path.exists(ortho_path) or os.path.getsize(ortho_path) == 0:
        print(f"  [스킵] ortho 없음/손상: {ortho_path}")
        return None

    cap_orig  = cv2.VideoCapture(orig_path)
    cap_ortho = cv2.VideoCapture(ortho_path)

    fps = cap_orig.get(cv2.CAP_PROP_FPS) or 30.0
    total_cut = int(fps * CLIP_SEC)

    # 원본 패널: ROI 크롭 → TARGET_H로 리사이즈
    orig_scale = TARGET_H / roi_h
    panel_w_orig = int(roi_w * orig_scale)

    # ortho 패널: TARGET_H로 리사이즈
    ortho_w = int(cap_ortho.get(cv2.CAP_PROP_FRAME_WIDTH))
    ortho_h = int(cap_ortho.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ortho_scale = TARGET_H / ortho_h if ortho_h > 0 else 1.0
    panel_w_ortho = int(ortho_w * ortho_scale)

    # 전체 캔버스
    gap = 4  # 중간 구분선
    canvas_w = panel_w_orig + gap + panel_w_ortho
    canvas_h = TARGET_H + 40  # 하단 라벨 공간

    os.makedirs(CLIP_DIR, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (canvas_w, canvas_h))

    written = 0
    while written < total_cut:
        ret1, f_orig = cap_orig.read()
        ret2, f_ortho = cap_ortho.read()
        if not ret1 or not ret2:
            break

        # 원본: 리사이즈 → ROI 크롭
        f_orig = cv2.resize(f_orig, (1024, 576))
        roi_crop = f_orig[y1:y2, x1:x2]
        panel_L = cv2.resize(roi_crop, (panel_w_orig, TARGET_H))

        # ortho: 리사이즈
        panel_R = cv2.resize(f_ortho, (panel_w_ortho, TARGET_H))

        # 캔버스 합성
        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
        canvas[:TARGET_H, :panel_w_orig] = panel_L
        canvas[:TARGET_H, panel_w_orig:panel_w_orig+gap] = 255  # 흰색 구분선
        canvas[:TARGET_H, panel_w_orig+gap:] = panel_R

        # 하단 라벨
        cv2.putText(canvas, "Original", (10, canvas_h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(canvas, "Ortho (v10)", (panel_w_orig + gap + 10, canvas_h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 100), 1)

        writer.write(canvas)
        written += 1

    cap_orig.release()
    cap_ortho.release()
    writer.release()

    print(f"  [비교영상] {os.path.basename(out_path)}  ({written/fps:.1f}s, {canvas_w}x{canvas_h})")
    return out_path


def main():
    json_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*_calib.json")))
    print(f"  calib JSON {len(json_files)}개")

    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            calib = json.load(f)
        print(f"\n  [{calib['dir_name']}]")
        make_compare(calib)


if __name__ == "__main__":
    main()
