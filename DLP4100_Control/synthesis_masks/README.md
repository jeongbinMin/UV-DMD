# synthesis_masks — 서열 CSV → 사이클별 DMD 마스크 BMP (1920×1080)

DMD의 마이크로미러 1개 = CSV의 칸 1개. 격자 크기가 DMD와 같아서(1920×1080) 만들어진 BMP를 크기 변환 없이 `../dmd_display.py`에 줄 수 있습니다.

```
python make_random_csv.py                 # random_sequences_1920x1080.csv 생성 (시드 1234, 길이 15~25, ACGT)
python make_step_bmps.py                  # 위 CSV로 random_sequences_1920x1080_bmp\step_000001A.bmp ... 생성
python ..\dmd_display.py random_sequences_1920x1080_bmp\step_000001A.bmp   (A 자리는 1단계의 염기 글자)
```

필요: `pip install -r ..\requirements.txt` (Pillow). DMD 쪽 장비 없이도 두 스크립트는 실행됩니다.

## 알고리즘 (`make_step_bmps.py`)

기존 `mas20_bmp_file_maker.py`와 같은 탐욕적 공통 상위 서열 방식입니다.

1. 남은 서열 중 가장 긴 길이 `max_len`을 구함
2. 길이가 `max_len`인 서열들의 **첫 글자 중 최빈 글자** 선택(동률이면 행 우선 스캔에서 먼저 나온 글자)
3. **길이와 상관없이** 그 글자로 시작하는 모든 칸의 첫 글자를 하나씩 삭제 → 그 칸들이 이번 사이클에 노광할 곳(BMP에서 흰색 255)
4. 모든 서열이 빌 때까지 반복

선택한 글자를 이은 것이 합성 순서(`sequence_order.txt`)입니다. 모든 서열이 그 순서의 부분 서열이므로, BMP를 step 순서대로 노광하면 각 칸의 서열이 **첫 글자부터 마지막 글자 순으로** 만들어집니다. 사이클 수가 최소라는 보장은 없습니다(근사).

## 출력

| 파일 | 내용 |
|---|---|
| `step_000001A.bmp` ... | 사이클별 마스크. 8비트 흑백, 0/255, 1920×1080. 이름 끝의 글자는 그 step의 염기. `--no-base`를 주면 글자 없이 `step_000001.bmp` |
| `sequence_order.txt` | 전체 합성 순서(글자 이어붙임) |
| `steps_log.tsv` | step, 글자, 최대 길이, 노광 칸 수, 파일명 |

## 검증한 것 (1920×1080, 시드 1234, 이 환경에서)

- CSV가 기존 `mas20_random_csv_file.py`의 출력과 **바이트 단위로 같음**
- 합성 순서와 모든 step BMP가 기존 스크립트 결과와 **픽셀 단위로 같음**(86 step)
- BMP 86장에서 207만 개 칸의 서열을 복원 → 원본 CSV와 **불일치 0개**
- `dmd_display.py`가 BMP를 읽고 전송 데이터가 정확히 259,200 bytes
- 실행 시간 약 40초, BMP 약 173MB(86장). 한 번만 돌리면 되는 오프라인 작업

## 기존 스크립트에서 바꾼 점

| 바꾼 것 | 이유 |
|---|---|
| 격자 크기를 1920×1080으로 고정 검사 | BMP가 DMD와 크기가 다르면 `dmd_display.py`가 오류를 냄 |
| 짧은/긴 행을 조용히 채우지 않고 오류 | 크기 오류를 숨기지 않기 위해 |
| `--scale` 제거 | 정수 배율로는 1920×1080을 만들 수 없음 |
| (기존과 같음) 파일명 `step_000001A.bmp` | LabVIEW가 `\step_` + 6자리 번호 + **염기 글자** + `.bmp`로 이름을 만드는 것으로 보임(String Subset 노드). 글자 없는 이름이 필요하면 `--no-base` |
| 이모지 없는 ASCII 출력, 끝에 `SUCCESS` | Windows 한국어 콘솔(cp949)에서 `UnicodeEncodeError`를 피하기 위해 |
| 저장 후 BMP를 다시 읽어 노광 칸과 비교 | 파일이 의도한 칸을 정확히 담았는지 매 step 확인 |

## 확인이 필요한 것

- CSV의 글자 순서가 **실제 합성 순서와 같은지**(알고리즘은 첫 글자부터 지움). 서열을 거꾸로 합성하는 방식이면 CSV를 뒤집어서 넣어야 함.
- 격자가 1080행보다 작을 때(예: 860행)의 배치 방법은 정해지지 않음. 지금은 오류로 막혀 있음.
- 흰색 = 노광(미러 ON) 극성은 `dmd_display.py` 기본값(흰색 = ON)과 같음. 광학계에서 반대이면 `--invert`.
