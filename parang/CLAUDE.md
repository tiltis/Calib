# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 언어 규칙

모든 응답, 주석, companion(Pricklewise 포함)은 **한국어**로 작성한다.

## 프로젝트 개요

해상 영상 왜곡 보정 (Sea Wave Orthorectification). 선박 탑재 카메라 영상을 등간격 m/pixel 이미지로 변환하는 것이 목표.

## 참고 파일 경로

- 계획/흐름 문서: C:\Users\PC00\OneDrive\삼중과제 (한글 텍스트 파일들)

- 영상 데이터: C:\Users\tilti\OneDrive\samjung\data\ (8개 세트)

  | 폴더 | 파일 수 | 특이사항 |
  |------|---------|----------|
  | Swell_20260120_UTC1007 | 7개 | 기준 세트 (알고리즘 검증 기준선) |
  | Wind_20260109_UTC1139 | 8개 | 저속(9.8kts) + 혼합파(92%) + 고파고(4.0m) |
  | Roll_20260123_UTC0454 | 1개 | 최고 파고(4.4m) + 롤링 조건 |
  | Roll_20260128_UTC0302 | 1개 | 롤링 조건 |
  | FlowOpti06_20260112_UTC1548 | 1개 | 혼합도 98% (swell:wind=51:49) |
  | SET01_20260115_UTC0819 | 1개 | following seas (enc_sw=2.8m/s, 극히 작음) |
  | SET07_20260116_UTC0745 | 1개 | 순수 너울(dom=99%), enc_sw=21.3m/s |
  | SET18_20260127_UTC0733 | 1개 | swell 지배(87%), 장파장(186m) |

- 해상 정보: C:\Users\tilti\OneDrive\samjung\Weather_Info.xlsx

- 최근 보고자료: C:\Users\tilti\OneDrive\samjung\삼성중공업_성현_왜곡보정_2026_03_26.pptx

- 현재 코드: ./piza2.py (v9, 수정 금지), ./2026-04-06/piza4.py (v11, 현업 권장), ./2026-04-06/piza5.py (v12, 실험용)

## 실행 방법

```bash
# 배치 처리 (권장) — 폴더/파일 선택 UI 포함
python 2026-04-06/batch_run.py

# 단독 실행 (단일 영상)
python 2026-04-06/piza4.py   # v11 현업 권장
python 2026-04-06/piza5.py   # v12 실험 (relief displacement)
```

batch_run.py 조작: 폴더 번호 선택 → 파일 목록 표시 → 엔터(전체) / 숫자(단일) / 2,3(복수)
ROI 선택: 마우스 드래그 → Enter 확인 | r 재선택 | q 종료
ROI는 같은 폴더 내 다음 파일에 자동 재사용 ({dir}_roi.json)

## 아키텍처

### piza.py (v4) — Wavelength 기반

1. ROI 선택

2. detect_crests_sobel() — CLAHE + Sobel Y + peak finding

3. estimate_pixel_scale() — crest spacing 비율로 perspective scale 추정

4. compute_ortho_matrix_isometric() — trapezoid→rectangle homography

5. 6개 윈도우로 실시간 시각화

### piza2.py (v8) — Velocity 기반 (메인)

1. ROI 선택

2. Phase 1 (캘리브레이션 ~20s): CrestTracker로 파봉 추적

3. get_velocity_vs_y() — 슬라이딩 윈도우 속도 추정

4. build_velocity_scale_map() — 선형회귀로 m/pixel(y) 산출, R² 낮으면 wind speed로 재시도

5. build_remap_tables() — cv2.remap() 용 비선형 워핑 테이블 생성

6. Phase 2: 캘리브레이션된 remap으로 실시간 재생, 실패시 homography fallback

### v8이 v4보다 나은 이유

- v4는 swell+wind 혼합파에서 실패

- v8은 행별 실제 파봉 이동속도를 측정하므로 파종 구분 불필요

- v8은 cv2.remap()으로 행별 비선형 스케일링 (v4는 단일 homography)

### piza3.py (v10) — XY 동시 보정

v9 + 가로(X) 방향 보정 추가:
- `scale_x = mpp_at_row / base_mpp`, `map_x = cx + outer(1/scale_x, cols-cx)`
- 상단(먼 거리) 좁은 파봉을 물리적 너비로 펼쳐서 방사형 왜곡 제거

### piza4.py (v11) — 현업 권장 버전

v10 + 5개 안정성/정확도 개선:
1. **2차 다항 회귀**: vel(y) 1차→2차 자동 선택 (R² 개선 ≥ 0.02 기준)
2. **mpp 단조성 강제**: `np.maximum.accumulate` — 접힘 아티팩트 방지
3. **cumsum off-by-one 수정**: 출력 상단 평탄 구간 제거
4. **출력 높이 상한**: roi_h × 3 — 메모리 폭발 방지
5. **코덱**: H264 우선 → mp4v 폴백 — 파일 크기 50~70% 감소

### piza5.py (v12) — 실험용 (relief displacement)

v11 + **파고 기반 3D 보정**:
- 파봉(+Hs/2)과 파곡(-Hs/2)의 원근 변위를 프레임별 동적 보정
- `H_CAMERA = 30m` (미지 — 선박 스펙 확인 시 정밀도 대폭 향상)
- `relief%` 슬라이더로 실시간 강도 조절
- **주의**: H_CAMERA가 추정값이라 현업 배포 전 검증 필요

### 핵심 물리 상수

| 변수 | 설명 |
|------|------|
| G = 9.81 | 중력 가속도 |
| CALIB_SECONDS = 20 | Phase 1 캘리브레이션 시간 |
| H_CAMERA = 30.0 | 카메라 해수면 위 높이 [m] (v12만) |
| weather_cache.json | xlsx에서 추출한 38세트 기상 파라미터 |

## 개발 이력

| 버전 | 파일 | 핵심 변경 |
|------|------|-----------|
| v4 | piza.py | wavelength 기반, crest spacing으로 homography 추정 |
| v8 | piza2.py (초기) | velocity 기반, CrestTracker + cv2.remap() |
| v9 | piza2.py | xlsx 자동 로딩(weather_cache.json), dominance 기반 enc 선택, output/ 저장 |
| v10 | 2026-04-06/piza3.py | XY 동시 보정 (가로방향 방사형 왜곡 제거) |
| v11 | 2026-04-06/piza4.py | 2차 회귀, 단조성, cumsum fix, out_h 상한, H264 코덱 **(현업 권장)** |
| v12 | 2026-04-06/piza5.py | relief displacement (파고 기반 3D 보정, 실험용) |

**piza2.py는 수정 금지.** 변경은 반드시 날짜 폴더 내 복사본에서.

## 현재 파일 구조

```
parang/
  piza2.py                  # v9 (수정 금지 — 안정 기준선)
  weather_cache.json        # xlsx에서 사전 추출한 38개 세트 기상 파라미터
  2026-04-06/
    piza3.py                # v10 (XY 보정)
    piza4.py                # v11 (현업 권장 — 2차 회귀, 안정성 개선)
    piza5.py                # v12 (실험 — relief displacement)
    batch_run.py            # 배치 처리 UI (현재 piza5 연결)
    make_report.py          # PPTX 보고서 자동 생성
    make_clips.py           # 원본+ortho 1분 클립 생성
    make_comparison.py      # 보정 전/후 비교 영상
    make_v9v10_doc.py       # v9 vs v10 비교 워드 문서
    add_version_slides.py   # 보고서에 버전 비교 슬라이드 추가
```

output/ 저장 위치: `C:\Users\tilti\OneDrive\samjung\output\`
- `{dir}_calib.json` — 캘리브레이션 결과 (mpp, R², enc_speed 등)
- `{dir}_ortho.mp4` — 보정된 영상
- `{dir}_roi.json` — ROI 좌표 (같은 폴더 다음 파일 자동 재사용)
- `clips/` — 1분 클립 (orig + ortho 페어), compare 영상
- `v9_vs_v10_비교.docx` — 버전 비교 워드 문서
- `report_orthorectification.pptx` — 메인 보고서 (15슬라이드)

## 진행 상황

```
[완료] v4 → v8 → v9 → v10 → v11 → v12 버전 개발
[완료] weather_cache.json 생성 (xlsx OneDrive 잠금 우회)
[완료] batch_run.py — 배치 처리 + 파일 선택 UI
[완료] 8개 세트 전체 배치 처리 (v10 기준) → calib.json + ortho.mp4 생성
[완료] 보고서 PPTX 생성 (15슬라이드, 버전 비교 포함)
[완료] 1분 클립 페어 생성 (orig + ortho × 8세트 = 16파일)
[완료] v9 vs v10 비교 워드 문서
[대기] v11(piza4)로 8개 세트 재배치 — 2차 회귀 효과 비교 필요
[실험] v12(piza5) relief displacement — H_CAMERA 확인 시 현업 투입 가능
```

## 알려진 이슈 및 한계

- **SET01 (following seas)**: enc_sw=2.8m/s로 극히 작음 → 캘리브레이션 불안정 가능
- **FlowOpti06 혼합도 98%**: swell:wind=51:49 → 어느 쪽도 dominant하지 않아 weighted 평균 사용
- **Roll 세트**: 선박 롤링으로 ROI 내 파도 방향 변동 → 속도 추정 R² 낮을 수 있음
- **등방성 가정 (v10~v11)**: 가로 스케일 = 세로 스케일 → 카메라 틸트 있으면 부정확
- **Relief displacement (v12)**: 파고에 의한 원근 변위 보정은 H_CAMERA 정확도에 의존 — 기본값 30m은 추정
- **v12 temporal flickering**: 프레임별 파봉 검출 노이즈로 출력 영상 떨림 가능 → temporal smoothing 미구현

## 작업 규칙

- Python 사용, 한글 주석

- 변경 전 반드시 백업

- 에러 나면 스스로 디버깅해서 해결

- 결과물은 C:\Users\tilti\OneDrive\samjung\output 에 저장

- 각 단계마다 git commit 남길 것

- 작업 날짜 폴더 생성하고 그 하위에 py 파일 만들기 (그리고 파일명은 직관적 이해가 쉽게 compact 하게 만들기)

## 보고서 규칙

- 작업 과정과 결과를 pptx로 정리할 것

- 스타일: 흰색 배경, 깔끔한 톤 (교수/기업 보고용)

- python-pptx 사용

- 각 슬라이드는 간결하게 핵심만

- 결과 영상은 30초 이내로 잘라서 첨부 (보정 전/후 비교)

- 영상 자르기는 opencv 또는 ffmpeg 사용

- pptx에 영상 직접 삽입 (embed video)

- 저장 경로: C:\Users\tilti\OneDrive\samjung\output

## 의존성

```

opencv-python

numpy

scipy (find_peaks, gaussian_filter1d)

openpyxl

python-pptx

```
