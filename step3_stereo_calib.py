"""
Step 3: 스테레오 캘리브레이션 (LWIR ↔ Visible)
- step2에서 저장한 LWIR 코너 데이터를 로드
- 동일 이미지 쌍의 Visible에서 자동으로 코너 검출
- 스테레오 캘리브레이션으로 두 카메라 사이의 R, T 계산

의존 파일: calib_lwir_intrinsic.npz (step2 결과)

저장 파일: calib_stereo.npz
  - K_lwir, dist_lwir  : LWIR 내부 파라미터
  - K_vis,  dist_vis   : Visible 내부 파라미터
  - R, T               : LWIR → Visible 좌표계 변환 (회전, 이동)
  - rms                : 스테레오 재투영 오차

설정값:
  CHECKERBOARD : step2와 동일한 코너 수
  SQUARE_SIZE  : 실제 격자 한 칸 크기 (미터 단위)
"""
import cv2
import numpy as np
import os
import glob

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"
VIS_DIR  = os.path.join(BASE_DIR, "visible")

CHECKERBOARD = (3, 3)    # ← step2와 동일하게 맞출 것
SQUARE_SIZE  = 0.025     # 미터 단위. 예) 25mm 격자 → 0.025


def make_objp():
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE
    return objp


def detect_vis_corners(img_path):
    """Visible 이미지에서 자동으로 체커보드 코너 검출"""
    img  = cv2.imread(img_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    flags = (cv2.CALIB_CB_ADAPTIVE_THRESH
             + cv2.CALIB_CB_NORMALIZE_IMAGE
             + cv2.CALIB_CB_FAST_CHECK)
    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, flags)

    if ret:
        corners = cv2.cornerSubPix(
            gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        )
    return ret, corners, gray.shape[::-1]  # (corners, img_size as (w,h))


def main():
    # ── LWIR 데이터 로드 ──────────────────────────────────────────────
    lwir_calib_path = os.path.join(BASE_DIR, "calib_lwir_intrinsic.npz")
    if not os.path.exists(lwir_calib_path):
        print(f"파일 없음: {lwir_calib_path}")
        print("step2_lwir_intrinsic.py 를 먼저 실행하세요.")
        return

    data        = np.load(lwir_calib_path, allow_pickle=True)
    K_lwir      = data["mtx"]
    dist_lwir   = data["dist"]
    lwir_imgpts = list(data["imgpoints"])   # 이미지별 코너 좌표
    valid_lwir  = list(data["valid_files"]) # 성공한 LWIR 파일 경로

    print(f"LWIR 캘리브 로드 완료: {len(valid_lwir)}장")

    # ── 대응하는 Visible 파일 이름 추론 ──────────────────────────────
    #   lwir/lwir_005.png → visible/vis_005.png
    vis_imgpts  = []
    obj_pts     = []
    used_lwir   = []
    objp        = make_objp()
    vis_size    = None

    print("Visible 코너 자동 검출 중...")
    for lwir_path, lwir_corners in zip(valid_lwir, lwir_imgpts):
        basename   = os.path.basename(lwir_path)            # lwir_005.png
        vis_name   = basename.replace("lwir_", "vis_")      # vis_005.png
        vis_path   = os.path.join(VIS_DIR, vis_name)

        if not os.path.exists(vis_path):
            print(f"  건너뜀 (vis 없음): {vis_name}")
            continue

        ret, vis_corners, size = detect_vis_corners(vis_path)
        if ret:
            vis_imgpts.append(vis_corners)
            obj_pts.append(objp)
            used_lwir.append(lwir_corners)
            vis_size = size
            print(f"  OK: {vis_name}")
        else:
            print(f"  건너뜀 (코너 미검출): {vis_name}")

    if len(obj_pts) < 4:
        print(f"\n성공 쌍이 {len(obj_pts)}개뿐입니다. 최소 4쌍 필요.")
        print("Visible 이미지 자동 검출이 안 되면 tools/manual_homography.py 를 사용하세요.")
        return

    print(f"\n{len(obj_pts)}쌍으로 캘리브레이션 계산 중...")

    # ── Visible 내부 파라미터 캘리브레이션 ───────────────────────────
    rms_vis, K_vis, dist_vis, _, _ = cv2.calibrateCamera(
        obj_pts, vis_imgpts, vis_size, None, None
    )
    print(f"Visible RMS: {rms_vis:.4f} px")

    # LWIR 이미지 크기 (첫 번째 이미지에서 읽기)
    lwir_img0  = cv2.imread(valid_lwir[0])
    lwir_size  = lwir_img0.shape[:2][::-1]

    # ── 스테레오 캘리브레이션 ─────────────────────────────────────────
    # CALIB_FIX_INTRINSIC: 위에서 구한 내부 파라미터를 고정하고 R, T만 최적화
    rms_stereo, K_lwir_out, dist_lwir_out, K_vis_out, dist_vis_out, R, T, E, F = \
        cv2.stereoCalibrate(
            obj_pts,
            used_lwir,   # LWIR 코너 (기준)
            vis_imgpts,  # Visible 코너
            K_lwir, dist_lwir,
            K_vis,  dist_vis,
            lwir_size,
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
            flags=cv2.CALIB_FIX_INTRINSIC,
        )

    print(f"스테레오 RMS: {rms_stereo:.4f} px")
    print(f"카메라 간 거리: {np.linalg.norm(T)*100:.1f} cm")
    print(f"R:\n{R}")
    print(f"T (m): {T.flatten()}")

    save_path = os.path.join(BASE_DIR, "calib_stereo.npz")
    np.savez(save_path,
             K_lwir=K_lwir_out, dist_lwir=dist_lwir_out,
             K_vis=K_vis_out,   dist_vis=dist_vis_out,
             R=R, T=T,
             rms=rms_stereo)
    print(f"\n저장 완료: {save_path}")
    print("→ step4_live_overlay.py 를 실행하세요.")


if __name__ == "__main__":
    main()
