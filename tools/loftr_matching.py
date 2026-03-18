"""
LoFTR 딥러닝 크로스모달 매칭 (실험용)
- kornia의 LoFTR 모델로 LWIR ↔ Visible 특징점 자동 매칭
- GPU 있으면 자동으로 사용

의존 패키지: torch, kornia
  pip install torch kornia
"""
import cv2
import torch
import kornia as K
import kornia.feature as KF
import numpy as np
import os
import glob
import ssl

# SSL 인증서 우회 (가중치 다운로드용)
ssl._create_default_https_context = ssl._create_unverified_context

BASE_DIR   = r"C:\Users\tilti\OneDrive\Calib"
LWIR_DIR   = os.path.join(BASE_DIR, "lwir")
VIS_DIR    = os.path.join(BASE_DIR, "visible")
TEST_INDEX = 0       # 테스트할 이미지 쌍 번호
RESIZE     = (640, 512)
NUM_DRAW   = 100     # 시각화할 매칭 수 (상위 N개)


def main():
    lwir_files = sorted(glob.glob(os.path.join(LWIR_DIR, "*.png")))
    vis_files  = sorted(glob.glob(os.path.join(VIS_DIR,  "*.png")))
    if not lwir_files or not vis_files:
        print("이미지를 찾을 수 없습니다.")
        return

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"디바이스: {device}")

    matcher = KF.LoFTR(pretrained="outdoor").to(device).eval()
    print("LoFTR 모델 로드 완료\n")

    img_lwir = cv2.imread(lwir_files[TEST_INDEX], cv2.IMREAD_GRAYSCALE)
    img_vis  = cv2.imread(vis_files[TEST_INDEX],  cv2.IMREAD_GRAYSCALE)

    lwir_rs = cv2.resize(img_lwir, RESIZE)
    vis_rs  = cv2.resize(img_vis,  RESIZE)

    t_lwir = K.image_to_tensor(lwir_rs, False).float() / 255.0
    t_vis  = K.image_to_tensor(vis_rs,  False).float() / 255.0

    with torch.no_grad():
        result = matcher({"image0": t_vis.to(device),
                          "image1": t_lwir.to(device)})

    mkpts_vis  = result["keypoints0"].cpu().numpy()
    mkpts_lwir = result["keypoints1"].cpu().numpy()
    print(f"매칭 포인트: {len(mkpts_vis)}개")

    kpts_vis  = [cv2.KeyPoint(x, y, 1) for x, y in mkpts_vis]
    kpts_lwir = [cv2.KeyPoint(x, y, 1) for x, y in mkpts_lwir]
    matches   = [cv2.DMatch(i, i, 0) for i in range(len(mkpts_vis))]

    matched_img = cv2.drawMatches(
        cv2.cvtColor(vis_rs,  cv2.COLOR_GRAY2BGR), kpts_vis,
        cv2.cvtColor(lwir_rs, cv2.COLOR_GRAY2BGR), kpts_lwir,
        matches[:NUM_DRAW], None,
        matchColor=(0, 255, 0), singlePointColor=(0, 0, 255), flags=0,
    )

    cv2.imshow("LoFTR: Visible (left) ↔ LWIR (right)", matched_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
