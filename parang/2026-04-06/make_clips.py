"""
각 데이터 세트에 대해 원본 1분 + ortho 1분 클립을 페어로 생성.
저장 위치: samjung/output/clips/{name}_orig_1min.mp4, {name}_ortho_1min.mp4
"""
import os, json, glob, subprocess

FFMPEG = r"C:\Users\tilti\anaconda3\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
OUT_DIR = r"C:\Users\tilti\OneDrive\samjung\output"
DATA_DIR = r"C:\Users\tilti\OneDrive\samjung\data"
CLIPS_DIR = os.path.join(OUT_DIR, "clips")
DURATION = 60  # 초

os.makedirs(CLIPS_DIR, exist_ok=True)


def trim_video(src, dst, duration=60):
    """ffmpeg로 영상을 duration초만 잘라서 저장 (재인코딩 없이 copy)"""
    if os.path.exists(dst):
        print(f"  [스킵] 이미 존재: {os.path.basename(dst)}")
        return
    cmd = [
        FFMPEG, "-y",
        "-ss", "0",
        "-i", src,
        "-t", str(duration),
        "-c", "copy",       # 재인코딩 없이 빠르게
        "-avoid_negative_ts", "make_zero",
        dst
    ]
    print(f"  -> {os.path.basename(dst)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # copy 실패 시 재인코딩으로 재시도
        print(f"  [copy 실패, 재인코딩 시도]")
        cmd2 = [
            FFMPEG, "-y",
            "-ss", "0",
            "-i", src,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac",
            dst
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0:
            print(f"  [에러] {r2.stderr[-200:]}")


def main():
    calib_files = sorted(glob.glob(os.path.join(OUT_DIR, "*_calib.json")))
    print(f"총 {len(calib_files)}개 세트 처리\n")

    for cj in calib_files:
        with open(cj) as f:
            d = json.load(f)
        name = d["dir_name"]
        video = d["video"]

        orig_path = os.path.join(DATA_DIR, name, video)
        ortho_path = os.path.join(OUT_DIR, f"{name}_ortho.mp4")

        print(f"[{name}]")

        # 원본 1분 클립
        if os.path.exists(orig_path):
            trim_video(orig_path, os.path.join(CLIPS_DIR, f"{name}_orig_1min.mp4"), DURATION)
        else:
            print(f"  [경고] 원본 없음: {orig_path}")

        # ortho 1분 클립
        if os.path.exists(ortho_path):
            trim_video(ortho_path, os.path.join(CLIPS_DIR, f"{name}_ortho_1min.mp4"), DURATION)
        else:
            print(f"  [경고] ortho 없음: {ortho_path}")

        print()

    print("완료! 저장 위치:", CLIPS_DIR)


if __name__ == "__main__":
    main()
