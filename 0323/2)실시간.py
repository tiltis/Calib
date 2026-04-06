import cv2
import numpy as np


def run_realtime_calibration(k1_val=-0.19):
    # 0번은 내장 웹캠, LWIR 외부 카메라라면 1번 또는 2번일 수 있습니다.
    cap = cv2.VideoCapture(1, cv2.CAP_MSMF)

    if not cap.isOpened():
        print("카메라를 열 수 없습니다. 인덱스(0, 1, 2...)를 확인해주세요.")
        return

    # --- 에러 수정 부분: 속성 가져오기 ---
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if width == 0 or height == 0:  # 간혹 초기화 직후 0을 반환하는 경우 대비
        width, height = 640, 480

        # 1. 고정된 카메라 파라미터 설정
    # f(초점거리)는 이미지 가로폭의 0.7~1.0배 사이로 설정하는 것이 일반적입니다.
    f = width * 0.8
    K = np.array([[f, 0, width / 2],
                  [0, f, height / 2],
                  [0, 0, 1]], dtype=np.float32)

    # k1 = -0.19 적용 (배럴 왜곡 보정)
    D = np.array([k1_val, 0, 0, 0], dtype=np.float32)

    # 2. 연산 속도 최적화를 위한 맵(Map) 미리 계산
    # alpha=0: 검은 여백 없이 꽉 차게 잘라냄 / alpha=1: 모든 픽셀 보존(검은 여백 생김)
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, D, (width, height), 0)
    map1, map2 = cv2.initUndistortRectifyMap(K, D, None, new_K, (width, height), cv2.CV_32FC1)

    print(f"실시간 보정 가동 중... (k1: {k1_val})")
    print("종료하려면 영상 창에서 'q'를 누르세요.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("프레임을 읽을 수 없습니다.")
            break

        # 3. 고속 리매핑 (Remap)
        undistorted_frame = cv2.remap(frame, map1, map2, cv2.INTER_LINEAR)

        # 결과 출력 (원본과 보정본을 가로로 결합)
        combined = np.hstack((frame, undistorted_frame))

        cv2.imshow("LWIR Real-time Fix (Left: Original / Right: Undistorted)", combined)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    # 요청하신 k1 = -0.19 적용
    run_realtime_calibration(-0.17)