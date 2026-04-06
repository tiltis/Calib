import cv2
import numpy as np
import os

# ==========================================
# ⚙️ 세팅 영역 (경로 확인 필수)
# ==========================================
DIR_LWIR = r"C:\Users\tilti\OneDrive\Calib\lwir"
DIR_VIS = r"C:\Users\tilti\OneDrive\Calib\visible"

# 1. 📂 결과물 전용 저장 폴더 생성 (원본과 분리)
SAVE_DIR = os.path.join(DIR_LWIR, "Aligned_Results")
os.makedirs(SAVE_DIR, exist_ok=True)

TARGET_IMAGES = 5
DISPLAY_SCALE = 0.6

# ==========================================
# 🌍 전역 변수 (다음 사진에도 계속 유지됨!)
# ==========================================
# 글로벌 아핀 파라미터
g_tx, g_ty = 0.0, 0.0
g_scale = 1.0
g_angle = 0.0
g_alpha = 0.5

# 픽셀 유동화 (Liquify) 맵 파라미터
flow_x = None  # X방향 픽셀 밀림 맵
flow_y = None  # Y방향 픽셀 밀림 맵

# 브러시 세팅
brush_radius = 50
brush_strength = 1.0

# 마우스 상태
is_r_dragging = False
last_rx, last_ry = 0, 0

# 이미지 전역 변수
img_vis_global = None
img_lwir_global = None
original_w_vis, original_h_vis = 0, 0


def update_display():
    global img_vis_global, img_lwir_global, g_alpha, flow_x, flow_y
    if img_vis_global is None or img_lwir_global is None: return

    # 글로벌 변환 (크기, 회전, 전체 이동)
    center = (original_w_vis / 2, original_h_vis / 2)
    m_rot = cv2.getRotationMatrix2D(center, g_angle, g_scale)
    m_rot[0, 2] += g_tx
    m_rot[1, 2] += g_ty
    warped_global = cv2.warpAffine(img_lwir_global, m_rot, (original_w_vis, original_h_vis), flags=cv2.INTER_LINEAR)

    # 로컬 픽셀 유동화
    map_x, map_y = np.meshgrid(np.arange(original_w_vis), np.arange(original_h_vis))
    map_x = map_x.astype(np.float32) - flow_x
    map_y = map_y.astype(np.float32) - flow_y

    warped_final = cv2.remap(warped_global, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                             borderValue=0)

    # 합성 및 텍스트 표시
    lwir_warped_color = cv2.cvtColor(warped_final, cv2.COLOR_GRAY2BGR)
    blended = cv2.addWeighted(img_vis_global, 1.0 - g_alpha, lwir_warped_color, g_alpha, 0.0)

    status_text = f"Brush:{brush_radius} | Liquify: R-Drag | S:{g_scale:.3f} A:{g_angle:.1f} | Tx:{g_tx} Ty:{g_ty}"
    cv2.putText(blended, status_text, (10, original_h_vis - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    disp_w = int(original_w_vis * DISPLAY_SCALE)
    disp_h = int(original_h_vis * DISPLAY_SCALE)
    displayed_img = cv2.resize(blended, (disp_w, disp_h))

    cv2.imshow("Photoshop Liquify Aligner", displayed_img)


def mouse_callback(event, x, y, flags, param):
    global is_r_dragging, last_rx, last_ry, flow_x, flow_y, brush_radius

    true_x = int(x / DISPLAY_SCALE)
    true_y = int(y / DISPLAY_SCALE)

    if event == cv2.EVENT_RBUTTONDOWN:
        is_r_dragging = True
        last_rx, last_ry = true_x, true_y

    elif event == cv2.EVENT_MOUSEMOVE:
        if is_r_dragging:
            dx = true_x - last_rx
            dy = true_y - last_ry

            x_min = max(0, true_x - brush_radius)
            x_max = min(original_w_vis, true_x + brush_radius)
            y_min = max(0, true_y - brush_radius)
            y_max = min(original_h_vis, true_y + brush_radius)

            yy, xx = np.mgrid[y_min:y_max, x_min:x_max]
            dist_sq = (xx - true_x) ** 2 + (yy - true_y) ** 2
            weight = np.exp(-dist_sq / (2 * (brush_radius / 2.0) ** 2))

            flow_x[y_min:y_max, x_min:x_max] += dx * weight * brush_strength
            flow_y[y_min:y_max, x_min:x_max] += dy * weight * brush_strength

            last_rx, last_ry = true_x, true_y
            update_display()

    elif event == cv2.EVENT_RBUTTONUP:
        is_r_dragging = False


def main():
    global g_tx, g_ty, g_scale, g_angle, g_alpha, brush_radius
    global img_vis_global, img_lwir_global, original_w_vis, original_h_vis
    global flow_x, flow_y

    files_lwir = sorted([f for f in os.listdir(DIR_LWIR) if f.lower().endswith(('.png', '.jpg'))])
    files_vis = sorted([f for f in os.listdir(DIR_VIS) if f.lower().endswith(('.png', '.jpg'))])

    img_pairs = list(zip(files_lwir, files_vis))
    if not img_pairs:
        print("🚨 이미지를 찾을 수 없습니다.")
        return

    print("🚀 [최종 픽셀 유동화 & WASD/TFGH 툴] 시작합니다.")
    print(f"📂 저장 폴더: {SAVE_DIR}")
    print("   [조작키] 이동(1px): w/a/s/d | 이동(10px): t/f/g/h (상/좌/하/우)")
    print("   [조작키] 크기: [ ] | 각도: , . | 투명도: - = | 저장&다음: u | 종료: q")

    cv2.namedWindow("Photoshop Liquify Aligner")
    cv2.setMouseCallback("Photoshop Liquify Aligner", mouse_callback)

    # 텍스트 로그 파일 경로 변경 (저장 폴더 안으로)
    log_file_path = os.path.join(SAVE_DIR, "liquify_parameters_log.txt")
    with open(log_file_path, "w") as f:
        f.write("=== Photoshop Liquify Parameters Log ===\n")

    current_idx = 0

    while current_idx < TARGET_IMAGES and current_idx < len(img_pairs):
        l_file, v_file = img_pairs[current_idx]

        path_lwir = os.path.join(DIR_LWIR, l_file)
        path_vis = os.path.join(DIR_VIS, v_file)

        img_vis_global = cv2.imread(path_vis)
        img_lwir_global = cv2.imread(path_lwir, cv2.IMREAD_GRAYSCALE)

        if img_vis_global is None or img_lwir_global is None:
            current_idx += 1
            continue

        original_h_vis, original_w_vis = img_vis_global.shape[:2]

        if flow_x is None or flow_y is None:
            flow_x = np.zeros((original_h_vis, original_w_vis), dtype=np.float32)
            flow_y = np.zeros((original_h_vis, original_w_vis), dtype=np.float32)

        update_display()
        print(f"\n📸 [{current_idx + 1}/{TARGET_IMAGES}] 작업 중: {l_file}")

        while True:
            key = cv2.waitKeyEx(30)
            if key == -1: continue

            # --- 단축키 세팅 ---
            if key == ord('q'):
                print("🛑 프로그램을 종료합니다.")
                cv2.destroyAllWindows()
                return

            # 4. 저장 키: 'u'
            elif key == ord('u'):
                center = (original_w_vis / 2, original_h_vis / 2)
                m_rot = cv2.getRotationMatrix2D(center, g_angle, g_scale)
                m_rot[0, 2] += g_tx
                m_rot[1, 2] += g_ty
                warped_global = cv2.warpAffine(img_lwir_global, m_rot, (original_w_vis, original_h_vis))
                map_x, map_y = np.meshgrid(np.arange(original_w_vis), np.arange(original_h_vis))
                warped_final = cv2.remap(warped_global, map_x.astype(np.float32) - flow_x,
                                         map_y.astype(np.float32) - flow_y, cv2.INTER_LINEAR)

                base_name = os.path.splitext(l_file)[0]

                # 저장 경로를 새로 만든 SAVE_DIR 로 변경
                save_path = os.path.join(SAVE_DIR, f"{base_name}_liquified.png")
                cv2.imwrite(save_path, warped_final)

                log_text = f"[{l_file}] Tx: {g_tx:.0f}, Ty: {g_ty:.0f}, Scale: {g_scale:.4f}, Angle: {g_angle:.2f}\n"
                with open(log_file_path, "a") as f:
                    f.write(log_text)

                npz_save_path = os.path.join(SAVE_DIR, f"{base_name}_flow_map.npz")
                np.savez(npz_save_path, flow_x=flow_x, flow_y=flow_y, g_tx=g_tx, g_ty=g_ty, g_scale=g_scale,
                         g_angle=g_angle)

                print(f"💾 [저장 완료] 결과물이 '{SAVE_DIR}' 폴더에 안전하게 저장되었습니다.")
                break

            elif key == ord('r'):
                flow_x = np.zeros((original_h_vis, original_w_vis), dtype=np.float32)
                flow_y = np.zeros((original_h_vis, original_w_vis), dtype=np.float32)
                print("♻️ 유동화 맵 초기화 완료")

            elif key == ord('9'):
                brush_radius = max(10, brush_radius - 10)
            elif key == ord('0'):
                brush_radius += 10
            elif key == ord('-'):
                g_alpha = max(0.0, g_alpha - 0.1)
            elif key == ord('='):
                g_alpha = min(1.0, g_alpha + 0.1)
            elif key == ord('['):
                g_scale -= 0.001
            elif key == ord(']'):
                g_scale += 0.001
            elif key == ord(','):
                g_angle += 0.1
            elif key == ord('.'):
                g_angle -= 0.1

            # 💡 [이동 키 완벽 분리]
            # 1픽셀 이동 (wasd)
            elif key == ord('w'): g_ty -= 1
            elif key == ord('s'): g_ty += 1
            elif key == ord('a'): g_tx -= 1
            elif key == ord('d'): g_tx += 1

            # 10픽셀 이동 (tfgh) - 대소문자 모두 허용
            elif key in (ord('t'), ord('T')): g_ty -= 10
            elif key in (ord('g'), ord('G')): g_ty += 10
            elif key in (ord('f'), ord('F')): g_tx -= 10
            elif key in (ord('h'), ord('H')): g_tx += 10

            update_display()

        current_idx += 1

    cv2.destroyAllWindows()
    print("🎉 모든 작업이 끝났습니다. 수고하셨습니다!")


if __name__ == '__main__':
    main()