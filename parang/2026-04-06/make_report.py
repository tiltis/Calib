"""
make_report.py — 등거리 투영 보고서 PPTX 자동 생성

흐름:
  1. output/*.json 읽기 → 캘리브레이션 결과 수집
  2. 보정 전(원본) / 보정 후(ortho) 영상 30초 클립 생성 (opencv)
  3. python-pptx로 슬라이드 구성 + 영상 삽입
  4. output/report_orthorectification.pptx 저장

저장 구조:
  output/
    {dir}_calib.json        ← piza2.py 실행 후 생성됨
    {dir}_ortho.mp4         ← piza2.py 실행 후 생성됨
    clips/{dir}_orig30s.mp4 ← 이 스크립트가 생성
    clips/{dir}_ortho30s.mp4← 이 스크립트가 생성
    report_orthorectification.pptx
"""

import os
import json
import glob
import cv2
import numpy as np

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm

# ============================================================
# 경로 설정
# ============================================================
OUTPUT_DIR  = r"C:\Users\tilti\OneDrive\samjung\output"
VIDEO_BASE  = r"C:\Users\tilti\OneDrive\samjung"
CLIP_DIR    = os.path.join(OUTPUT_DIR, "clips")
CLIP_SEC    = 30       # 보정 전/후 클립 길이 (초)
SLIDE_W     = Inches(13.33)
SLIDE_H     = Inches(7.5)

# ============================================================
# 색상 / 스타일
# ============================================================
C_NAVY   = RGBColor(0x1E, 0x3A, 0x5F)   # 제목 네이비
C_BLUE   = RGBColor(0x2E, 0x75, 0xB6)   # 강조 파랑
C_GRAY   = RGBColor(0x40, 0x40, 0x40)   # 본문 회색
C_LGRAY  = RGBColor(0xD9, 0xD9, 0xD9)   # 구분선
C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK  = RGBColor(0x00, 0x00, 0x00)
FONT     = "맑은 고딕"


# ============================================================
# 유틸 — 영상 클립 생성 (opencv, 30초)
# ============================================================
def clip_video(src_path, dst_path, seconds=30):
    """
    src_path 영상의 앞 seconds초를 잘라 dst_path에 저장.
    이미 존재하면 스킵.
    """
    if os.path.exists(dst_path):
        print(f"  [클립 스킵] 이미 있음: {os.path.basename(dst_path)}")
        return True
    if not os.path.exists(src_path):
        print(f"  [클립 실패] 원본 없음: {src_path}")
        return False

    cap = cv2.VideoCapture(src_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_cut = int(fps * seconds)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(dst_path, fourcc, fps, (w, h))

    written = 0
    while written < total_cut:
        ret, frame = cap.read()
        if not ret: break
        writer.write(frame)
        written += 1

    cap.release()
    writer.release()
    print(f"  [클립 생성] {os.path.basename(dst_path)}  ({written/fps:.1f}s, {w}x{h})")
    return True


# ============================================================
# 유틸 — 썸네일 추출 (10초 지점)
# ============================================================
def extract_thumbnail(video_path, out_path, at_sec=10):
    """영상 at_sec 초 지점 프레임을 PNG로 저장"""
    if os.path.exists(out_path):
        return out_path
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * at_sec))
    ret, frame = cap.read()
    cap.release()
    if ret:
        cv2.imwrite(out_path, frame)
        return out_path
    return None


# ============================================================
# 유틸 — pptx 텍스트 박스
# ============================================================
def add_textbox(slide, text, left, top, width, height,
                font_size=18, bold=False, color=C_GRAY,
                align=PP_ALIGN.LEFT, font_name=FONT):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf    = txBox.text_frame
    tf.word_wrap = True
    p  = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name      = font_name
    run.font.size      = Pt(font_size)
    run.font.bold      = bold
    run.font.color.rgb = color
    return txBox


def add_rect(slide, left, top, width, height, fill_color):
    """배경 직사각형 추가"""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape


# ============================================================
# 슬라이드 1 — 표지
# ============================================================
def make_title_slide(prs, dir_names):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    # 상단 네이비 바
    add_rect(slide, 0, 0, SLIDE_W, Inches(1.4), C_NAVY)

    # 제목
    add_textbox(slide, "해상 영상 등거리 투영 알고리즘",
                Inches(0.5), Inches(0.2), Inches(12), Inches(0.9),
                font_size=32, bold=True, color=C_WHITE, align=PP_ALIGN.LEFT)

    # 부제목
    add_textbox(slide, "Wave Orthorectification  |  보정 전/후 비교 보고서",
                Inches(0.5), Inches(1.5), Inches(10), Inches(0.5),
                font_size=16, color=C_BLUE)

    # 처리 영상 목록
    names_str = "\n".join(f"  • {n}" for n in dir_names) if dir_names else "  (처리된 결과 없음 — piza2.py 먼저 실행)"
    add_textbox(slide, f"처리 영상:\n{names_str}",
                Inches(0.5), Inches(2.2), Inches(8), Inches(3.5),
                font_size=14, color=C_GRAY)

    # 날짜 / 출처
    add_textbox(slide, "삼성중공업 CCTV 기반 파랑 계측\n2026.04",
                Inches(9.5), Inches(6.5), Inches(3.5), Inches(0.8),
                font_size=11, color=C_GRAY, align=PP_ALIGN.RIGHT)

    # 하단 라인
    add_rect(slide, 0, Inches(7.2), SLIDE_W, Pt(3), C_NAVY)

    return slide


# ============================================================
# 슬라이드 2 — 알고리즘 개요
# ============================================================
def make_algo_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # 제목 바
    add_rect(slide, 0, 0, SLIDE_W, Inches(0.75), C_NAVY)
    add_textbox(slide, "알고리즘 개요  —  Velocity-based Orthorectification (v9)",
                Inches(0.3), Inches(0.1), Inches(12), Inches(0.55),
                font_size=20, bold=True, color=C_WHITE)

    # 흐름도 (텍스트 박스 5단계)
    steps = [
        ("① ROI 선택",        "마우스 드래그로\n해수면 영역 지정"),
        ("② 파봉 추적 (20s)", "CLAHE→Sobel→peak\n프레임간 이동 추적"),
        ("③ 속도 맵 구축",    "슬라이딩 윈도우\n(y, px/s) 선형 회귀"),
        ("④ m/px 보정",       "enc_speed / vel(y)\n= m/pixel(y)"),
        ("⑤ 등거리 투영",     "cv2.remap()으로\n행별 비선형 보정"),
    ]
    box_w = Inches(2.3)
    box_h = Inches(1.8)
    gap   = Inches(0.15)
    top   = Inches(1.3)

    for i, (title, body) in enumerate(steps):
        lft = Inches(0.3) + i * (box_w + gap)
        # 배경 박스
        add_rect(slide, lft, top, box_w, box_h, RGBColor(0xE8, 0xF0, 0xFB))
        # 단계 제목
        add_textbox(slide, title, lft + Inches(0.08), top + Inches(0.08),
                    box_w - Inches(0.16), Inches(0.5),
                    font_size=13, bold=True, color=C_NAVY)
        # 본문
        add_textbox(slide, body, lft + Inches(0.08), top + Inches(0.6),
                    box_w - Inches(0.16), Inches(1.1),
                    font_size=11, color=C_GRAY)
        # 화살표 (마지막 제외)
        if i < len(steps) - 1:
            add_textbox(slide, "→",
                        lft + box_w, top + Inches(0.7),
                        gap + Inches(0.1), Inches(0.5),
                        font_size=18, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER)

    # v8→v9 개선 내용
    note = (
        "v9 개선: ① Weather_Info.xlsx 자동 로딩  "
        "② Swell/Wind dominance 기반 encounter speed 자동 선택  "
        "③ 캘리브 결과 JSON + 등거리 영상 output 저장"
    )
    add_textbox(slide, note,
                Inches(0.3), Inches(3.4), Inches(12.7), Inches(0.5),
                font_size=11, color=C_BLUE)

    # 수식
    formula = "m/pixel(y)  =  encounter_speed  /  velocity(y)      encounter_speed = c_wave + SOG · cos(θ)"
    add_textbox(slide, formula,
                Inches(0.5), Inches(4.1), Inches(12), Inches(0.6),
                font_size=13, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER)

    # 물리 가정 요약
    assume = (
        "가정:  ① 해수면 평면 (파고 무시)  "
        "② 카메라 정지 (롤링/피칭 없음)  "
        "③ Pinhole 카메라 (렌즈 왜곡 없음)  "
        "④ encounter speed 일정"
    )
    add_textbox(slide, assume,
                Inches(0.5), Inches(4.9), Inches(12), Inches(0.5),
                font_size=10, color=RGBColor(0x80, 0x80, 0x80))

    add_rect(slide, 0, Inches(7.2), SLIDE_W, Pt(3), C_NAVY)
    return slide


# ============================================================
# 슬라이드 3 — 결과 요약 테이블
# ============================================================
def make_summary_slide(prs, calib_list):
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    add_rect(slide, 0, 0, SLIDE_W, Inches(0.75), C_NAVY)
    add_textbox(slide, "처리 결과 요약",
                Inches(0.3), Inches(0.1), Inches(12), Inches(0.55),
                font_size=20, bold=True, color=C_WHITE)

    if not calib_list:
        add_textbox(slide, "처리된 결과가 없습니다.\npiza2.py를 실행하면 output/*.json이 생성됩니다.",
                    Inches(1), Inches(2), Inches(11), Inches(2),
                    font_size=16, color=C_GRAY, align=PP_ALIGN.CENTER)
        add_rect(slide, 0, Inches(7.2), SLIDE_W, Pt(3), C_NAVY)
        return slide

    # 테이블 헤더
    headers = ["영상", "Method", "Enc(m/s)", "R²", "base m/px", "출력 크기"]
    col_w   = [Inches(3.8), Inches(1.6), Inches(1.4), Inches(1.0), Inches(1.5), Inches(1.8)]
    row_h   = Inches(0.45)
    tbl_top = Inches(0.9)
    lft     = Inches(0.3)

    # 헤더 행
    x = lft
    for h, cw in zip(headers, col_w):
        add_rect(slide, x, tbl_top, cw, row_h, C_NAVY)
        add_textbox(slide, h, x + Inches(0.05), tbl_top + Inches(0.05),
                    cw - Inches(0.1), row_h - Inches(0.05),
                    font_size=11, bold=True, color=C_WHITE)
        x += cw

    # 데이터 행
    for ri, c in enumerate(calib_list):
        y   = tbl_top + row_h * (ri + 1)
        bg  = RGBColor(0xF2, 0xF7, 0xFF) if ri % 2 == 0 else C_WHITE
        x   = lft
        enc   = f"{c.get('enc_speed', 0):.2f}"
        r2    = f"{c.get('r_sq', 0):.3f}" if c.get('r_sq') is not None else "—"
        mpp   = f"{c.get('base_mpp', 0):.3f}"
        sz    = f"{c['out_size'][0]}×{c['out_size'][1]}" if c.get('out_size') else "—"
        meth  = "remap" if c.get('use_remap') else "homography"
        vals  = [c.get('dir_name',''), meth, enc, r2, mpp, sz]

        for v, cw in zip(vals, col_w):
            add_rect(slide, x, y, cw, row_h, bg)
            add_textbox(slide, str(v), x + Inches(0.05), y + Inches(0.05),
                        cw - Inches(0.1), row_h - Inches(0.05),
                        font_size=10, color=C_GRAY)
            x += cw

    add_rect(slide, 0, Inches(7.2), SLIDE_W, Pt(3), C_NAVY)
    return slide


# ============================================================
# 슬라이드 4+ — 영상별 상세 (파라미터 + 영상 삽입)
# ============================================================
def make_video_slide(prs, calib, orig_clip, ortho_clip, thumb_orig, thumb_ortho):
    """
    왼쪽: 캘리브 파라미터 요약
    오른쪽: 보정 전(상) / 보정 후(하) 영상 또는 썸네일
    """
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    dir_name = calib.get('dir_name', '')
    add_rect(slide, 0, 0, SLIDE_W, Inches(0.75), C_NAVY)
    add_textbox(slide, f"결과: {dir_name}",
                Inches(0.3), Inches(0.1), Inches(12), Inches(0.55),
                font_size=18, bold=True, color=C_WHITE)

    # ---- 왼쪽: 파라미터 요약 ----
    wx = calib.get('weather', {})
    wv = calib.get('wave', {})
    r2   = calib.get('r_sq')
    mpp  = calib.get('base_mpp', 0)
    enc  = calib.get('enc_speed', 0)
    enc_lbl = calib.get('enc_label', '')
    meth = "remap (비선형)" if calib.get('use_remap') else "homography (fallback)"
    sz   = calib.get('out_size', [0, 0])

    params_text = (
        f"SOG:      {wx.get('sog_knots', 0):.1f} kts\n"
        f"Heading:  {wx.get('heading_deg', 0):.1f}°\n"
        f"\n"
        f"Swell  Hs={wx.get('swell_hs', 0):.2f}m  "
        f"Tp={wx.get('swell_tp', 0):.2f}s\n"
        f"Wind   Hs={wx.get('wind_hs', 0):.2f}m  "
        f"Tp={wx.get('wind_tp', 0):.2f}s\n"
        f"\n"
        f"Enc speed:  {enc:.2f} m/s\n"
        f"              ({enc_lbl})\n"
        f"\n"
        f"R²:          {f'{r2:.3f}' if r2 is not None else '—'}\n"
        f"base m/px:  {mpp:.4f}\n"
        f"방법:        {meth}\n"
        f"출력 크기:  {sz[0]}×{sz[1]}"
    )
    add_textbox(slide, params_text,
                Inches(0.3), Inches(0.9), Inches(4.2), Inches(5.8),
                font_size=12, color=C_GRAY)

    # ---- 오른쪽: 보정 전/후 영상 or 썸네일 ----
    vid_left  = Inches(4.8)
    vid_top_o = Inches(0.9)   # 원본(보정 전)
    vid_top_r = Inches(4.1)   # 결과(보정 후)
    vid_w     = Inches(8.2)
    vid_h     = Inches(3.0)

    # 라벨
    add_textbox(slide, "▶ 보정 전 (원본)",
                vid_left, vid_top_o - Inches(0.28), vid_w, Inches(0.28),
                font_size=11, bold=True, color=C_NAVY)
    add_textbox(slide, "▶ 보정 후 (등거리 투영)",
                vid_left, vid_top_r - Inches(0.28), vid_w, Inches(0.28),
                font_size=11, bold=True, color=C_BLUE)

    def try_embed_video(clip_path, thumb_path, left, top, width, height):
        """영상 삽입 시도 → 실패하면 썸네일 이미지로 대체"""
        if clip_path and os.path.exists(clip_path):
            try:
                slide.shapes.add_movie(
                    clip_path, left, top, width, height,
                    mime_type='video/mp4'
                )
                return True
            except Exception as e:
                print(f"  [영상 삽입 실패] {e}")
        # 썸네일 대체
        if thumb_path and os.path.exists(thumb_path):
            slide.shapes.add_picture(thumb_path, left, top, width, height)
            add_textbox(slide, "(영상 삽입 불가 — 썸네일)",
                        left, top + height - Inches(0.3), width, Inches(0.3),
                        font_size=9, color=RGBColor(0xAA, 0xAA, 0xAA), align=PP_ALIGN.CENTER)
        else:
            # 회색 박스
            add_rect(slide, left, top, width, height, RGBColor(0xCC, 0xCC, 0xCC))
            add_textbox(slide, "영상 없음\n(piza2.py 실행 후 생성)",
                        left, top + height // 2 - Inches(0.3), width, Inches(0.6),
                        font_size=12, color=C_GRAY, align=PP_ALIGN.CENTER)
        return False

    try_embed_video(orig_clip,  thumb_orig,  vid_left, vid_top_o, vid_w, vid_h)
    try_embed_video(ortho_clip, thumb_ortho, vid_left, vid_top_r, vid_w, vid_h)

    add_rect(slide, 0, Inches(7.2), SLIDE_W, Pt(3), C_NAVY)
    return slide


# ============================================================
# 메인
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CLIP_DIR,   exist_ok=True)

    # ---- calib JSON 수집 ----
    json_files  = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*_calib.json")))
    calib_list  = []
    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            calib_list.append(json.load(f))
    print(f"  calib JSON {len(calib_list)}개 발견")

    dir_names = [c.get('dir_name', '') for c in calib_list]

    # ---- 영상 클립 생성 ----
    clip_pairs = []   # (dir_name, orig_clip, ortho_clip, thumb_orig, thumb_ortho)
    for c in calib_list:
        dir_name   = c.get('dir_name', '')
        video_file = c.get('video', '')
        orig_src   = os.path.join(VIDEO_BASE, dir_name, video_file)
        ortho_src  = os.path.join(OUTPUT_DIR, f"{dir_name}_ortho.mp4")

        orig_clip  = os.path.join(CLIP_DIR, f"{dir_name}_orig30s.mp4")
        ortho_clip = os.path.join(CLIP_DIR, f"{dir_name}_ortho30s.mp4")
        thumb_orig = os.path.join(CLIP_DIR, f"{dir_name}_orig_thumb.png")
        thumb_rtho = os.path.join(CLIP_DIR, f"{dir_name}_ortho_thumb.png")

        print(f"\n  [{dir_name}]")
        clip_video(orig_src,  orig_clip,  CLIP_SEC)
        clip_video(ortho_src, ortho_clip, CLIP_SEC)
        extract_thumbnail(orig_src,  thumb_orig)
        extract_thumbnail(ortho_src, thumb_rtho)

        clip_pairs.append((dir_name, orig_clip, ortho_clip, thumb_orig, thumb_rtho))

    # ---- PPTX 생성 ----
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    print("\n  PPTX 슬라이드 생성 중...")

    make_title_slide(prs, dir_names)
    print("  슬라이드 1: 표지")

    make_algo_slide(prs)
    print("  슬라이드 2: 알고리즘 개요")

    make_summary_slide(prs, calib_list)
    print("  슬라이드 3: 결과 요약 테이블")

    for c, (dir_name, orig_clip, ortho_clip, thumb_orig, thumb_ortho) in zip(calib_list, clip_pairs):
        make_video_slide(prs, c, orig_clip, ortho_clip, thumb_orig, thumb_ortho)
        print(f"  슬라이드 +: {dir_name}")

    if not calib_list:
        # 데이터 없어도 표지+개요+빈 요약 3장은 만들어둠
        print("  (calib 결과 없음 - 표지/개요/빈요약 3장만 생성)")

    out_path = os.path.join(OUTPUT_DIR, "report_orthorectification.pptx")
    prs.save(out_path)
    print(f"\n  [완료] {out_path}")
    print(f"  슬라이드 수: {len(prs.slides)}")


if __name__ == '__main__':
    main()
