import cv2
import numpy as np

# 이미지 경로
image_path = r"C:\Users\tilti\OneDrive\Calib\lwir\lwir_033.png"
img = cv2.imread(image_path)

if img is None:
    print("이미지를 불러올 수 없습니다.")
    exit()

h, w = img.shape[:2]


def update_undistort(val):
    # 트랙바 값(0~200)을 실제 k1 범위(-1.0 ~ 1.0)로 변환
    k1 = (val - 100) / 100.0

    # 가상의 카메라 매트릭스
    f = w * 0.8
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float32)
    D = np.array([k1, 0, 0, 0], dtype=np.float32)

    # 보정 실행
    new_K, _ = cv2.getOptimalNewCameraMatrix(K, D, (w, h), 1)
    dst = cv2.undistort(img, K, D, None, new_K)

    # 결과 출력
    cv2.putText(dst, f"k1: {k1:.3f}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("Real-time Manual Calib", dst)


cv2.namedWindow("Real-time Manual Calib")
# 중간값(100)이 k1=0 이 되도록 설정
cv2.createTrackbar("k1 adjustment", "Real-time Manual Calib", 100, 200, update_undistort)

# 초기 화면 출력
update_undistort(100)

print("슬라이더를 좌우로 움직여 가로선이 직선이 되는 지점을 찾으세요.")
print("[ s ]: 현재 파라미터 저장 및 종료")
print("[ ESC ]: 그냥 종료")

while True:
    key = cv2.waitKey(1) & 0xFF
    if key == ord('s'):
        val = cv2.getTrackbarPos("k1 adjustment", "Real-time Manual Calib")
        final_k1 = (val - 100) / 100.0
        print(f"저장된 k1: {final_k1}")
        # np.savez 등으로 저장 로직 추가 가능
        break
    elif key == 27:
        break

cv2.destroyAllWindows()