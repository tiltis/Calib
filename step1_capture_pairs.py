"""
Step 1: 카메라 쌍 동시 캡처
- LWIR (index 1, 640x512) + Visible (index 2, 3264x2448) 동시 촬영
- 격자 보드 캘리브레이션 이미지 수집용

저장 경로:
  lwir/lwir_001.png ...
  visible/vis_001.png ...

단축키:
  [Space / S] : 현재 프레임 저장
  [Q / ESC]   : 종료
"""
import cv2
import os
import time

BASE_DIR = r"C:\Users\tilti\OneDrive\Calib"
LWIR_DIR = os.path.join(BASE_DIR, "lwir")
VIS_DIR  = os.path.join(BASE_DIR, "visible")

CAM_INDEX_LWIR = 1
CAM_INDEX_VIS  = 2
RES_LWIR = (640, 512)
RES_VIS  = (3264, 2448)
PREVIEW_H = 480  # 화면 표시용 높이


def main():
    os.makedirs(LWIR_DIR, exist_ok=True)
    os.makedirs(VIS_DIR,  exist_ok=True)

    cap_lwir = cv2.VideoCapture(CAM_INDEX_LWIR, cv2.CAP_MSMF)
    cap_vis  = cv2.VideoCapture(CAM_INDEX_VIS,  cv2.CAP_MSMF)

    if not cap_lwir.isOpened() or not cap_vis.isOpened():
        print("카메라를 열 수 없습니다. 인덱스와 연결을 확인하세요.")
        return

    cap_lwir.set(cv2.CAP_PROP_FRAME_WIDTH,  RES_LWIR[0])
    cap_lwir.set(cv2.CAP_PROP_FRAME_HEIGHT, RES_LWIR[1])
    cap_vis.set(cv2.CAP_PROP_FRAME_WIDTH,   RES_VIS[0])
    cap_vis.set(cv2.CAP_PROP_FRAME_HEIGHT,  RES_VIS[1])

    # 기존 저장 파일 수 파악 → 이어서 번호 부여
    existing = len([f for f in os.listdir(LWIR_DIR) if f.endswith(".png")])
    count = existing
    print(f"기존 캡처 {existing}장 → {existing+1}번부터 이어서 저장")
    print("[Space/S]: 캡처  [Q/ESC]: 종료")

    while True:
        ret_l, frame_lwir = cap_lwir.read()
        ret_v, frame_vis  = cap_vis.read()

        if not ret_l or not ret_v:
            time.sleep(0.05)
            continue

        h_l, w_l = frame_lwir.shape[:2]
        h_v, w_v = frame_vis.shape[:2]

        # 미리보기 리사이즈
        lwir_disp = cv2.resize(frame_lwir, (int(w_l * PREVIEW_H / h_l), PREVIEW_H))
        vis_disp  = cv2.resize(frame_vis,  (int(w_v * PREVIEW_H / h_v), PREVIEW_H))

        if len(lwir_disp.shape) == 2:
            lwir_disp = cv2.cvtColor(lwir_disp, cv2.COLOR_GRAY2BGR)

        cv2.putText(lwir_disp, f"LWIR {w_l}x{h_l}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(vis_disp,  f"VIS  {w_v}x{h_v}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        preview = cv2.hconcat([lwir_disp, vis_disp])
        cv2.putText(preview, f"Saved: {count}", (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imshow("Capture  [Left: LWIR | Right: Visible]", preview)

        key = cv2.waitKey(1) & 0xFF
        if key in (32, ord('s')):  # Space or S
            count += 1
            cv2.imwrite(os.path.join(LWIR_DIR, f"lwir_{count:03d}.png"), frame_lwir)
            cv2.imwrite(os.path.join(VIS_DIR,  f"vis_{count:03d}.png"),  frame_vis)
            print(f"[{count:03d}] 저장  LWIR:{w_l}x{h_l}  VIS:{w_v}x{h_v}")
        elif key in (ord('q'), 27):
            break

    cap_lwir.release()
    cap_vis.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
