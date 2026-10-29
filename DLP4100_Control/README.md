# DLP4100_Control — DLP Discovery 4100 에 BMP 한 장 출력하기

```
python dmd_display.py "C:\DMD\mask.bmp"
```

> **상태: 장비에서 아직 실행해 보지 않았습니다.** 작성 환경에는 Windows, DLL, DLP4100 이 없어서
> 가짜 DLL 로 호출 순서·전송 바이트·비트 패킹만 검증했습니다. 아래 "확인되지 않은 사항"을 꼭 읽고,
> 각 Step 의 결과를 알려 주세요.

---

## 1. 조사 결과 (Step 1)

### 왜 DLL(`D4100_usb.dll`)을 쓰는가
TI API 가이드(DLPU039A) 4장은 "ActiveX 는 오래된 기술이라 호환성 문제가 있으니 `D4100_usb.dll` 직접 사용을 권장하고, 보통 더 빠르다"고 합니다.

### ActiveX 전용 함수와 DLL 함수는 다릅니다 (혼용 금지)
| 함수 | ActiveX (DDC4100.ocx, 5장) | DLL (D4100_usb.dll, 6장) |
|---|---|---|
| `ConnectDevice`, `FileToFrameBuffer`, `LoadToDMD`, `ConvertImage`, `LoadImageFileToBuffer`, `MemToFrameBuffer`, `Clear`, `Reset` | 있음 | **없음** |
| `LoadData`, `LoadControl`, `ClearFifos`, `SetBlkMd/SetBlkAd/SetRowMd/SetRowAddr`, `GetNumDev`, `GetDMDTYPE`, `program_FPGA` | 일부 있음(시그니처 다름) | 있음 |

- 장치 번호: ActiveX 는 1부터, DLL 은 **0부터**.
- `LoadData` 시그니처가 다릅니다: ActiveX `LoadData(RowData, length)` / DLL `LoadData(RowData, length, DMDType, DeviceNumber)`.
- 따라서 DLL 에는 BMP 를 읽는 함수가 없습니다. **BMP → 1 bit/pixel 변환은 Python 이 직접** 하고(TI 의 `ConvertImage`와 같은 규칙: R,G,B 중 하나라도 임계값 이상이면 1), 그 결과를 `LoadData`로 보냅니다.

### 오픈소스 비교
| 항목 | [nadinem100/DMD_setup](https://github.com/nadinem100/DMD_setup) | [Sharvaj/DLP-Discovery-DMD-Control](https://github.com/Sharvaj/DLP-Discovery-DMD-Control) |
|---|---|---|
| 언어 | Python (ctypes) | C++ (Visual Studio 2019) + MATLAB |
| DLL | `D4100_usb.dll` (`C:\Windows\SysWOW64\`) | `D4100_usb.dll` + TI 헤더/lib |
| 실제 사용 호출 | `LoadData`, `LoadControl`, `ClearFifos`, `SetBlk*/SetRow*` | 동일 (+ `program_FPGA`, `SetWDT`, `SetTPGEnable`) |
| 대상 DMD | 1024×768 (DLP7000) 하드코딩 | 1920×1080 (DLP9500) 하드코딩 |
| BMP 직접 출력 | 아니오 (numpy 패턴을 직접 패킹) | 부분적 (`LoadBMP` 있으나 일부 블록만 전송하는 미완성 코드) |
| 비트 패킹 | MSB = 왼쪽 픽셀 | 바이트 배열 직접 작성 |
| 라이선스 | **LICENSE 파일 없음** | Apache-2.0 |
| 필요 비트수 | README: **32-bit Python** | 32-bit 빌드 추정(미확인) |

**선정:** Python+ctypes 구조는 nadinem100 방식, DMD 에 데이터를 넣고 반영하는 호출 순서는 Sharvaj 의 `myLoadLive`(주석에 TI e2e 포럼 출처로 보임)를 따릅니다.
이유: 두 저장소가 서로 다른 DMD 용이라 어느 것도 그대로는 쓸 수 없고, 호출 순서 자체는 같은 골격이라 합칠 수 있기 때문입니다. 해상도는 `GetDMDTYPE`으로 자동 감지하므로 DLP7000/DLP9500/DLP650LNIR 모두 같은 코드로 처리합니다.

그 외 DLP4100 을 지원하는 공개 Python 코드는 추가로 찾지 못했습니다(TI E2E 포럼에 "GitHub 에 Python 사례가 있다"는 언급만 확인).

---

## 2. 설치 (Step 2)

**왜 이 순서인가:** TI 매뉴얼(DLPU040D 3.2.1)이 "USB 를 연결하기 *전에* 소프트웨어를 먼저 설치"하라고 합니다. 설치 프로그램이 USB 드라이버(INF)와 `D4100_usb.dll`을 넣어 주기 때문입니다.

1. TI 의 **DLP Discovery 4100 Explorer GUI** 설치 ([다운로드](https://www.ti.com/tool/download/DLPLCRC410EVM-GUI), 수출 승인 절차 있음). 설치 중 오류가 나면 매뉴얼대로 **32-bit** VC++ 2010 재배포 패키지(x86)를 설치하고 재부팅 후 재설치 (Windows 가 64-bit 여도 GUI 가 32-bit 이므로).
2. 재부팅 후 보드 전원을 켜고 USB 연결. 장치 관리자에 TI D4100 Explorer 가 보이는지 확인. 자동 설치가 실패하면 `<설치폴더>\Driver\Win10\x64\D4100-USB.inf` 로 수동 설치.
3. **먼저 TI GUI 로 이미지 한 장이 뜨는지 확인**하세요. 그래야 이후 문제가 하드웨어인지 Python 인지 구분됩니다.
4. `D4100_usb.dll` 위치 확인 (보통 `C:\Windows\SysWOW64\`). 없으면 설치 폴더에서 찾아 `dmd_display.py` 옆에 복사해도 됩니다 (스크립트가 그 순서로 탐색).
5. Python 설치 — **DLL 과 같은 비트수**여야 합니다. 로드 시 비트수가 다르면 Windows 가 에러 193 을 내므로, 스크립트가 DLL 의 PE 헤더를 읽어 미리 알려 줍니다. 대부분 32-bit 일 것으로 추정되지만 `--info` 가 확정해 줍니다.
   ```
   python -m pip install -r requirements.txt
   ```
6. (선택) `D4100_GUI_FPGA.bin` — GUI 설치 폴더에 있음. 아래 "FPGA" 참고.

**Windows 11:** TI 문서는 Windows 7/8.x/10 만 명시합니다. 11 지원 여부는 **확인되지 않았습니다.** (오픈소스 쪽 사용 환경도 문서에 없음.)

---

## 3. 단계별 테스트

공통: 명령은 `cmd`/PowerShell 에서 이 폴더로 이동한 뒤 실행. 출력은 `INFO:`/`OK:`/`ERROR:` 로 시작하고, 성공 시 종료코드 0, 실패 시 1.

### Step 3 — 장치 인식 (`--info`)
**왜:** 패턴을 보내기 전에 DLL 로드·USB·DMD 인식이 되는지만 따로 확인해야, 이후 실패 원인을 좁힐 수 있습니다. 이 단계는 화면을 바꾸지 않습니다.
```
python dmd_display.py --info
```
정상 예:
```
INFO: python 32-bit, DLL C:\Windows\SysWOW64\D4100_usb.dll (32-bit)
INFO: devices        : 1
INFO: DMD type       : 1 (DLP7000/DLP7000UV, 1024x768)
INFO: USB speed      : high (USB2.0)
INFO: DLL revision   : ...
INFO: APPS_FPGA rev  : ...
OK: device detected
```
| 오류 | 원인 / 해결 |
|---|---|
| `D4100_usb.dll not found` | `--dll "경로"` 지정 또는 DLL 을 스크립트 옆에 복사 |
| `Bitness mismatch` | 메시지가 말하는 비트수의 Python 설치 |
| `Cannot load ... 126` | 의존 DLL 누락 → 32-bit VC++ 2010 재배포 + GUI 설치 확인 |
| `No DLP Discovery 4100 found` | USB, 전원(SW4), 장치 관리자 드라이버 확인. TI GUI 가 켜져 있으면 USB 를 점유할 수 있으니 **GUI 종료** |
| `GetDMDTYPE=15` | DMD 플렉스 케이블 / J2 점퍼 확인 |
| `USB speed: full` | USB 2.0 포트/케이블로 교체 (전송이 매우 느려짐) |

> `APPS_FPGA rev` 가 0.0 이거나 이상하면 FPGA 가 API 용 코드로 설정되지 않은 것일 수 있습니다 → "FPGA" 참고.

### Step 4 — 전체 ON/OFF·테스트 패턴 (`--test`)
**왜:** BMP 변환 문제와 하드웨어 제어 문제를 분리하기 위해, 파일 없이 코드가 만든 패턴으로 먼저 확인합니다.
```
python dmd_display.py --test white
python dmd_display.py --test black
python dmd_display.py --test checker
python dmd_display.py --test mark
```
정상: 명령마다 `OK: displayed ...` 가 나오고 DMD 출력이 바뀝니다. (전원 직후 TI 기본 코드가 돌리는 순환 테스트 패턴은 `SetTPGEnable(0)`으로 끕니다.)

`--test mark` 로 **방향/비트순서**를 확인하세요 (비대칭 패턴: 좌상단 채운 사각형 + 'F' + 대각선).
| 보이는 모습 | 의미 / 조치 |
|---|---|
| 좌상단에 사각형, 'F' 정상, 대각선 매끈 | 정상 |
| 'F' 가 좌우 반전 | 광학계에서 반전된 것. 이미지를 미리 뒤집어 사용 |
| 대각선이 8픽셀 톱니 모양 | 바이트 내부 비트 순서가 반대 (알려 주시면 코드 1줄 수정) |
| 흑백이 반대 | `--invert` 사용 (광학계 극성) |

### Step 5 — BMP 출력
**왜 해상도 검사:** 크기가 다른 이미지를 몰래 늘리면 마스크가 왜곡되어 합성 위치가 틀어집니다. 그래서 기본은 **오류**이고, `--resize`를 직접 줄 때만 변환합니다.
```
python dmd_display.py --make-test-bmp test_mask.bmp --size 1024x768   # (이미 포함됨. DMD 크기에 맞춰 재생성 가능)
python dmd_display.py "C:\DMD\mask.bmp"
```
정상: `OK: displayed C:\DMD\mask.bmp on DLP7000/DLP7000UV (1024x768), N of M mirrors ON`

| 오류 | 해결 |
|---|---|
| `Image is WxH but DMD is ...` | 이미지를 DMD 해상도로 저장, 또는 `--resize` |
| `File not found` | 경로 확인 (공백이 있으면 따옴표) |
| `LoadData(...) returned 0 (expected 1)` 등 `returned ... (expected 1)` | **실패한 호출 이름이 그대로 출력**됩니다. 그 줄을 알려 주세요 |

옵션: `--threshold N`(기본 128, 밝은 픽셀=ON), `--invert`, `--resize`, `--device N`.

### 패턴 유지 검증 (스크립트 종료 후)
**기대:** 스크립트는 USB 로 레지스터/이미지를 쓰고 끝낼 뿐 DMD 를 끄는 명령을 보내지 않으며, 보드는 PC 없이도 단독으로 동작하는 구조(전원만 넣으면 테스트 패턴이 순환, 매뉴얼 2.2.1)라서 **유지될 것으로 예상**합니다. 하지만 이것은 **추정이며 장비에서 확인되지 않았습니다.**
```
python dmd_display.py --test mark
(스크립트 종료 후 10초, 1분, 5분 뒤 DMD 출력이 그대로인지 관찰)
```
- 사라지면 → 원인 후보: 워치독(WDT) 설정(`SetWDT`, 매뉴얼은 "WDT 가 켜지면 다른 리셋을 비활성화한다"고만 설명하며 정확한 동작은 **확인되지 않음**). `--wdt 0` / `--wdt 1` 로 비교해 주세요.
- 별도 유지 방법: `--hold` (스크립트가 USB 를 연 채로 Ctrl+C 까지 대기).
- 참고: TI 는 **전원을 끄기 전에 SW3 로 미러를 Park(float)** 하라고 권장합니다(매뉴얼 2.2.1/2.2.4.3). 정적 패턴을 장시간 켜 둘 때도 같은 주의가 필요한지는 DMD 데이터시트(제공되지 않음)에서 확인하세요.

### Step 6 — LabVIEW System Exec.vi 호출
**왜 가능하다고 보는가:** 기존 구조가 이미 `python.exe` + 스크립트 경로를 `System Exec.vi`에 넘기고 stdout 을 문자열로 받는 방식입니다. 이 스크립트도 똑같이 "실행 → stdout 출력 → 종료코드" 구조이고, 메시지는 ASCII 라서 코드페이지 문제가 없습니다.

명령줄 배열(기존 `test_code.py` 자리에 교체, BMP 경로를 세 번째 요소로 추가):
```
"C:\...\Python\Python3xx-32\python.exe"
"C:\DLP4100_Control\dmd_display.py"
"C:\DMD\step_001.bmp"
```
- `wait until completion` = TRUE, 반환된 `return code` 가 0 인지와 `standard output` 의 `OK:` 로 성공 판정.
- **DLL 이 32-bit 이면 python.exe 도 32-bit 경로**를 써야 합니다 (기존 `Python312` 경로가 64-bit 면 그대로 쓰면 안 됨).
- 먼저 `cmd` 에서 같은 명령이 성공하는지 확인한 뒤 LabVIEW 에서 호출하세요. LabVIEW 가 실행하는 계정/작업 폴더가 달라 DLL 탐색이 실패하는 경우를 구분하기 위해서입니다.
- 호출마다 USB 연결·초기화를 다시 하므로 한 장당 소요시간이 생깁니다. TI 는 USB 2.0 에서 초당 약 7–10 프레임이라고 하며, 파이썬 기동 포함 실측값은 **확인되지 않았습니다.** (스텝 속도가 문제가 되면 상주 프로세스 방식을 별도 작업으로 검토.)
- `--test`/`--info` 도 같은 방식으로 호출 가능합니다.

---

## 확인되지 않은 사항 (추측하지 않음)

1. **실제 장비 동작 전체** — 이 코드는 장비에서 실행된 적이 없습니다.
2. TI `D4100_usb.dll` 이 32-bit 전용인지 64-bit 판도 있는지 (API 가이드의 "32/64-bit 지원"은 Windows 개발 환경을 말함). `--info` 가 설치된 DLL 의 비트수를 알려 줍니다.
3. 공장 출하 FPGA 코드가 `D4100_GUI_FPGA.bin` 과 같은지. 다르면 `--fpga-bin "…\D4100_GUI_FPGA.bin"` 으로 한 번 올려야 할 수 있습니다 (TI ActiveX `ConnectDevice`는 미초기화 시 이 파일을 올린다고 문서화). FPGA 설정은 휘발성이라 보드 재부팅 시 다시 필요할 수 있다는 점도 미확인.
4. `SetBlkMd(3)` + `SetBlkAd(8)` = 전체(Global) 리셋이라는 값 의미 — 두 저장소가 공통으로 쓰는 값이지만 DLPC410 데이터시트(DLPS024)는 제공되지 않아 직접 확인하지 못했습니다.
5. 픽셀 극성(1=ON)과 방향 — 광학계에 따라 다르므로 `--test mark` 로 확인 필요.
6. DLP650LNIR(1280×800, 블록당 50행) 경로 — TI 문서 기준으로 구현했지만 두 저장소 모두 이 DMD 로 검증되지 않음.
7. Windows 11 동작.
8. 패턴 유지(위 섹션), WDT 의 정확한 동작.

## 출처 및 라이선스

- 호출 순서(`LoadData` → `LoadControl` 커밋): [Sharvaj/DLP-Discovery-DMD-Control](https://github.com/Sharvaj/DLP-Discovery-DMD-Control) `ControllerFunctions.cpp` 의 `myLoadLive` — **Apache License 2.0**. 코드를 복사하지 않고 Python 으로 새로 작성했으나 호출 순서를 따랐으므로 출처를 밝힙니다.
- ctypes 로딩 방식 참고: [nadinem100/DMD_setup](https://github.com/nadinem100/DMD_setup) — 저장소에 **LICENSE 파일이 없습니다.** 코드는 복사하지 않았습니다. 이 프로젝트를 외부에 배포한다면 저자에게 확인하세요.
- API 사양: TI DLPU039A, DLPU040D. `D4100_usb.dll` 과 FPGA bin 은 TI 소유이며 이 폴더에 포함하지 않았습니다.
