# UV-DMD 인수인계 (파이썬 개발용)

TI DLP Discovery 4100 DMD에 BMP 패턴을 출력하는 파이썬 도구를 개발하는 프로젝트다.
이 문서는 이전 세션의 결과를 다음 세션이 그대로 이어받기 위한 것이다.
**확인된 사실**과 **아직 모르는 것**을 구분해서 적었으니, 모르는 것을 사실처럼 쓰지 말 것.

## 0. 작업 방식 (중요)

- 응답은 한국어로 하고, 설명할 때는 **왜 그렇게 해야 하는지**를 함께 설명한다 (사용자 요청).
- Claude는 클라우드 컨테이너에서 동작한다. **사용자의 Windows 장비 PC, DMD 장비는 직접 보거나 실행할 수 없다.**
  코드를 이 저장소 브랜치에 푸시하면 사용자가 장비 PC에서 `git pull` 후 실행하고, 출력/오류 캡처를 보내 준다.
  따라서 장비 동작은 사용자의 캡처로만 검증할 수 있다.
- 작업 브랜치: `claude/laughing-hopper-dwia8k` (저장소 `jeongbinmin/uv-dmd`). 여기에만 푸시하고, PR은 사용자가 요청할 때만 만든다.
  저장소에는 다른 세션이 만든 `claude/compassionate-bohr-5acr9s`, `claude/dreamy-heisenberg-wq9eni` 브랜치도 있으나 이 작업과 무관하다.

## 1. 장비 PC 환경 (사용자 PC, Windows)

| 항목 | 값 |
|---|---|
| 저장소 clone 위치 | `C:\DLP4100_Control\uv-dmd` |
| `dmd_display.py` 위치 / 작업 디렉터리 | `C:\DLP4100_Control` |
| 테스트 BMP 폴더 | `C:\DLP4100_Control\test_bmp` |
| **32-bit** python.exe (DMD 제어에 사용) | `C:\Users\DPEG_Thinkpad\AppData\Local\Programs\Python\Python312-32\python.exe` |
| 다른 파이썬 (64-bit, DMD 제어에 쓰면 안 됨) | `...\Python\Python312\python.exe`, `...\Python\Python38\python.exe` |
| USB DLL | `C:\Windows\SysWOW64\D4100_usb.dll` |
| FPGA 이미지 | `C:\Program Files (x86)\D4100Explorer\D4100_GUI_FPGA.bin` |
| DMD 종류 (스크립트 로그) | DLP9500/DLP9500UV 0.95 1080p, 1920x1080 |

- DMD 제어는 **반드시 32-bit 파이썬**으로 한다. USB DLL이 32-bit(SysWOW64)이라 64-bit로 호출하면 로드에 실패해서 원인 파악이 어려워진다.
  BMP 생성(`mas20_*.py`, `make_test_bmps.py`)은 numpy/pillow가 있는 아무 파이썬이나 된다.
- 32-bit 확인: `python.exe -c "import struct; print(struct.calcsize('P')*8)"` → `32`.

## 2. dmd_display.py 인터페이스 (실장비에서 검증됨)

**이 파일은 이 저장소에 없고, 이전 세션은 내용을 본 적이 없다.** 아래는 사용자가 알려 준 사양과 실행 로그에서 확인된 동작뿐이다.
(WORK_LOG.md, README.md도 사용자가 처음에 언급했지만 이 저장소에는 없다. 필요하면 사용자에게 요청할 것.)

호출:

```
"<32-bit python.exe>" "C:\DLP4100_Control\dmd_display.py" "<BMP 전체경로>"
```

- BMP는 **정확히 1920x1080**, 흰 픽셀 = 미러 ON, 검은 픽셀 = OFF. 크기가 다르면 오류.
- 성공: 종료 코드 0, stdout 마지막 줄 `SUCCESS`. 실패: 종료 코드 1, stdout 마지막 줄 `FAILED`.
- 로그(`[INFO]`, `[OK]`, `[ERROR]`)와 `SUCCESS`/`FAILED`는 **모두 stdout**으로 나온다. stdout/stderr를 파일로 분리해 본 것은 크기 불일치 실패 케이스 한 번뿐이고, 그때 stderr는 비어 있었다. 성공 케이스는 분리해서 확인하지 않았다.
  `[ERROR]` 원인 줄은 마지막 줄(`FAILED`) 바로 앞에 있다. (파이썬 자체가 죽는 경우의 traceback은 stderr로 갈 수 있으나 확인하지 않았다.)
- `--hold` 옵션은 쓰지 않는다 (프로세스가 끝나지 않는다). `--resize` 옵션은 쓰지 않는다 (크기 오류를 숨기고 늘려서 성공시킨다).
- **동시에 두 프로세스를 실행하면 안 된다.** USB를 한 프로세스만 쓴다. TI GUI(D4100 Explorer)가 열려 있어도 안 된다. 호출은 반드시 직렬로 한다.
- 장비 전원을 켠 뒤 **첫 호출은 FPGA 로드로 더 오래 걸린다.** 소요 시간은 **아직 측정하지 않았다** (임의 숫자로 타임아웃을 정하지 말고 먼저 측정할 것).

### 실장비 cmd 실행 결과 (사용자가 직접 실행, 이전 세션에서 확인됨)

| 입력 | 결과 |
|---|---|
| `step_000001.bmp` (왼쪽 절반 흰색) | `SUCCESS`, 코드 0, 패턴 정상 반영. 로그: `board is in power-on state, loading FPGA...`, `image: 1920x1080 mode=L`, `ON pixels: 1036800 / 2073600 (50.0%)` |
| `bad_size_500x500.bmp` | `FAILED`, 코드 1, `[ERROR] image is 500x500 but the DMD is 1920x1080. Fix the BMP, or pass --resize ...` |
| 장비 미연결/전원 꺼짐 | `FAILED`, 코드 1, `[ERROR] GetNumDev() = 0: no DLP Discovery 4100 found. Check USB cable, power and the 'TI D4100 Explorer' driver in Device Manager.` |

세 경우 모두 종료 코드와 마지막 줄이 서로 일치했다. 8비트 흑백(`mode=L`) BMP를 정상 수용한다.

## 3. 저장소 파일

| 파일 | 역할 |
|---|---|
| `mas20_random_csv_file.py` | 테스트용 랜덤 서열 CSV 생성. 기본 1080행 x 1920열, `random_sequences_1920x1080.csv`, 서열 길이 15~25, 알파벳 `ACGT`, seed 1234 |
| `mas20_bmp_file_maker.py` | 서열 CSV → step별 BMP(1920x1080) 생성 (아래 4절) |
| `make_test_bmps.py` | 장비 테스트용 BMP 3장 생성 (아래 5절) |
| `HANDOFF.md` | 이 문서 |

## 4. BMP 생성기 (`mas20_bmp_file_maker.py`)

### 개념
엑셀에서 저장한 CSV의 **셀 하나 = DMD 픽셀 하나**이고, 셀의 문자열이 그 픽셀에서 합성할 서열(예: `ACGTTA...`)이다.
step마다 어떤 염기를 붙일지 정하고, 그 염기가 붙는 픽셀만 흰색인 BMP를 한 장 만든다.

### 알고리즘 (원본 코드를 분석한 결과, 동작을 그대로 유지함)
매 step:
1. 남은 문자열 중 **최대 길이**를 찾는다.
2. 최대 길이를 가진 셀들의 **첫 글자 중 최빈 문자**를 이번 step의 염기로 고른다. 동률이면 행 우선 스캔에서 먼저 나온 글자.
3. 그 글자로 시작하는 **모든 셀**(길이와 무관)의 첫 글자를 1개 삭제한다.
4. 삭제가 일어난 셀 위치만 흰색(255)인 BMP를 저장한다.
5. 모든 셀이 빌 때까지 반복한다.

(긴 서열을 먼저 끝내는 쪽으로 염기를 고르는 그리디 방식이라 전체 step 수를 줄인다. 최대 길이가 아닌 셀도 같은 글자로 시작하면 함께 소비한다.)

### 원본 대비 변경점
- 출력 BMP는 **항상 1920x1080 고정** (L 모드 8비트, 흰색 255 = ON). 저장 직후 파일을 다시 열어 크기를 검증한다.
- 그리드가 DMD보다 작으면 `--align`(기본 `center`, `topleft` 가능)으로 배치하고 나머지는 검정(OFF). `--scale N`은 셀 하나를 NxN 픽셀로 확대한다.
- 그리드(x scale)가 1920x1080보다 크면 **오류로 중단**한다. 잘라내면 일부 셀이 조용히 빠져 합성이 틀리기 때문이다.
- 200만 셀(1920x1080)을 다루기 위해 numpy로 벡터화했다 (선택 규칙은 동일).
  실행 시간은 풀 해상도 랜덤 CSV 기준 이 클라우드 환경에서 약 7초(86 step)였다. 사용자 PC에서는 측정하지 않았다.
- CSV는 `utf-8-sig`로 읽고(엑셀 "CSV UTF-8"의 BOM이 첫 셀 첫 글자로 들어가는 문제 방지), 디코딩에 실패하면 `cp949`로 재시도한다.
- 파일명은 기본 `step_000001.bmp`처럼 **번호만** 쓴다 (번호로 경로를 예측할 수 있게). `--char_in_name`을 주면 `step_000001A.bmp`처럼 염기 문자가 붙는다.
  어떤 step이 어떤 염기인지는 `sequence_order.txt`(문자만 이어붙임), `sequence_order.tsv`, `steps_log.tsv`에 기록된다.
- 부가 출력: `final_grid.txt`(남은 문자열, 정상 종료면 전부 빈 문자열).

### 사용
```
python mas20_bmp_file_maker.py --infile <csv> --outdir <BMP 출력 폴더> [--align center|topleft] [--scale N] [--char_in_name] [--max_steps N] [--no_order]
```
- `--infile` 생략 시 스크립트 폴더의 가장 큰 `.csv`를 자동 선택, `--outdir` 생략 시 `스크립트폴더/<csv 파일명>`.
- 의존성: `numpy`, `pillow`.

### 검증된 것
- 작은 그리드(37x53, 길이 0~6, 알파벳 `ACGTN`; 빈 셀/동률/짧은 셀 포함)에서 원본 스크립트와 비교: 27 step의 파일명, 픽셀, `sequence_order`, `final_grid` 모두 일치.
- 500x500 그리드가 중앙(x 710~1209, y 290~789)에 놓임, 픽셀 값은 0/255뿐.
- 1081행 그리드는 오류 종료(exit 1). BOM이 붙은 CSV 정상 인식.
- 이 검증용 비교 스크립트는 저장소에 커밋하지 않았다 (필요하면 다시 만들 것. 원본은 사용자가 업로드한 `mas20_bmp_file_maker.py`).

### 사용자가 정한 것
- 엑셀 표는 **1920열 x 1080행**(셀 1개 = DMD 픽셀 1개)으로 쓴다.
- 미결: 표가 정확히 1920x1080이 아니면 조용히 중앙 배치되어 어긋날 수 있다. 크기가 정확하지 않으면 오류로 막는 `--strict` 옵션을 제안했으나 **사용자 답을 받지 못했다.** 추가 전에 확인할 것.

## 5. 테스트 BMP (`make_test_bmps.py`)

```
python make_test_bmps.py <출력폴더>
```
- `step_000001.bmp`: 왼쪽 절반만 흰색 (방향 확인용)
- `step_000002.bmp`: 120px 체커보드
- `bad_size_500x500.bmp`: 크기 불일치 실패 테스트용

전체 흰색(전 미러 ON)은 일부러 만들지 않았다. 광원이 그대로 나가는 것을 피하기 위해서다. **장비 테스트 때는 UV 광원을 끄거나 막아 둘 것.**

## 6. 남은 일 / 다음 단계 후보

사용자가 "이제 파이썬으로 개발한다"고 했을 뿐 구체적인 다음 기능은 정하지 않았다. 아래는 이전 세션이 본 후보이며, **무엇을 먼저 할지는 사용자에게 확인할 것.**

1. **step 순서대로 BMP를 DMD에 출력하는 파이썬 제어 프로그램** (`dmd_display.py`를 subprocess로 호출하거나 import). 만들 때 지킬 점:
   - 호출은 직렬로, 이전 호출이 끝난 뒤 다음 호출. TI GUI 종료 상태 전제.
   - 판정은 종료 코드 0, stdout 마지막 줄 `SUCCESS`, 프로세스 시작 오류 없음 세 조건을 **모두** 확인한다 (각각 다른 실패를 잡는다: 시작 실패 / 비정상 종료 / 출력 불일치). stdout이 비어도 실패.
   - 오류 원인(`[ERROR]` 줄)은 마지막 줄 앞에 있으므로 실패 시 stdout 전체를 기록한다. stderr도 함께 기록한다.
   - 소요 시간(특히 전원 직후 첫 호출과 이후 호출)을 측정해 기록하고, 그 값으로 타임아웃을 정한다.
2. `--strict` 옵션 추가 여부 결정 (4절).
3. 전체 파이프라인 점검: 1920x1080 엑셀 CSV → `mas20_bmp_file_maker.py` → step 순서 출력. 실제 사용자 CSV로는 아직 돌려 보지 않았다.
4. 한글/공백이 들어간 폴더 경로의 BMP 호출은 **검증하지 않았다.** 사용자의 실제 BMP 폴더에 한글과 공백이 있다 (`...\예시파일\dmd bmp이미지 예시파일\random_sequences_500x500`). 문제가 생기면 영문 경로로 옮기는 것이 가장 단순하다.
5. `dmd_display.py`의 소스를 사용자에게 받아 인터페이스를 코드로 확인하면 좋다 (현재는 로그와 사용자 설명으로만 안다).

## 7. 모르는 것 (사실처럼 쓰지 말 것)

- `dmd_display.py`의 내용, WORK_LOG.md의 내용.
- 전원 직후 첫 호출의 소요 시간, 이후 호출의 소요 시간.
- 성공 케이스와 장비 미연결 케이스에서 stderr가 비어 있는지 (분리해서 확인한 것은 크기 불일치 실패 한 번뿐).
- 사용자 PC에서의 BMP 생성기 실행 시간과 메모리.
