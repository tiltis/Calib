"""
Step 4: 실시간 LWIR + Visible 오버레이 뷰어
- step3의 스테레오 캘리브레이션 결과로 LWIR을 Visible 시점으로 정합
- 호모그래피는 장면 평균 깊이(SCENE_DEPTH_M)를 가정해 계산
  → 물체까지 거리가 크게 달라지면 미스얼라인 발생 (정상)

의존 파일: calib_stereo.npz (step3 결과)

단축키:
  [A / D]     : 블렌딩 비율 조절 (LWIR ↔ Visible)
  [↑ / ↓]     : 가정 깊이 ±0.1m 조정
  [Q / ESC]   : 종료
"""
import cv2
import numpy as np
import os

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"

CAM_INDEX_LWIR = 1
CAM_INDEX_VIS  = 2
RES_LWIR = (640, 512)
RES_VIS  = (2024, 1536)

SCENE_DEPTH_M = 2.0   # 초기 가정 깊이 (미터). ↑↓ 키로 실시간 조정
ALPHA_INIT    = 0.5   # 초기 블렌딩 비율 (0=Visible만, 1=LWIR만)


def compute_homography(K_lwir, K_vis, R, T, depth_m):
    """
    LWIR → Visible 호모그래피 (평면 장면 가정)
    H = K_vis @ (R - T @ n^T / d) @ K_lwir^{-1}
    """
    n = np.array([[0.0], [0.0], [1.0]])  # 카메라 전방 법선
    H = K_vis @ (R - (T @ n.T) / depth_m) @ np.linalg.inv(K_lwir)
    return H


def main():
    calib_path = os.path.join(BASE_DIR, "calib_stereo.npz")
    if not os.path.exists(calib_path):
        print(f"파일 없음: {calib_path}")
        print("step3_stereo_calib.py 를 먼저 실행하세요.")
        return

    data      = np.load(calib_path)
    K_lwir    = data["K_lwir"];   dist_lwir = data["dist_lwir"]
    K_vis     = data["K_vis"];    dist_vis  = data["dist_vis"]
    R         = data["R"];        T         = data["T"]
    print(f"스테레오 파라미터 로드 완료 (RMS: {float(data['rms']):.4f} px)")

    cap_lwir = cv2.VideoCapture(CAM_INDEX_LWIR, cv2.CAP_MSMF)
    cap_vis  = cv2.VideoCapture(CAM_INDEX_VIS,  cv2.CAP_MSMF)

    cap_lwir.set(cv2.CAP_PROP_FRAME_WIDTH,  RES_LWIR[0])
    cap_lwir.set(cv2.CAP_PROP_FRAME_HEIGHT, RES_LWIR[1])
    cap_vis.set(cv2.CAP_PROP_FRAME_WIDTH,   RES_VIS[0])
    cap_vis.set(cv2.CAP_PROP_FRAME_HEIGHT,  RES_VIS[1])

    alpha = ALPHA_INIT
    depth = SCENE_DEPTH_M
    print("A/D: 블렌딩 조절 | ↑↓: 깊이 조절 | Q/ESC: 종료")

    while True:
        ret_l, frame_lwir = cap_lwir.read()
        ret_v, frame_vis  = cap_vis.read()
        if not ret_l or not ret_v:
            continue

        h_l, w_l = frame_lwir.shape[:2]

        # LWIR 왜곡 보정
        lwir_undist = cv2.undistort(frame_lwir, K_lwir, dist_lwir)

        # 호모그래피로 LWIR → Visible 시점 변환
        H = compute_homography(K_lwir, K_vis, R, T, depth)
        lwir_warped = cv2.warpPerspective(lwir_undist, H, (w_l, h_l))

        # Visible을 LWIR 해상도로 리사이즈
        vis_resized = cv2.resize(frame_vis, (w_l, h_l))
        vis_undist  = cv2.undistort(vis_resized,
                                    K_vis, dist_vis,
                                    None,
                                    cv2.getOptimalNewCameraMatrix(
                                        K_vis, dist_vis, (w_l, h_l), 1, (w_l, h_l))[0])

        if len(lwir_warped.shape) == 2:
            lwir_warped = cv2.cvtColor(lwir_warped, cv2.COLOR_GRAY2BGR)

        # LWIR에 colormap 적용 (열화상 느낌)
        lwir_gray = cv2.cvtColor(lwir_warped, cv2.COLOR_BGR2GRAY)
        lwir_color = cv2.applyColorMap(lwir_gray, cv2.COLORMAP_INFERNO)

        combined = cv2.addWeighted(vis_undist, 1.0 - alpha, lwir_color, alpha, 0)

        cv2.putText(combined,
                    f"Alpha:{alpha:.1f}  Depth:{depth:.1f}m  [A/D: blend | UP/DN: depth]",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
        cv2.imshow("Live Overlay  [LWIR + Visible]", combined)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord('a'):
            alpha = max(0.0, alpha - 0.05)
        elif key == ord('d'):
            alpha = min(1.0, alpha + 0.05)
        elif key == 82:  # ↑
            depth = round(depth + 0.1, 1)
            print(f"깊이: {depth} m")
        elif key == 84:  # ↓
            depth = max(0.1, round(depth - 0.1, 1))
            print(f"깊이: {depth} m")

    cap_lwir.release()
    cap_vis.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
