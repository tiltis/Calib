import cv2


def identify_cameras(max_index=5):
    """
    연결된 카메라를 하나씩 열어서 화면에 보여줍니다.
    직접 눈으로 보고 어떤 인덱스가 VIS이고 FLIR인지 확인하세요.

    조작법:
      n : 다음 카메라로 넘어가기
      q : 종료
    """

    print("=== 카메라 식별 도구 ===")
    print("각 카메라를 하나씩 띄워줍니다.")
    print("'n' = 다음 카메라 / 'q' = 종료\n")

    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"[Index {i}] 카메라 없음 — 건너뜀")
            continue

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
        print(f"[Index {i}] 열림 — {w}x{h}  ← 지금 화면을 보세요!")

        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"  → 프레임 읽기 실패, 건너뜁니다.")
                break

            label = f"Camera Index {i}  ({w}x{h})  |  n=next  q=quit"
            cv2.putText(frame, label, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

            cv2.imshow("Camera Identify", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('n'):
                break
            elif key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                print("\n종료됨.")
                return

        cap.release()
        cv2.destroyAllWindows()

    print("\n=== 탐색 완료 ===")
    print("확인한 인덱스를 vis_flir_overlay.py 에 넣어주세요:")
    print("  VIS_INDEX  = ?")
    print("  FLIR_INDEX = ?")


if __name__ == "__main__":
    identify_cameras()