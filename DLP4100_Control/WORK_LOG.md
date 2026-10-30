# DLP4100 BMP 출력 검증 — 작업 기록

TI DLP Discovery 4100을 오픈소스 Python 코드로 제어해 BMP 한 장을 DMD에 출력할 수 있는지 검증한 작업의 전체 기록입니다.
사용법은 [README.md](README.md), 이 문서는 **무엇을 왜 어떻게 결정했고 무엇이 실제로 확인되었는지**를 남긴 것입니다.

## 1. 결과 요약

**성공 조건 충족**: Windows PC에서 Python 스크립트를 실행하면 지정한 BMP가 DLP4100 DMD에 정상 출력됨.

```
python dmd_display.py "C:\DMD\mask.bmp"
```

| 확인 항목 | 결과 |
|---|---|
| 장비 | DLP Discovery 4100, DMD type 0 = DLP9500/DLP9500UV, 1920×1080, 15블록×72행 |
| 환경 | Windows 10 (10.0.19043), 32-bit Python 3.12, `D4100_usb.dll`(`C:\Windows\SysWOW64`) |
| BMP 출력 | `test_mask.bmp`의 글자 `F`가 정상 방향, 1픽셀 대각선이 매끈 |
| 비트 순서 | 기본값(한 바이트에서 왼쪽 픽셀 = bit7)이 맞음. `--lsb-first` 불필요 |
| 종료 후 유지 | 스크립트 종료 후에도 패턴 유지 |
| 전원 투입 직후 | FPGA 자동 로드 후 출력 성공 |
| 명령줄 호출 | 성공 시 종료 코드 0, 없는 파일이면 `FAILED`와 종료 코드 1 |

## 2. 구현 경로를 고른 이유

**Python(32-bit) + `ctypes`로 `D4100_usb.dll` 직접 호출 + Pillow로 BMP 변환**

1. TI API 문서(DLPU039A §4)가 "ActiveX는 구형이며 DLL 직접 호출을 권장"이라고 명시.
2. `FileToFrameBuffer`, `LoadToDMD`, `ConvertImage`는 **ActiveX(OCX) 전용**. DLL(§6)에는 `LoadData`, `LoadControl`, `ClearFifos`, `SetBlkMd/Ad`, `SetRowMd/Addr` 같은 저수준 함수만 있음.
3. 따라서 BMP → 1-bit 데이터 변환은 Python이 직접 해야 함. 두 API를 섞지 않았음.
4. DMD가 3종(1920×1080, 1024×768, 1280×800)으로 해상도·블록 구조가 달라서, `GetDMDTYPE`으로 **자동 감지**하고 해상도를 하드코딩하지 않음.

## 3. 오픈소스 조사

| 프로젝트 | 라이선스 | 판단 |
|---|---|---|
| [Sharvaj/DLP-Discovery-DMD-Control](https://github.com/Sharvaj/DLP-Discovery-DMD-Control) | Apache-2.0 | 로드·리셋 호출 순서의 기준(Python으로 재작성, 라이선스 사본·출처 유지). 1920×1080 전용. `LoadBMP`는 블록 로드 루프가 `i=1`부터라 첫 블록을 건너뛰어 사용하지 않음 |
| [nadinem100/DMD_setup](https://github.com/nadinem100/DMD_setup) | 없음 | 호출 순서 교차 검증에만 사용. 라이선스가 없어 코드는 복사하지 않음. 1024×768 전용 |
| [DAsh0244/D4100_api_control](https://github.com/DAsh0244/D4100_api_control) | 없음 | 2019년 초안(전체 ON/OFF까지, 비트 패킹·이미지 경로 없음). 사용하지 않음 |

세 프로젝트가 서로 달랐던 점: DLL 호출 규약(`WinDLL` vs `CDLL`), 행 주소 설정 모드(3 vs 2). 실장비에서 **stdcall(`WinDLL`)** 이 맞음을 확인했고, 행 주소 모드는 3으로 동작함.

## 4. 구현 (`dmd_display.py`)

- 흐름: DLL 로드 → 장치/DMD 종류 확인 → (전원 투입 직후면) FPGA 자동 로드 → BMP 검사·이진화 → 블록 단위 `LoadData` → 글로벌 리셋.
- 해상도가 DMD와 다르면 오류. `--resize`를 명시했을 때만 최근접 보간으로 변환.
- 이진화: R/G/B 중 하나라도 128 이상이면 1(ON). 기본 극성은 흰색 = ON, 반대는 `--invert`.
- 옵션: `--info`, `--regs`(읽기 전용 레지스터 덤프), `--test on|off|half|tpg`, `--make-test-bmp WxH OUT`, `--hold`, `--dll`, `--fpga-bin`, `--device`.
- 종료 시 어떤 명령도 보내지 않음(Clear/Float 없음).
- 메시지는 콘솔 인코딩 문제를 피하려고 ASCII 영어. 마지막 줄은 `SUCCESS` 또는 `FAILED`.
- 검증: 가짜 DLL로 3종 DMD의 호출 순서, 전송 바이트가 원본 이미지와 비트 단위로 일치하는지(MSB/LSB 모두), 크기 불일치 오류, FPGA 자동 로드 조건을 확인한 뒤 실장비에서 시험.

## 5. 실장비에서 새로 알게 된 사실

### 5-1. FPGA는 전원을 끄면 사라지고, 로드 전에는 DMD type이 `16`으로 읽힘

| 상태 | FPGA rev | DLPC410 version | `GetDMDTYPE()` |
|---|---|---|---|
| 전원 투입 직후 | `0x1` | `0x11` | **16** (TI 문서에 없는 값) |
| `program_FPGA`로 `D4100_GUI_FPGA.bin` 로드 후 | `0xac02230d` | `0x7` | **0** |

- `program_FPGA`는 1 반환. 로드된 FPGA는 같은 전원 세션에서는 유지되고, 전원을 껐다 켜면 사라짐.
- 한때 "비트 4가 켜져 있으니 하위 비트만 보면 type 0일 것"이라는 가설을 세웠으나 **틀렸음**(원인은 FPGA 미초기화). 마스킹하지 않은 것이 옳았음.
- 조치: 유효한 DMD 값이 아니면 `D4100_GUI_FPGA.bin`을 찾아 1회 자동 로드하고, 로드 후에도 인식되지 않으면 DMD 보드/플랫 케이블 문제로 판단해 오류를 냄. 이미 초기화된 보드는 건드리지 않음.

### 5-2. `SetPWRFLOAT(0)`이 이 보드에서 미러를 park시킨 것으로 보임 (가장 큰 걸림돌)

- 증상: `tpg`/`on`/`half`/BMP가 모두 `SUCCESS`인데 DMD에 아무것도 안 보임. TI GUI는 같은 보드·같은 조명에서 정상.
- 원인 추정: 제가 로드 시퀀스에 넣은 `SetPWRFLOAT(0)`("미러가 park가 아니게 함")이 실제로는 float를 걸었음. TI 문서는 "1 = float 활성"이라 했지만 보드 동작은 **반대 극성**으로 보임. 정상 동작 중 `PWRFLOAT` 레지스터는 **1**로 읽힘.
- 조치: 이 호출을 제거하자 `--test on`이 보였음.
- 한계: `SetPWRFLOAT(0)` 직후의 값을 읽어 극성을 직접 확인하지는 않음(관측과 맞는 해석).
- 진단 도구: 읽기 전용 `--regs`를 추가해 TI GUI가 남긴 상태와 비교할 수 있게 함.

### 5-3. 정상 출력 후 레지스터 값

```
BlkMd 0, BlkAd 8, RowMd 0, RowAddr 0, RST2BLKZ 0, COMPDATA 0, NSFLIP 0,
WDT 1, PWRFLOAT 1, EXTRESETENBL 0, SWOverrideEnable 1, SWOverrideValue 0,
TPGEnable 0, PatternForce 0, PatternSelect 0, Load4 0, GPIO 0
```
`SWOverrideEnable = 1`이라 보드 SW1의 위치와 무관하게 소프트웨어 값이 적용되는 것으로 읽힘(DLPU039A §6.2.28). 사용자 보드의 SW1은 8개 모두 OFF였음.

### 5-4. 장치 정보 (참고)

DLL rev `0x00020001`, USB 고속(`0x1`), 드라이버 rev `0x10303e7`, USB 펌웨어 rev `0x200`, VID `0x0451` / PID `0xAF33`, `D4100_usb.dll` 393,728 bytes(2018-08-24), `D4100_GUI_FPGA.bin` 1,569,584 bytes.

## 6. 겪은 문제와 해결 (재현 시 참고)

| 문제 | 원인 | 해결 |
|---|---|---|
| `지정된 경로를 찾을 수 없습니다` | 예시로 든 Python 경로가 실제와 달랐음 | `py -0p`로 실제 경로 확인, `py -3.12-32` 사용 |
| `pip`에서 `Invalid requirement: '404: Not Found'` | 저장소가 비공개라 `curl`이 404 문구를 파일로 저장(파일 크기 14 bytes) | 브라우저로 ZIP 받기, 또는 저장소를 공개로 전환 |
| `GetDMDTYPE() = 16` | FPGA 미초기화 | `--fpga-bin`, 이후 자동 로드로 대체 |
| `SUCCESS`인데 화면에 안 보임 | `SetPWRFLOAT(0)` 호출 | 호출 제거 |
| `D4100_usb.dll`을 찾기 어려움 | D4100 Explorer 설치 폴더에 없고 `C:\Windows\SysWOW64`에 설치됨 | 스크립트가 해당 경로를 자동 탐색 |

## 7. 아직 확인하지 못한 것

- **유지 시간의 상한**: 종료 직후와 시험 시간 동안은 유지됐지만 몇 분 이상의 장시간 유지는 미측정.
- **실제 LabVIEW System Exec.vi에서의 호출**: 명령줄(32-bit `python.exe` 전체 경로, 다른 작업 디렉터리)까지만 확인.
- **전원을 끌 때 미러 park**: 스크립트에 넣지 않았음. TI는 전원 차단 전 SW3(park)을 누르길 강하게 권장(DLPU040D p.27).
- **`SetPWRFLOAT` 극성**: 위 5-2 한계 참고.
- **`--test tpg`**: 내부 테스트 패턴의 모양이 TI 문서에 없어 판정 기준이 없었고, 결과는 보고되지 않았음.
- **Windows 11**: 이번 PC는 Windows 10이었고, TI 문서도 10까지 명시.
- **DLPC410 데이터시트(DLPS024)**: 제공되지 않아 글로벌 리셋 값(`SetBlkMd(3)`, `SetBlkAd(8)`)과 행 모드의 레지스터 의미를 직접 확인하지 못했고, 동작 코드와 실측에 의존.

## 8. 이후 작업(별도 진행 예정)

노출 시간 제어, Pattern Sequence, Dark Time, Hardware Trigger, Syringe Pump 연동, LabVIEW 프로그램 개발, DNA 합성 자동화.
이 작업들은 5장에서 확인한 사실(전원 투입 후 FPGA 로드, `PWRFLOAT` 극성, 글로벌 리셋 시퀀스)을 바탕으로 해야 함.

## 9. 파일과 출처

```
DLP4100_Control/
├── dmd_display.py                  # 본체
├── test_mask.bmp                   # 1920x1080 테스트 이미지
├── requirements.txt                # Pillow
├── README.md                       # 설치·테스트·사용법
├── WORK_LOG.md                     # 이 문서
└── LICENSE-Sharvaj-Apache-2.0.txt  # 출처 표기용 사본
```

- TI 문서: [DLPU039A API Programmer's Guide](https://ti.com/lit/pdf/DLPU039), DLPU040D User's Guide.
- TI E2E 참고: [812675](https://e2e.ti.com/support/dlp/f/94/t/812675), [819526](https://e2e.ti.com/support/dlp/f/94/t/819526), [844754](https://e2e.ti.com/support/dlp-products-group/dlp/f/dlp-products-forum/844754/dlpd4x00kit-problem-using-d4100_usb-dll).
- 코드의 로드 시퀀스는 Sharvaj/DLP-Discovery-DMD-Control(Apache-2.0)을 Python으로 다시 작성한 것이며, nadinem100·DAsh0244에서는 코드를 가져오지 않았음.
