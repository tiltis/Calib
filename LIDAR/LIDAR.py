import math
import matplotlib.pyplot as plt
import numpy as np
from rplidar import RPLidar
import time

PORT_NAME    = 'COM6'
BAUDRATE     = 256000
MAX_DIST_MM  = 12000
RESOLUTION   = 60      # 격자 크기 (mm)
MIN_HITS     = 3       # 최소 감지 횟수 (노이즈 제거)
UPDATE_EVERY = 10      # 화면 갱신 주기 (스캔 횟수)

GRID_SIZE = (2 * MAX_DIST_MM) // RESOLUTION
grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.int16)

def run_static_map():
    print(f"[{PORT_NAME}] 연결 중...")
    lidar = RPLidar(PORT_NAME, baudrate=BAUDRATE, timeout=3)
    lidar.reset();       time.sleep(2)
    lidar.clean_input()
    lidar.start_motor(); time.sleep(2)
    lidar.clean_input()

    fig, ax = plt.subplots(figsize=(9, 9))
    fig.patch.set_facecolor('#111111')
    ax.set_facecolor('#111111')
    ax.set_title("LiDAR Occupancy Grid Map", color='white', fontsize=13)
    ax.axis('off')

    # imshow로 격자 렌더링 (scatter보다 훨씬 빠름)
    img_data = np.zeros((GRID_SIZE, GRID_SIZE, 3), dtype=np.uint8)
    im = ax.imshow(img_data, origin='lower',
                   extent=[-MAX_DIST_MM, MAX_DIST_MM, -MAX_DIST_MM, MAX_DIST_MM])

    # 거리 눈금 원
    for r in range(2000, MAX_DIST_MM + 1, 2000):
        ax.add_patch(plt.Circle((0, 0), r, fill=False,
                                color='white', alpha=0.1, linestyle='--', linewidth=0.7))
        ax.text(r + 150, 150, f'{r//1000}m', color='white', fontsize=7, alpha=0.3)

    ax.plot(0, 0, 'o', color='cyan', markersize=8, zorder=5)

    status = ax.text(0.02, 0.98, "스캔 누적 중...", transform=ax.transAxes,
                     color='lime', fontsize=9, va='top',
                     bbox=dict(boxstyle='round', fc='black', alpha=0.6))

    buf_a, buf_d = [], []
    scan_num = 0

    def update_display():
        # 격자 → RGB 이미지 변환 (numpy 연산만 사용)
        occupied = grid >= MIN_HITS
        intensity = np.clip((grid / 20.0) * 255, 0, 255).astype(np.uint8)
        img = np.zeros((GRID_SIZE, GRID_SIZE, 3), dtype=np.uint8)
        img[occupied, 1] = intensity[occupied]        # Green 채널
        img[occupied, 0] = (intensity[occupied] * 0.5).astype(np.uint8)  # Red 살짝
        im.set_data(img)

    try:
        print(f"맵핑 시작! | 해상도: {RESOLUTION}mm/셀 | 갱신: {UPDATE_EVERY}스캔마다")
        print("종료: 창 닫기 또는 Ctrl+C")

        for new_scan, quality, angle, distance in lidar.iter_measures(max_buf_meas=3000):
            if new_scan and buf_a:
                scan_num += 1

                # 벡터화된 격자 업데이트 (Python 루프 없음)
                a = np.radians(np.array(buf_a))
                d = np.array(buf_d, dtype=np.float32)
                cx = ((d * np.cos(a) + MAX_DIST_MM) / RESOLUTION).astype(int)
                cy = ((d * np.sin(a) + MAX_DIST_MM) / RESOLUTION).astype(int)

                mask = (cx >= 0) & (cx < GRID_SIZE) & (cy >= 0) & (cy < GRID_SIZE)
                np.add.at(grid, (cy[mask], cx[mask]), 1)

                buf_a.clear(); buf_d.clear()

                if scan_num % UPDATE_EVERY == 0:
                    update_display()
                    occupied = int(np.sum(grid >= MIN_HITS))
                    status.set_text(f"스캔 {scan_num}회 | 벽 셀: {occupied:,}개")
                    plt.pause(0.001)

            if new_scan:
                buf_a.clear(); buf_d.clear()

            if quality > 0 and 0 < distance <= MAX_DIST_MM:
                buf_a.append(angle)
                buf_d.append(distance)

            if not plt.fignum_exists(fig.number):
                break

    except KeyboardInterrupt:
        print("\n중지")
    except Exception as e:
        print(f"\n에러: {e}")
    finally:
        lidar.stop()
        lidar.stop_motor()
        lidar.disconnect()
        plt.close()


if __name__ == '__main__':
    run_static_map()
