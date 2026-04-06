# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

해상 영상 왜곡 보정 (Sea Wave Orthorectification). 선박 탑재 카메라 영상을 등간격 m/pixel 이미지로 변환하는 것이 목표.

## 참고 파일 경로

- 계획/흐름 문서: C:\Users\PC00\OneDrive\삼중과제 (한글 텍스트 파일들)

- Swell 영상: C:\Users\tilti\OneDrive\samjung\Swell_20260120_UTC1007

- Wind 영상: C:\Users\tilti\OneDrive\samjung\Wind_20260109_UTC1139

- 해상 정보: C:\Users\tilti\OneDrive\samjung\Weather_Info.xlsx

- 최근 보고자료: C:\Users\tilti\OneDrive\samjung\삼성중공업_성현_왜곡보정_2026_03_26.pptx

- 현재 코드: ./piza2.py

## 실행 방법

```bash

# v4 — wavelength 기반 (단순, 정확도 낮음)

python piza.py

# v8 — velocity 기반 (더 robust, 권장)

python piza2.py

```

영상 경로는 main()에 하드코딩됨. ROI 선택: 마우스 드래그 → Enter 확인 | r 재선택 | q 종료

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

### 핵심 물리 상수 (항차별 하드코딩)

| 변수 | 설명 |

|------|------|

| SOG_KNOTS, HEADING_DEG | 선박 상태 |

| SWELL_*, WIND_* | 기상 데이터 파라미터 |

| ENCOUNTER_SPEED_SWELL/WIND | 겉보기 파속 = phase_speed + SOG·cos(angle) |

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
