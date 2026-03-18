"""
수동 워핑 튜너 (트랙바 기반)
- LWIR / Visible 이미지 쌍을 불러와 슬라이더로 정합 파라미터를 실시간 조정
- [Spacebar]: 현재 파라미터 저장 → calib_manual_warp.npz
- [W/A/S/D]: LWIR 미세 이동 (대문자: 10px 단위)
- [Q / ESC]: 종료

저장 파일: calib_manual_warp.npz
  - mtx, dist : LWIR 왜곡 파라미터 (근사값)
  - tx, ty     : 이동량 (픽셀)
  - vis_scale  : Visible 줌 비율
  - stretch_y  : LWIR Y축 스트레치 비율
  - rotate_deg : LWIR 회전각 (도)
"""
import cv2
import numpy as np
import os
import glob

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"
LWIR_DIR = os.path.join(BASE_DIR, "lwir")
VIS_DIR  = os.path.join(BASE_DIR, "visible")
LWIR_W, LWIR_H = 640, 512
WIN = "Manual Warp Tuner"


def main():
    lwir_files = sorted(glob.glob(os.path.join(LWIR_DIR, "*.png")))
    vis_files  = sorted(glob.glob(os.path.join(VIS_DIR,  "*.png")))
    if not lwir_files or not vis_files:
        print("이미지를 찾을 수 없습니다. 경로를 확인하세요.")
        return

    cv2.namedWindow(WIN)
    nothing = lambda x: None
    cv2.createTrackbar("Image Index",          WIN, 0,   len(lwir_files) - 1, nothing)
    cv2.createTrackbar("LWIR k1 (+100)",        WIN, 100, 200,  nothing)
    cv2.createTrackbar("LWIR Focal",            WIN, 600, 1500, nothing)
    cv2.createTrackbar("Vis Zoom (%)",          WIN, 100, 300,  nothing)
    cv2.createTrackbar("LWIR Stretch Y (%)",    WIN, 100, 150,  nothing)
    cv2.createTrackbar("LWIR Rotate (+180 deg)",WIN, 180, 360,  nothing)
    cv2.createTrackbar("Alpha (0=Vis 100=LWIR)",WIN, 50,  100,  nothing)

    tx, ty = 0, 0
    prev_idx = -1
    img_lwir = img_vis = None

    print(f"[{WIN}] W/A/S/D: 이동 | Shift+WASD: 10px | Space: 저장 | Q/ESC: 종료")

    while True:
        idx         = cv2.getTrackbarPos("Image Index",           WIN)
        k1_raw      = cv2.getTrackbarPos("LWIR k1 (+100)",         WIN)
        focal       = cv2.getTrackbarPos("LWIR Focal",             WIN)
        vis_zoom    = cv2.getTrackbarPos("Vis Zoom (%)",           WIN)
        stretch_raw = cv2.getTrackbarPos("LWIR Stretch Y (%)",     WIN)
        rotate_raw  = cv2.getTrackbarPos("LWIR Rotate (+180 deg)", WIN)
        alpha_raw   = cv2.getTrackbarPos("Alpha (0=Vis 100=LWIR)", WIN)

        k1         = (k1_raw - 100) / 100.0
        vis_scale  = max(10, vis_zoom) / 100.0
        stretch_y  = max(50, stretch_raw) / 100.0
        rotate_deg = rotate_raw - 180
        alpha      = alpha_raw / 100.0

        if idx != prev_idx:
            img_lwir  = cv2.imread(lwir_files[idx])
            img_vis_o = cv2.imread(vis_files[idx])
            if img_lwir.shape[:2] != (LWIR_H, LWIR_W):
                img_lwir = cv2.resize(img_lwir, (LWIR_W, LWIR_H))
            img_vis  = cv2.resize(img_vis_o, (LWIR_W, LWIR_H))
            prev_idx = idx

        cx, cy = LWIR_W / 2.0, LWIR_H / 2.0

        # Visible zoom
        M_vis = np.float32([[vis_scale, 0, cx*(1-vis_scale)],
                             [0, vis_scale, cy*(1-vis_scale)]])
        vis_zoomed = cv2.warpAffine(img_vis, M_vis, (LWIR_W, LWIR_H))

        # LWIR undistort
        mtx  = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1]], dtype=np.float32)
        dist = np.array([k1, 0, 0, 0, 0], dtype=np.float32)
        lwir_flat = cv2.undistort(img_lwir, mtx, dist)

        # LWIR rotate
        R = cv2.getRotationMatrix2D((cx, cy), rotate_deg, 1.0)
        lwir_rot = cv2.warpAffine(lwir_flat, R, (LWIR_W, LWIR_H))

        # LWIR translate + stretch Y
        M_lwir = np.float32([[1, 0, tx],
                              [0, stretch_y, cy*(1-stretch_y) + ty]])
        lwir_final = cv2.warpAffine(lwir_rot, M_lwir, (LWIR_W, LWIR_H))

        if len(lwir_final.shape) == 2:
            lwir_final = cv2.cvtColor(lwir_final, cv2.COLOR_GRAY2BGR)

        combined = cv2.addWeighted(vis_zoomed, 1.0 - alpha, lwir_final, alpha, 0)

        info = (f"VZoom:{vis_scale:.2f} | Stretch:{stretch_y:.2f} | "
                f"Rot:{rotate_deg:.1f} | k1:{k1:.2f} | tx:{tx} ty:{ty}")
        cv2.putText(combined, info, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        cv2.imshow(WIN, combined)

        key = cv2.waitKey(10) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == 32:  # Spacebar → 저장
            save_path = os.path.join(BASE_DIR, "calib_manual_warp.npz")
            np.savez(save_path, mtx=mtx, dist=dist, tx=tx, ty=ty,
                     vis_scale=vis_scale, stretch_y=stretch_y, rotate_deg=rotate_deg)
            print(f"저장 완료: {save_path}")
            break
        elif key == ord('w'): ty -= 1
        elif key == ord('s'): ty += 1
        elif key == ord('a'): tx -= 1
        elif key == ord('d'): tx += 1
        elif key == ord('W'): ty -= 10
        elif key == ord('S'): ty += 10
        elif key == ord('A'): tx -= 10
        elif key == ord('D'): tx += 10

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
