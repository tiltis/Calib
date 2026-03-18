"""
4점 클릭 수동 호모그래피 (백업용)
- LWIR 창과 Visible 창에서 동일 지점 4쌍을 직접 클릭해 호모그래피 행렬 계산
- step3_stereo_calib.py 가 잘 안 맞을 때 대안으로 사용

저장 파일: calib_manual_homography.npy  (3x3 행렬 H, Visible → LWIR 방향)
의존 파일: calib_lwir_intrinsic.npz (LWIR undistort용)
"""
import cv2
import numpy as np
import os
import glob

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"
LWIR_DIR = os.path.join(BASE_DIR, "lwir")
VIS_DIR  = os.path.join(BASE_DIR, "visible")


def main():
    # LWIR 내부 파라미터 로드 (왜곡 보정용)
    calib_path = os.path.join(BASE_DIR, "calib_lwir_intrinsic.npz")
    if not os.path.exists(calib_path):
        print(f"파일 없음: {calib_path}")
        print("step2_lwir_intrinsic.py 를 먼저 실행하세요.")
        return
    data = np.load(calib_path)
    mtx, dist = data["mtx"], data["dist"]

    lwir_files = sorted(glob.glob(os.path.join(LWIR_DIR, "*.png")))
    vis_files  = sorted(glob.glob(os.path.join(VIS_DIR,  "*.png")))
    if not lwir_files or not vis_files:
        print("이미지를 찾을 수 없습니다.")
        return

    img_lwir = cv2.imread(lwir_files[0])
    img_vis  = cv2.imread(vis_files[0])
    h_l, w_l = img_lwir.shape[:2]

    # LWIR 왜곡 보정
    new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (w_l, h_l), 1, (w_l, h_l))
    lwir_flat   = cv2.undistort(img_lwir, mtx, dist, None, new_mtx)

    # Visible 표시용 리사이즈
    disp_w    = 1024
    scale_v   = img_vis.shape[1] / disp_w
    disp_h    = int(img_vis.shape[0] / scale_v)
    vis_small = cv2.resize(img_vis, (disp_w, disp_h))

    pts_lwir, pts_vis = [], []
    lwir_disp = lwir_flat.copy()

    def on_click_lwir(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts_lwir) < 4:
            pts_lwir.append([x, y])
            cv2.circle(lwir_disp, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(lwir_disp, str(len(pts_lwir)), (x+5, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("LWIR (undistorted)", lwir_disp)

    def on_click_vis(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts_vis) < 4:
            rx, ry = int(x * scale_v), int(y * scale_v)
            pts_vis.append([rx, ry])
            cv2.circle(vis_small, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(vis_small, str(len(pts_vis)), (x+5, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("Visible", vis_small)

    print("LWIR 창 → Visible 창 순서로 동일 지점 4쌍 클릭 (ESC: 중단)")
    cv2.imshow("LWIR (undistorted)", lwir_disp)
    cv2.imshow("Visible", vis_small)
    cv2.setMouseCallback("LWIR (undistorted)", on_click_lwir)
    cv2.setMouseCallback("Visible", on_click_vis)

    while len(pts_vis) < 4:
        if cv2.waitKey(1) & 0xFF == 27:
            break

    if len(pts_lwir) == 4 and len(pts_vis) == 4:
        # H: Visible → LWIR 방향
        H, _ = cv2.findHomography(np.array(pts_vis, dtype=np.float32),
                                   np.array(pts_lwir, dtype=np.float32))
        save_path = os.path.join(BASE_DIR, "calib_manual_homography.npy")
        np.save(save_path, H)
        print(f"저장 완료: {save_path}")

        # 결과 미리보기
        vis_warped = cv2.warpPerspective(img_vis, H, (w_l, h_l))
        overlay = cv2.addWeighted(lwir_flat, 0.5, vis_warped, 0.5, 0)
        cv2.imshow("Result (any key to close)", overlay)
        cv2.waitKey(0)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
