import cv2
import numpy as np


def find_cameras(max_index=5):
    """사용 가능한 카메라 인덱스 탐색"""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            found.append((i, w, h))
            print(f"  [Index {i}] {w}x{h}")
            cap.release()
    return found


def rotate_image(image, angle):
    """이미지를 중심 기준으로 회전"""
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h),
                             flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0))
    return rotated


def run_overlay(vis_idx=1, flir_idx=0, k1_val=-0.17, alpha=0.5):
    """
    VIS 카메라 위에 FLIR(LWIR) 카메라를 오버레이하여 실시간 표시.
    """

    # ── 카메라 탐색 ──
    print("=== 카메라 탐색 중 ===")
    cams = find_cameras()
    if len(cams) < 2:
        print(f"카메라가 {len(cams)}개만 발견됨. VIS와 FLIR 두 대가 필요합니다.")
        print("인덱스를 수동으로 조정해 주세요.")
        if len(cams) == 0:
            return

    # ── 카메라 열기 ──
    print(f"\n=== VIS: index {vis_idx} / FLIR: index {flir_idx} ===")
    cap_vis = cv2.VideoCapture(vis_idx, cv2.CAP_DSHOW)
    cap_flir = cv2.VideoCapture(flir_idx, cv2.CAP_DSHOW)

    if not cap_vis.isOpened():
        print(f"VIS 카메라(index {vis_idx})를 열 수 없습니다.")
        return
    if not cap_flir.isOpened():
        print(f"FLIR 카메라(index {flir_idx})를 열 수 없습니다.")
        return

    # ── VIS 해상도 ──
    vis_w = int(cap_vis.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    vis_h = int(cap_vis.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    # ── FLIR 해상도 및 왜곡 보정 맵 준비 ──
    flir_w = int(cap_flir.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
    flir_h = int(cap_flir.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    f = flir_w * 0.8
    K = np.array([[f, 0, flir_w / 2],
                  [0, f, flir_h / 2],
                  [0, 0, 1]], dtype=np.float32)
    D = np.array([k1_val, 0, 0, 0], dtype=np.float32)

    new_K, roi = cv2.getOptimalNewCameraMatrix(K, D, (flir_w, flir_h), 0)
    map1, map2 = cv2.initUndistortRectifyMap(
        K, D, None, new_K, (flir_w, flir_h), cv2.CV_32FC1
    )

    print(f"\nVIS  해상도: {vis_w}x{vis_h}")
    print(f"FLIR 해상도: {flir_w}x{flir_h} (k1={k1_val})")
    print(f"오버레이 투명도(alpha): {alpha}")
    print("\n── 조작법 ──")
    print("  y/g/h/j        : FLIR 위치 이동 (1px)")
    print("  z/x/c/v      : FLIR 위치 이동 (10px)  ← ↓ ↑ →")
    print("  a / d        : 투명도 감소 / 증가  (0.05)")
    print("  w / s        : 크기 확대 / 축소    (0.05)")
    print("  r / f        : 시계 / 반시계 회전  (0.5도)")
    print("  R / F        : 시계 / 반시계 회전  (5도)")
    print("  0            : 회전 리셋")
    print("  q            : 종료")

    # ── 오버레이 초기값 ──
    scale = 0.75
    offset_x, offset_y = 79, 54
    angle = 1.0

    # 방향키 코드 (Windows waitKeyEx)
    KEY_LEFT = 2424832
    KEY_RIGHT = 2555904
    KEY_UP = 2490368
    KEY_DOWN = 2621440

    while True:
        ret_v, frame_vis = cap_vis.read()
        ret_f, frame_flir = cap_flir.read()
        if not ret_v or not ret_f:
            print("프레임 읽기 실패")
            break

        # 1) FLIR 왜곡 보정
        flir_undist = cv2.remap(frame_flir, map1, map2, cv2.INTER_LINEAR)

        # 2) FLIR → VIS 해상도에 맞게 리사이즈
        target_w = int(vis_w * scale)
        target_h = int(vis_h * scale)
        flir_resized = cv2.resize(flir_undist, (target_w, target_h))

        # 3) FLIR 그레이스케일이면 → 컬러맵 적용
        if len(flir_resized.shape) == 2 or flir_resized.shape[2] == 1:
            flir_color = cv2.applyColorMap(flir_resized, cv2.COLORMAP_INFERNO)
        else:
            flir_color = flir_resized

        # 4) 회전 적용
        if abs(angle) > 0.01:
            flir_color = rotate_image(flir_color, angle)

        # 5) 오버레이 영역 계산
        x1 = max(offset_x, 0)
        y1 = max(offset_y, 0)
        x2 = min(offset_x + target_w, vis_w)
        y2 = min(offset_y + target_h, vis_h)

        fx1 = x1 - offset_x
        fy1 = y1 - offset_y
        fx2 = fx1 + (x2 - x1)
        fy2 = fy1 + (y2 - y1)

        if x2 > x1 and y2 > y1:
            roi_vis = frame_vis[y1:y2, x1:x2]
            roi_flir = flir_color[fy1:fy2, fx1:fx2]

            if roi_flir.shape[2] != roi_vis.shape[2]:
                roi_flir = cv2.cvtColor(roi_flir, cv2.COLOR_GRAY2BGR)

            blended = cv2.addWeighted(roi_vis, 1.0 - alpha, roi_flir, alpha, 0)
            frame_vis[y1:y2, x1:x2] = blended

        # 6) 정보 텍스트
        info = (f"alpha={alpha:.2f} | scale={scale:.2f} | "
                f"offset=({offset_x},{offset_y}) | rot={angle:.1f}deg | q=quit")
        cv2.putText(frame_vis, info, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

        cv2.imshow("VIS + FLIR Overlay", frame_vis)

        # ── 키 입력 ──
        raw_key = cv2.waitKeyEx(1)
        if raw_key == -1:
            continue

        # === 종료 ===
        if raw_key == ord('q'):
            break

        # === 투명도 ===
        elif raw_key == ord('a'):
            alpha = round(max(0.0, alpha - 0.05), 2)
        elif raw_key == ord('d'):
            alpha = round(min(1.0, alpha + 0.05), 2)

        # === 스케일 ===
        elif raw_key == ord('w'):
            scale = round(min(2.0, scale + 0.05), 2)
        elif raw_key == ord('s'):
            scale = round(max(0.1, scale - 0.05), 2)

        # === 회전: r/f = 0.5도, R/F = 5도, 0 = 리셋 ===
        elif raw_key == ord('r'):
            angle = round(angle - 0.5, 1)
        elif raw_key == ord('f'):
            angle = round(angle + 0.5, 1)
        elif raw_key == ord('R'):
            angle = round(angle - 5.0, 1)
        elif raw_key == ord('F'):
            angle = round(angle + 5.0, 1)
        elif raw_key == ord('0'):
            angle = 0.0

        # === 이동: 방향키 = 1px ===
        elif raw_key == ord('g'):
            offset_x -= 1
        elif raw_key == ord('h'):
            offset_x += 1
        elif raw_key == ord('y'):
            offset_y -= 1
        elif raw_key == ord('j'):
            offset_y += 1

        # === 이동: h/j/k/l = 10px (vim 스타일) ===
        elif raw_key == ord('z'):
            offset_x -= 10
        elif raw_key == ord('x'):
            offset_x += 10
        elif raw_key == ord('c'):
            offset_y -= 10
        elif raw_key == ord('v'):
            offset_y += 10

    cap_vis.release()
    cap_flir.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    VIS_INDEX = 1
    FLIR_INDEX = 0

    run_overlay(
        vis_idx=VIS_INDEX,
        flir_idx=FLIR_INDEX,
        k1_val=-0.17,
        alpha=0.5,
    )









