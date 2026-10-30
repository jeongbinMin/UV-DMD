# DLP4100_Control — Python으로 DLP Discovery 4100에 BMP 한 장 출력

```
python dmd_display.py "C:\DMD\mask.bmp"
```

범위는 "BMP 1장 → DMD 출력"뿐입니다. GUI, 노출 시간, 시퀀스, 트리거, LabVIEW 개발은 포함하지 않습니다.

> **현재 상태 (사용자 장비 실측)**: DLP9500/9500UV(1920×1080)에서 `test_mask.bmp`가 DMD에 정상 출력됨(글자 `F` 정상 방향, 1픽셀 대각선 매끈 → 비트 순서 기본값 MSB 우선이 맞음), 스크립트 종료 후에도 패턴 유지, 전원 투입 직후 FPGA 자동 로드 후 출력 성공.
> 아직 확인하지 못한 것: 유지 시간의 상한, LabVIEW System Exec 호출.

---

## 1. 선택한 방법과 이유

**Python(32-bit) + `ctypes`로 `D4100_usb.dll` 직접 호출 + Pillow로 BMP 변환**

| 이유 | 근거 |
|---|---|
| ActiveX는 구형 기술이고 DLL 직접 호출을 권장 | TI DLPU039A §4 NOTE |
| `FileToFrameBuffer`, `LoadToDMD`, `ConvertImage`, `LoadImageFileToBuffer`는 **ActiveX(OCX) 전용**. DLL(§6)에는 없음 | DLPU039A §5.3 vs §6 |
| DLL에는 `LoadData`(raw 1-bit 행 데이터), `LoadControl`, `ClearFifos`, `SetBlkMd/Ad`, `SetRowMd/Addr` 등 저수준 함수만 있음 | DLPU039A §6.2 |
| 따라서 BMP → 1-bit 바이너리 변환은 Python이 해야 함 | 위 두 항목의 결론 |

두 API를 섞지 않습니다. 이 스크립트는 DLL 함수만 호출합니다.

## 2. 오픈소스 조사 결과

| 프로젝트 | DLP4100 호환 | 언어 | 라이선스 | 판단 |
|---|---|---|---|---|
| [Sharvaj/DLP-Discovery-DMD-Control](https://github.com/Sharvaj/DLP-Discovery-DMD-Control) | `D4100_usb.dll` 호출, **1920×1080(DLP9500)만 하드코딩**, 행 데이터를 `.bin`으로 읽음 | C++/MATLAB | **Apache-2.0** | **로드 시퀀스의 기준**. BMP 로더(`LoadBMP`)는 미완성(블록 로드 루프가 `i=1`부터 시작해 15블록 중 **첫 블록을 건너뜀**)이라 사용하지 않음 |
| [nadinem100/DMD_setup](https://github.com/nadinem100/DMD_setup) | `D4100_usb.dll` 호출, **1024×768(DLP7000)만 하드코딩**, Python ctypes | Python | **LICENSE 파일 없음** | 시퀀스 교차 검증에만 사용. **코드는 복사하지 않음**(라이선스 없으면 재사용 권한이 없음) |
| [DAsh0244/D4100_api_control](https://github.com/DAsh0244/D4100_api_control) | DLL 래퍼 초안(2019, README 비어 있음). `LoadData`와 전체 ON/OFF(`set_all_mirrors`)까지만 있고 **비트 패킹·이미지 경로 없음**, 768×1024 하드코딩, 32-bit 서버 + `CDLL` 사용 | Python | LICENSE 없음 | 사용하지 않음. 함수 시그니처와 호출 규약 비교용으로만 참고 |

두 프로젝트(Sharvaj, nadinem100)가 독립적으로 **같은 글로벌 리셋 값**(`SetBlkMd(3)`, `SetBlkAd(8)` → `LoadControl`)을 쓰는 것을 확인했습니다. 이것이 이 시퀀스를 채택한 근거입니다.

## 3. 확인된 것 / 확인하지 못한 것

**문서·코드로 확인함**
- DMD는 3종이고 해상도·블록 구조가 다름: DLP9500(UV) 1920×1080 15×72, DLP7000(UV) 1024×768 16×48, DLP650LNIR 1280×800 16×50 (DLPU040D Table 3-1). 그래서 스크립트는 `GetDMDTYPE`으로 **자동 감지**하며 해상도를 하드코딩하지 않음.
- `LoadData`는 한 번에 500행 이하 (DLPU039A §6.2.2). 블록 단위로 나눠 전송.
- BMP→바이너리 변환은 DLL에 없음 → Pillow로 처리.
- TI GUI 설치 프로그램이 32-bit이고 VC++ 2010 **x86** 런타임을 요구 (DLPU040D p.32).

**확인하지 못함 (추측하지 않음, 장비 테스트로 확인 필요)**
1. **사용 중인 DMD 종류**: 보유 장비가 어느 모델인지 모름 → Step 3의 `--info` 출력으로 확정.
2. **Windows 11 지원**: TI 문서는 Windows 7/8.x/10만 명시(DLPU039A §4). 드라이버 폴더도 `Win10\x64`. 11은 문서상 확인 불가.
3. **64-bit DLL 존재 여부**: 두 프로젝트 모두 32-bit 전제. 64-bit DLL이 설치 프로그램에 있는지 확인하지 못함 → **32-bit Python 사용**.
4. **DLL 호출 규약**(stdcall vs cdecl): nadinem100은 `WinDLL`, DAsh0244는 `CDLL`. 스크립트가 둘 다 시도해 자동 선택.
5. ~~픽셀 비트 순서~~ → **확인됨**: 기본값 bit7(MSB 우선)이 맞음(1픽셀 대각선이 매끈). `--lsb-first`는 필요 없음.
6. **극성**: 기본은 "흰 픽셀 = 1 = 미러 ON". 반대로 보이면 `--invert`.
7. ~~FPGA 초기화~~ → **실측으로 확인됨(아래 "실측 결과" 참고)**: 이 장비는 전원을 켤 때마다 FPGA를 로드해야 하며, 스크립트가 자동으로 처리함.
8. **레지스터 값의 의미**: DLPC410 데이터시트(DLPS024)는 제공되지 않아 직접 확인하지 못함. 글로벌 리셋 값(`SetBlkMd(3)`, `SetBlkAd(8)`)과 "행 주소 설정" 모드는 두 프로젝트의 동작 코드에 의존. **단, 세 프로젝트가 완전히 일치하지는 않음**: Sharvaj·nadinem100은 행 주소 설정에 `SetRowMd(3)`, DAsh0244 초안은 `SetRowMd(0b10)`(=2)를 사용. 이 스크립트는 3을 사용(동작 코드 두 곳). 출력이 위/아래로 어긋나면 이 값이 첫 의심 대상.
9. ~~스크립트 종료 후 패턴 유지~~ → **확인됨**(종료 후에도 유지). 유지 시간의 상한은 미측정.

**실측 결과 (사용자 장비, Windows 10 19043, 32-bit Python 3.12)**
- `D4100_usb.dll`은 `C:\Windows\SysWOW64\`에 있고 **`WinDLL`(stdcall)** 로 로드됨, 장치 1대 인식, USB 고속(0x1), VID 0x0451 / PID 0xAF33.
- **전원 투입 직후**: `FPGA rev 0x1`, `DLPC410 version 0x11`, `GetDMDTYPE() = 16`(문서에 없는 값). `program_FPGA`로 `D4100_GUI_FPGA.bin`을 로드하면 `FPGA rev 0xac02230d`, `DLPC410 version 0x7`, `GetDMDTYPE() = 0`(DLP9500/9500UV, 1920×1080)으로 바뀜.
- 로드된 FPGA는 같은 전원 세션에서는 유지되고, **전원을 껐다 켜면 사라짐**(다시 16).
- 따라서 스크립트는 `GetDMDTYPE()`이 유효한 DMD 값이 아니면 `D4100_GUI_FPGA.bin`을 찾아 **자동으로 1회 로드**하고 다시 확인함. 이미 초기화된 보드는 건드리지 않음. 로드 후에도 인식이 안 되면 DMD 보드/플랫 케이블 문제로 판단해 오류를 냄.
- **`SetPWRFLOAT(0)`은 이 보드에서 미러를 park(float)시킴(해석)**: 로드 시퀀스에 이 호출을 넣었을 때는 `tpg`/`on`/`half`/BMP가 모두 `SUCCESS`인데 DMD에 아무것도 안 보였고(TI GUI는 같은 보드에서 정상), 이 호출만 뺀 뒤 `--test on`이 보임. 정상 동작 중 `PWRFLOAT` 레지스터는 **1**로 읽힘 → TI 문서(1 = float 활성)와 **반대 극성**으로 보임. 이 스크립트는 `SetPWRFLOAT`를 호출하지 않음. (호출 직후 값을 읽어 직접 확인하지는 않음)
- 정상 출력 후 `--regs` 값: `BlkMd 0, BlkAd 8, RowMd 0, RowAddr 0, WDT 1, PWRFLOAT 1, SWOverrideEnable 1, SWOverrideValue 0, TPGEnable 0, 나머지 0`. `SWOverrideEnable = 1`이라 보드의 SW1 위치와 무관하게 소프트웨어 값이 적용되는 것으로 읽힘(DLPU039A §6.2.28).
- `python dmd_display.py --regs`는 레지스터를 **읽기만** 하는 진단 명령(상태 변경 없음). 문제가 생기면 TI GUI로 정상 출력 후 `--regs`와 비교.

---

## 4. Step 2 — 설치 (Windows PC, 한 번만)

1. **D4100 Explorer 설치** (`D4100Explorer-2.0-windows-installer.exe`) — **USB 연결 전에** 설치.
   *왜*: 설치 프로그램이 USB 드라이버 INF와 `D4100_usb.dll`을 설치함 (DLPU040D p.32). 설치 중 "post installation script 오류"가 나오면 제거 → **Microsoft VC++ 2010 x86** 설치 → 재부팅 → 재설치.
2. 재부팅 후 **USB 2.0(mini-B) + 전원 연결**.
   *왜*: 일부 시스템은 재부팅 없이는 드라이버가 제대로 설치되지 않음.
3. **장치 관리자 → 범용 직렬 버스 컨트롤러 → `TI D4100 Explorer`** 확인.
   `DLI USB FX2 Firmware 2008`이 "기타 장치"에 있으면 드라이버 수동 지정: `C:\Program Files (x86)\D4100Explorer\Driver\Win10\x64\D4100-USB.inf` (DLPU040D p.32~36).
4. **TI GUI(DLP Discovery 4100 Explorer)를 한 번 실행**해 하단 상태 패널에 `USB 2.0`과 DMD 종류가 뜨는지, BMP가 GUI에서 출력되는지 확인 후 **GUI를 종료**.
   *왜*: 하드웨어/광학 문제와 내 코드 문제를 분리하기 위함. 그리고 GUI가 열려 있으면 USB 장치를 점유할 수 있음.
5. **32-bit Python 설치** (예: `C:\Python312-32`, python.org의 "Windows installer (32-bit)").
   *왜*: DLL이 32-bit 전제이고, 기존 `Python312`는 64-bit일 가능성이 높음. LabVIEW는 `python.exe` 경로만 지정하므로 두 Python이 공존해도 무방.
   ```
   C:\Python312-32\python.exe -c "import struct;print(struct.calcsize('P')*8)"
   ```
   → `32`가 나와야 함.
6. 의존성 설치:
   ```
   C:\Python312-32\python.exe -m pip install -r requirements.txt
   ```
7. **DLL 위치 확인**. 스크립트는 `--dll` → 환경변수 `D4100_DLL` → 스크립트 폴더 → `C:\Program Files (x86)\D4100Explorer\` → `C:\Windows\SysWOW64\` 순으로 찾음. 위치를 모르면:
   ```
   dir C:\ /s /b | findstr /i D4100_usb.dll
   ```
   찾은 DLL을 `dmd_display.py` 옆에 복사하면 가장 단순함.
8. (필요 시) `D4100_GUI_FPGA.bin`은 D4100 Explorer 설치 폴더에 있음 (DLPU039A §5.1.3).

## 5. Step 3 — USB 장치 인식

```
C:\Python312-32\python.exe dmd_display.py --info
```

**정상 결과** (값은 장비마다 다름):
```
[INFO] DLL: C:\...\D4100_usb.dll (WinDLL)
[INFO] Python 32-bit
[INFO] devices found: 1
[INFO] USB speed (1=high,0=full): 0x1
[INFO] USB descriptor: bytes=18 VID=0x???? PID=0x????
[INFO] DMD type 0: DLP9500/DLP9500UV 0.95 1080p 1920x1080, 15 blocks x 72 rows
[OK] device recognised
```

| 오류 | 원인 | 해결 |
|---|---|---|
| `WinError 193` | 64-bit Python으로 32-bit DLL 로드 | 32-bit Python 사용 |
| `Could not load D4100_usb.dll` | DLL을 못 찾음 | `--dll "경로"` 지정 (Step 2-7) |
| `GetNumDev() = 0` | 드라이버 미설치, 케이블/전원, GUI가 장치 점유 | Step 2-3 재확인, GUI 종료. [e2e 사례](https://e2e.ti.com/support/dlp/f/94/t/819526) |
| `DMD still not recognised after loading the FPGA` | FPGA를 자동 로드했는데도 DMD가 인식되지 않음 | DMD 보드, 플랫 케이블, DMD 전원 확인 |
| `GetDMDTYPE() = 16`/`15` + `loading FPGA` 메시지 | 전원 투입 직후 상태. 스크립트가 FPGA를 자동 로드함(정상) | 조치 불필요. `D4100_GUI_FPGA.bin`을 못 찾으면 `--fpga-bin "경로"` 지정 |
| `ValueError ... too many/not enough arguments` | 호출 규약 불일치 | 결과를 알려 주세요 (자동 폴백이 실패한 경우) |

**알려 주실 것**: 위 출력 전체(특히 `DMD type` 줄과 `DLL:` 줄).

## 6. Step 4 — 내장/단순 테스트 패턴

먼저 **이미지 데이터 경로와 무관한** 하드웨어 점검, 이어서 데이터 경로 점검입니다.
*왜 이 순서*: `tpg`는 PC가 이미지를 보내지 않고 FPGA 내부 패턴을 켭니다. `tpg`는 되는데 `on`이 안 되면 문제는 데이터 전송 쪽으로 좁혀집니다.

```
python dmd_display.py --test tpg
python dmd_display.py --test on
python dmd_display.py --test off
python dmd_display.py --test half
```
- `tpg`: 내부 테스트 패턴 1 (`SetTPGEnable/PatternForce/PatternSelect`). 이후의 일반 출력은 `SetTPGEnable(0)`으로 자동 해제됩니다.
- `on`/`off`: 전체 ON/OFF. `half`: 위쪽 절반 ON.
- 미러가 ON이어도 **조명(UV 광원)과 광학 경로가 있어야** 눈에 보입니다. 안 보이면 조명을 먼저 확인하세요.

**알려 주실 것**: 각 명령이 `SUCCESS`를 냈는지, 실제 DMD 출력이 기대대로인지.

## 7. Step 5 — BMP 출력

```
python dmd_display.py test_mask.bmp
python dmd_display.py "C:\DMD\mask.bmp"
```
- `test_mask.bmp`는 **1920×1080**(DLP9500/9500UV용)입니다. 다른 크기의 DMD라면 같은 모양의 테스트 이미지를 만드세요 (하드웨어 불필요):
  ```
  python dmd_display.py --make-test-bmp 1024x768 test_1024.bmp
  ```
- 해상도가 DMD와 다르면 **오류로 중단**합니다. `--resize`를 명시했을 때만 최근접 보간으로 늘립니다 (마스크 경계가 번지지 않게).
- 이진화: R/G/B 중 하나라도 128 이상이면 1(ON). TI `ConvertImage`는 240 기준이라는 설명이 있어(DLPU039A §5.3) 완전한 흑백 BMP가 아니면 결과가 다를 수 있습니다.

**테스트 이미지 판독법** (모서리 사각형 = 왼쪽 위, 글자 `F`, 1픽셀 대각선, 테두리):

| 보이는 모습 | 의미 | 조치 |
|---|---|---|
| 정상 | 성공 | — |
| 대각선이 톱니처럼 깨지고 `F`가 8픽셀 단위로 뒤집힘 | 비트 순서 반대 | `--lsb-first` |
| 흰/검정이 반전 | 극성 | `--invert` |
| `F`가 상하/좌우 뒤집힘 | 방향 | 알려 주세요 (DLL의 `SetNSFLIP`으로 처리 가능하나, 광학계의 거울 때문일 수도 있어 먼저 확인이 필요) |
| 아무것도 안 나옴 | `SUCCESS`인데 안 보임 | Step 4의 `tpg`/`on` 결과와 조명 확인 |

## 8. Step 6 — 종료 후 패턴 유지, LabVIEW 호출 가능성

### 6-A. 종료 후에도 패턴이 유지되는가 (장비에서 확인 필요)
```
python dmd_display.py test_mask.bmp
```
스크립트가 끝난 뒤 **60초 이상** DMD 출력이 유지되는지 보세요.

- 이 스크립트는 종료 시 **어떤 명령도 보내지 않습니다**(Clear/Float 호출 없음). 그러므로 유지될 가능성이 높지만, DLL 언로드 시 동작과 DLPC410 워치독(`SetWDT`, 기본 활성)의 영향은 문서로 확인하지 못했습니다.
- **유지되지 않으면**: `--hold`로 프로세스를 살려 두세요 (`Ctrl+C`로 종료, 종료 시에도 지우지 않음).
  ```
  python dmd_display.py test_mask.bmp --hold
  ```
  이 경우 원인 후보(USB 핸들 해제 시 FPGA 상태, 워치독)를 알려 주시면 DLPS024 기준으로 따로 해결합니다.
- 장시간 정지 패턴이나 전원 차단 전에는 미러 float(DMD 보호)를 권장합니다 (DLPU040D p.47). 이 스크립트에는 넣지 않았습니다.

### 6-B. LabVIEW System Exec.vi 호출
기존 구조(`python.exe` + 스크립트 + BMP 경로)와 같은 형태입니다:
```
C:\Python312-32\python.exe C:\DLP4100_Control\dmd_display.py C:\DMD\step_1.bmp
```
- 인자는 BMP 경로 1개. 경로에 공백이 있으면 따옴표로 감싸세요.
- **종료 코드**: 성공 0, 실패 1. **표준 출력**: 마지막 줄이 `SUCCESS` 또는 `FAILED` (기존 "DMD output" 표시기에 그대로 표시됨). 메시지는 콘솔 인코딩 문제를 피하려고 영어 ASCII만 사용.
- `--hold`를 쓰면 프로세스가 끝나지 않으므로 System Exec의 "wait until completion"을 **False**로 해야 합니다.
- 호출마다 DLL을 열고 닫습니다. `--fpga-bin`은 붙일 필요가 없습니다. 장비 전원을 켠 뒤 **첫 호출**만 FPGA를 자동 로드하느라 몇 초 더 걸릴 수 있습니다(소요 시간은 미측정).
- **이 단계는 실제 LabVIEW에서 아직 검증하지 않았습니다.** 먼저 명령 프롬프트에서 같은 명령줄이 성공하면 LabVIEW에서도 같은 명령줄이 동작해야 하지만, 작업 디렉터리와 DLL 탐색 경로는 LabVIEW 쪽에서 확인이 필요합니다.

---

## 9. 파일과 라이선스

```
DLP4100_Control/
├── dmd_display.py                  # 본체 (이 저장소 소유자의 라이선스에 따름)
├── test_mask.bmp                   # 1920x1080 테스트 이미지
├── requirements.txt                # Pillow
├── README.md
└── LICENSE-Sharvaj-Apache-2.0.txt  # 아래 출처 표기용 사본
```
- 로드/리셋 호출 순서는 [Sharvaj/DLP-Discovery-DMD-Control](https://github.com/Sharvaj/DLP-Discovery-DMD-Control)(Apache-2.0)의 `ControllerFunctions.cpp`를 Python으로 다시 작성하고 일반화한 것입니다. Apache-2.0 §4에 따라 라이선스 사본과 출처를 유지했습니다.
- [nadinem100/DMD_setup](https://github.com/nadinem100/DMD_setup)과 [DAsh0244/D4100_api_control](https://github.com/DAsh0244/D4100_api_control)에는 라이선스가 없어 **코드를 가져오지 않고** 동작 비교에만 참고했습니다. 코드를 직접 재사용하려면 저작자에게 라이선스 부여를 요청해야 합니다.
- 함수 의미는 TI [DLPU039A](https://ti.com/lit/pdf/DLPU039)(API Programmer's Guide)와 DLPU040D(User's Guide) 기준입니다.
