import cv2
import numpy as np
import time
import os

# ==========================================
# ⚙️ 세팅 영역
# ==========================================
# 💡 카메라 번호 0번, 1번으로 수정
CAM_ID_LWIR = 0
CAM_ID_VIS = 1

NPZ_FILE_PATH = r"C:\Users\tilti\OneDrive\Calib\lwir\Aligned_Results\lwir_006_flow_map.npz"

DISPLAY_SCALE = 0.6  # 화면에 띄울 창 크기 비율
g_alpha = 0.5  # 투명도


def main():
    global g_alpha

    print("🚀 실시간 듀얼 카메라 센서 퓨전 뷰어를 시작합니다...")

    # 1. 마스터 키(npz) 로드
    if not os.path.exists(NPZ_FILE_PATH):
        print(f"🚨 NPZ 파일을 찾을 수 없습니다: {NPZ_FILE_PATH}")
        return

    npz_data = np.load(NPZ_FILE_PATH)
    g_tx = float(npz_data['g_tx'])
    g_ty = float(npz_data['g_ty'])
    g_scale = float(npz_data['g_scale'])
    g_angle = float(npz_data['g_angle'])

    # flow_x, flow_y는 VIS 영상의 해상도와 동일함
    flow_x = npz_data['flow_x']
    flow_y = npz_data['flow_y']

    vis_h, vis_w = flow_x.shape
    print(f"✅ 마스터 맵 로드 완료 (기준 캔버스 크기: {vis_w} x {vis_h})")

    # 2. 변환 행렬과 메쉬그리드 미리 세팅 (실시간 연산 속도 확보)
    center = (vis_w / 2, vis_h / 2)
    m_rot = cv2.getRotationMatrix2D(center, g_angle, g_scale)
    m_rot[0, 2] += g_tx
    m_rot[1, 2] += g_ty

    map_x, map_y = np.meshgrid(np.arange(vis_w), np.arange(vis_h))
    map_x = map_x.astype(np.float32) - flow_x
    map_y = map_y.astype(np.float32) - flow_y

    # 3. 카메라 연결
    print("⏳ 카메라 연결 중...")
    # 윈도우 환경에서 카메라 여는 속도/딜레이 개선을 위해 CAP_DSHOW 사용
    cap_lwir = cv2.VideoCapture(CAM_ID_LWIR, cv2.CAP_DSHOW)
    cap_vis = cv2.VideoCapture(CAM_ID_VIS, cv2.CAP_DSHOW)

    if not cap_lwir.isOpened(): print("🚨 LWIR(0번) 카메라 연결 실패!")
    if not cap_vis.isOpened(): print("🚨 VIS(1번) 카메라 연결 실패!")
    if not cap_lwir.isOpened() or not cap_vis.isOpened(): return

    print("🎥 라이브 스트리밍 시작! (종료: q, 투명도 조절: - / =)")
    cv2.namedWindow("Live Sensor Fusion (LWIR + VIS)")

    prev_time = time.time()

    while True:
        ret1, frame_lwir = cap_lwir.read()
        ret2, frame_vis = cap_vis.read()

        if not ret1 or not ret2:
            continue

        # LWIR 라이브 영상을 흑백으로 확실히 변환 (원본 해상도 유지!)
        if len(frame_lwir.shape) == 3:
            frame_lwir_gray = cv2.cvtColor(frame_lwir, cv2.COLOR_BGR2GRAY)
        else:
            frame_lwir_gray = frame_lwir

        # VIS 영상은 npz 생성 시점의 해상도로 강제 고정 (오류 방지)
        frame_vis_resized = cv2.resize(frame_vis, (vis_w, vis_h))

        # 4. 💡 [버그 픽스] LWIR 원본 프레임을 그대로 warpAffine에 통과시킴
        # g_scale 값에 의해 알아서 VIS 해상도에 맞게 커지면서 맞춰집니다.
        warped_global = cv2.warpAffine(frame_lwir_gray, m_rot, (vis_w, vis_h), flags=cv2.INTER_LINEAR)

        # 픽셀 유동화 덮어씌우기
        warped_final = cv2.remap(warped_global, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=0)

        # 5. 영상 합성
        lwir_color = cv2.cvtColor(warped_final, cv2.COLOR_GRAY2BGR)
        blended = cv2.addWeighted(frame_vis_resized, 1.0 - g_alpha, lwir_color, g_alpha, 0.0)

        # FPS 표시
        current_time = time.time()
        fps = 1 / (current_time - prev_time)
        prev_time = current_time

        cv2.putText(blended, f"FPS: {fps:.1f} | Alpha: {g_alpha:.1f} [-][=] | Quit [q]",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # 모니터에 맞게 축소해서 디스플레이
        disp_w = int(vis_w * DISPLAY_SCALE)
        disp_h = int(vis_h * DISPLAY_SCALE)
        cv2.imshow("Live Sensor Fusion (LWIR + VIS)", cv2.resize(blended, (disp_w, disp_h)))

        # 키 조작
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('-'):
            g_alpha = max(0.0, g_alpha - 0.1)
        elif key == ord('='):
            g_alpha = min(1.0, g_alpha + 0.1)

    cap_lwir.release()
    cap_vis.release()
    cv2.destroyAllWindows()
    print("🛑 라이브 퓨전 뷰어를 종료했습니다.")


if __name__ == '__main__':
    main()