"""
Step 2: LWIR 카메라 내부 파라미터 캘리브레이션 (수동 코너 클릭)
- LWIR 열화상은 콘트라스트가 낮아 자동 검출이 불안정하므로 수동 클릭 사용
- 각 이미지마다 격자 내부 코너를 Z자 순서(좌상→우하)로 클릭
- [ESC]: 해당 이미지 건너뜀

격자 설정: CHECKERBOARD = (내부 코너 열수, 내부 코너 행수)
  예) 4x4 칸 격자 → 내부 코너 3x3 → CHECKERBOARD = (3, 3)

저장 파일: calib_lwir_intrinsic.npz
  - mtx        : 카메라 행렬 (3x3)
  - dist       : 왜곡 계수 (1x5)
  - imgpoints  : 이미지 코너 좌표 목록 (step3에서 재사용)
  - objpoints  : 3D 물체 좌표 목록
  - valid_files: 성공한 이미지 파일 경로 목록
"""
import cv2
import numpy as np
import glob
import os

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"
LWIR_DIR = os.path.join(BASE_DIR, "lwir")

CHECKERBOARD = (3, 3)   # ← 실제 격자 내부 코너 수로 수정
SQUARE_SIZE  = 1.0      # 실제 크기를 모르면 1.0 (상대 단위)


def make_objp():
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE
    return objp


def main():
    images = sorted(glob.glob(os.path.join(LWIR_DIR, "*.png")))
    if not images:
        print(f"이미지 없음: {LWIR_DIR}")
        return

    n_pts   = CHECKERBOARD[0] * CHECKERBOARD[1]
    objp    = make_objp()
    objpoints, imgpoints, valid_files = [], [], []
    img_size = None

    print(f"총 {len(images)}장 | 이미지마다 코너 {n_pts}개 클릭 (ESC: 건너뜀)")
    print("클릭 순서: 좌상 → 우 → 다음 행 (Z자 순서)")

    for fname in images:
        img = cv2.imread(fname)
        if img is None:
            continue
        img_size = img.shape[:2][::-1]  # (width, height)

        gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        display = img.copy()
        clicked = []

        def on_click(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < n_pts:
                clicked.append([x, y])
                cv2.circle(display, (x, y), 4, (0, 0, 255), -1)
                cv2.putText(display, str(len(clicked)), (x+5, y-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                cv2.imshow("LWIR Labeling", display)

        win = "LWIR Labeling"
        cv2.imshow(win, display)
        cv2.setMouseCallback(win, on_click)
        print(f"  {os.path.basename(fname)}  ({len(objpoints)+1}/{len(images)})", end="  ")

        while len(clicked) < n_pts:
            key = cv2.waitKey(1) & 0xFF
            if key == 27:   # ESC → 건너뜀
                break

        if len(clicked) == n_pts:
            pts = np.array(clicked, dtype=np.float32).reshape(-1, 1, 2)
            refined = cv2.cornerSubPix(
                gray, pts, (5, 5), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            )
            objpoints.append(objp)
            imgpoints.append(refined)
            valid_files.append(fname)
            print("OK")
        else:
            print("건너뜀")

    cv2.destroyAllWindows()

    if len(objpoints) < 4:
        print(f"성공한 이미지가 {len(objpoints)}장으로 너무 적습니다. 최소 4장 필요.")
        return

    print(f"\n{len(objpoints)}장으로 캘리브레이션 계산 중...")
    rms, mtx, dist, _, _ = cv2.calibrateCamera(
        objpoints, imgpoints, img_size, None, None
    )
    print(f"RMS 재투영 오차: {rms:.4f} px")

    save_path = os.path.join(BASE_DIR, "calib_lwir_intrinsic.npz")
    np.savez(save_path,
             mtx=mtx, dist=dist,
             imgpoints=np.array(imgpoints, dtype=object),
             objpoints=np.array(objpoints, dtype=object),
             valid_files=np.array(valid_files))
    print(f"저장 완료: {save_path}")

    # 결과 미리보기 (첫 번째 이미지)
    img0 = cv2.imread(valid_files[0])
    img0_undist = cv2.undistort(img0, mtx, dist)
    cv2.imshow("Before / After Undistort (any key)", cv2.hconcat([img0, img0_undist]))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
