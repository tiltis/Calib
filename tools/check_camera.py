"""
카메라 스펙 확인 유틸리티
- 연결된 카메라 인덱스별 최대 해상도 출력
"""
import cv2

CAMERA_INDICES = [0, 1, 2]  # 확인할 인덱스 목록


def check_max_resolution(cam_index):
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"  [{cam_index}] 연결 불가")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 10000)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 10000)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    print(f"  [{cam_index}] 최대 해상도: {w} x {h}")


if __name__ == "__main__":
    print("=== 카메라 해상도 확인 ===")
    for idx in CAMERA_INDICES:
        check_max_resolution(idx)
    print("=========================")
