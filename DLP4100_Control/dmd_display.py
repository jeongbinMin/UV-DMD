#!/usr/bin/env python
"""Show one BMP on a TI DLP Discovery 4100 (DLPC410) DMD through D4100_usb.dll.

    python dmd_display.py "C:\\DMD\\mask.bmp"
    python dmd_display.py --info
    python dmd_display.py --test on|off|half|tpg
    python dmd_display.py --make-test-bmp 1024x768 test_mask.bmp

Uses only the low-level D4100_usb.dll API (TI DLPU039A, chapter 6). The ActiveX
calls FileToFrameBuffer / LoadToDMD / ConvertImage do NOT exist in the DLL, so
the BMP -> 1-bit conversion is done here with Pillow.

Attribution
  * The DMD load/reset call order follows myLoadPattern() / myLoadLive() in
    ControllerFunctions.cpp of https://github.com/Sharvaj/DLP-Discovery-DMD-Control
    (Apache License 2.0, copy in LICENSE-Sharvaj-Apache-2.0.txt), re-written in
    Python and generalised to the DMD types listed in TI DLPU039A / DLPU040D.
  * It was cross-checked against https://github.com/nadinem100/DMD_setup, which
    has no license file; no code was copied from it.
  * API meaning of every call: TI DLPU039A (DLP Discovery 4100 API Programmer's Guide).
"""
import argparse
import ctypes
import os
import struct
import sys
import time

# GetDMDTYPE() -> (name, columns, rows, blocks, rows per block)
# TI DLPU039A 6.1.10 and DLPU040D Table 3-1.
DMD_TYPES = {
    0: ("DLP9500/DLP9500UV 0.95 1080p", 1920, 1080, 15, 72),
    1: ("DLP7000/DLP7000UV 0.7 XGA", 1024, 768, 16, 48),
    7: ("DLP650LNIR 0.65 WXGA", 1280, 800, 16, 50),
}
NO_DMD = 15

# Read-only getters, DLPU039A chapter 6: used by --regs to compare the state left by
# the TI GUI with the state left by this script.
REG_GETTERS = ("GetBlkMd", "GetBlkAd", "GetRowMd", "GetRowAddr", "GetRST2BLKZ", "GetCOMPDATA",
               "GetNSFLIP", "GetWDT", "GetPWRFLOAT", "GetEXTRESETENBL", "GetSWOverrideEnable",
               "GetSWOverrideValue", "GetTPGEnable", "GetPatternForce", "GetPatternSelect",
               "GetLoad4", "GetGPIO")

THRESHOLD = 128  # R, G or B >= THRESHOLD -> pixel is 1 (mirror ON)

DLL_CANDIDATES = [
    os.environ.get("D4100_DLL", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "D4100_usb.dll"),
    r"C:\Program Files (x86)\D4100Explorer\D4100_usb.dll",
    r"C:\Windows\SysWOW64\D4100_usb.dll",
    "D4100_usb.dll",
]


FPGA_BIN_CANDIDATES = [
    os.environ.get("D4100_FPGA_BIN", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "D4100_GUI_FPGA.bin"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 "D4100Explorer", "D4100_GUI_FPGA.bin"),
]


class DmdError(Exception):
    pass


class NotInitialised(DmdError):
    """GetDMDTYPE() returned a value that is not a DMD type: the APPS_FPGA still
    holds its power-on design. Measured on the target board: after every power
    cycle FPGA rev reads 0x1 and GetDMDTYPE() reads 16 until D4100_GUI_FPGA.bin
    is programmed with program_FPGA()."""


def find_fpga_bin():
    for p in FPGA_BIN_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return None


def _signatures():
    """name -> (restype, argtypes) per DLPU039A chapter 6. Setting these avoids
    ctypes truncating/mis-signing return values (unsigned int, short)."""
    s, u, i, l = ctypes.c_short, ctypes.c_uint, ctypes.c_int, ctypes.c_long
    pu8 = ctypes.POINTER(ctypes.c_ubyte)
    sig = {
        "GetNumDev": (s, []),
        "GetDLLRev": (u, []),
        "GetDescriptor": (i, [ctypes.POINTER(ctypes.c_int), s]),
        "program_FPGA": (i, [pu8, l, s]),
        "LoadData": (i, [pu8, u, s, s]),
    }
    for n in ("GetDriverRev", "GetFirmwareRev", "GetFPGARev"):
        sig[n] = (u, [s])
    for n in ("GetUsbSpeed", "GetDDCVERSION", "GetDMDTYPE", "LoadControl", "ClearFifos") + REG_GETTERS:
        sig[n] = (s, [s])
    for n in ("SetBlkMd", "SetBlkAd", "SetRowMd", "SetRowAddr", "SetTPGEnable",
              "SetPatternForce", "SetPatternSelect", "SetPWRFLOAT"):
        sig[n] = (s, [s, s])
    return sig


def open_dll(explicit_path=None):
    """Load D4100_usb.dll. Which calling convention the DLL uses is not stated in
    DLPU039A and two open-source projects disagree (WinDLL vs CDLL), so try
    stdcall first and fall back to cdecl; ctypes on 32-bit Windows raises
    ValueError when the convention is wrong."""
    if not sys.platform.startswith("win"):
        raise DmdError("D4100_usb.dll is a Windows DLL; run this on the Windows PC.")
    paths = [explicit_path] if explicit_path else [p for p in DLL_CANDIDATES if p]
    last = None
    for path in paths:
        if os.path.isabs(path) and not os.path.exists(path):
            continue
        if os.path.isabs(path):
            os.add_dll_directory(os.path.dirname(path))
        for cls in (ctypes.WinDLL, ctypes.CDLL):
            try:
                dll = cls(path)
            except OSError as e:
                last = e
                if getattr(e, "winerror", None) == 193:
                    raise DmdError("%s is not loadable by this %d-bit Python (WinError 193). "
                                   "Use the same bitness as the DLL (32-bit Python)." % (path, _bits()))
                break
            _apply_signatures(dll)
            try:
                dll.GetDriverRev(0)  # harmless 1-argument call to test the convention
            except ValueError:
                continue
            print("[INFO] DLL: %s (%s)" % (path, cls.__name__))
            return dll
    raise DmdError("Could not load D4100_usb.dll (%s). Pass --dll PATH or set D4100_DLL." % (last or "not found"))


def _apply_signatures(dll):
    for name, (res, args) in _signatures().items():
        try:
            fn = getattr(dll, name)
        except AttributeError:
            continue  # reported only if the function is actually needed
        fn.restype, fn.argtypes = res, args


def _bits():
    return struct.calcsize("P") * 8


class Device:
    """One DLP Discovery 4100 board. DLL device numbers start at 0."""

    def __init__(self, dll, number=0):
        self.dll, self.number = dll, number

    def call(self, name, *args, check=True):
        try:
            fn = getattr(self.dll, name)
        except AttributeError:
            raise DmdError("D4100_usb.dll does not export %s" % name)
        r = fn(*args, self.number)
        if check and r != 1:  # every Set*/Load*/Clear* returns 1 on success (DLPU039A)
            raise DmdError("%s%r returned %r (expected 1)" % (name, args, r))
        return r

    def load(self, data, dmd_type):
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        r = self.dll.LoadData(buf, len(data), dmd_type, self.number)
        if r != 1:
            raise DmdError("LoadData(%d bytes) returned %r (expected 1)" % (len(data), r))

    def detect(self):
        n = self.dll.GetNumDev()
        if n < 1:
            raise DmdError("GetNumDev() = %d: no DLP Discovery 4100 found. Check USB cable, power "
                           "and the 'TI D4100 Explorer' driver in Device Manager." % n)
        if self.number >= n:
            raise DmdError("--device %d requested but only %d device(s) present" % (self.number, n))
        t = self.call("GetDMDTYPE", check=False)
        if t not in DMD_TYPES:
            raise NotInitialised("GetDMDTYPE() = %d (valid: %s; 15 = no DMD). After a power-on the "
                                 "FPGA must be loaded: --fpga-bin D4100_GUI_FPGA.bin"
                                 % (t, ", ".join(str(k) for k in sorted(DMD_TYPES))))
        return t, DMD_TYPES[t]

    def ready(self, fpga_bin=None):
        """detect(); if the board is in its power-on state, program the FPGA once
        and detect again. An already-initialised board is left untouched."""
        try:
            return self.detect()
        except NotInitialised as e:
            path = fpga_bin or find_fpga_bin()
            if not path:
                raise DmdError("%s (and no D4100_GUI_FPGA.bin found; pass --fpga-bin)" % e)
            print("[INFO] board is in power-on state, loading FPGA from %s" % path)
            self.program_fpga(path)
            try:
                return self.detect()
            except NotInitialised as e2:
                raise DmdError("DMD still not recognised after loading the FPGA: %s. Check the DMD "
                               "board, its flat cable and the DMD power." % str(e2).split(" (")[0])

    def program_fpga(self, bin_path):
        with open(bin_path, "rb") as f:
            data = f.read()
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        r = self.dll.program_FPGA(buf, len(data), self.number)
        # return value is not specified in DLPU039A: shown for information only
        print("[INFO] program_FPGA(%d bytes) returned %r; FPGA rev now 0x%08X"
              % (len(data), r, self.call("GetFPGARev", check=False) & 0xFFFFFFFF))

    def info(self):
        print("[INFO] Python %d-bit" % _bits())
        print("[INFO] devices found: %d" % self.dll.GetNumDev())
        print("[INFO] DLL rev: 0x%08X" % self.dll.GetDLLRev())
        for label, name in (("USB speed (1=high,0=full)", "GetUsbSpeed"), ("driver rev", "GetDriverRev"),
                            ("USB firmware rev", "GetFirmwareRev"), ("FPGA rev", "GetFPGARev"),
                            ("DLPC410 version", "GetDDCVERSION")):
            try:
                print("[INFO] %s: %s" % (label, hex(self.call(name, check=False) & 0xFFFFFFFF)))
            except DmdError as e:
                print("[WARN] %s" % e)
        try:
            d = (ctypes.c_int * 14)()
            n = self.dll.GetDescriptor(d, self.number)
            print("[INFO] USB descriptor: bytes=%d VID=0x%04X PID=0x%04X" % (n, d[7], d[8]))
        except Exception as e:
            print("[WARN] GetDescriptor failed: %s" % e)

    def regs(self):
        """Print the APPS_FPGA control registers. Read-only: changes nothing."""
        for name in REG_GETTERS:
            try:
                print("[REG] %-20s = %d" % (name[3:], self.call(name, check=False)))
            except DmdError as e:
                print("[WARN] %s" % e)

    def show(self, payload, dmd_type, geom):
        """Load a full 1-bit frame (MSB/LSB packing already done) and reset the mirrors."""
        _, cols, rows, blocks, rpb = geom
        bpr = cols // 8
        if len(payload) != bpr * rows:
            raise DmdError("payload is %d bytes, expected %d" % (len(payload), bpr * rows))
        c = self.call
        c("SetTPGEnable", 0)   # internal scrolling test patterns off, or they hide our data
        c("ClearFifos")        # DLPU039A 6.2.3: known state before sending image data
        c("SetBlkMd", 0)       # block mode: no-op while loading
        c("SetRowMd", 3)       # row mode: set address
        c("SetRowAddr", 0)     # start at top row
        self.load(payload[:bpr], dmd_type)           # first row alone, as in the reference code
        time.sleep(0.001)
        c("SetRowMd", 1)       # row mode: auto-increment
        blk = bpr * rpb
        self.load(payload[bpr:blk], dmd_type)        # rest of block 1
        for b in range(1, blocks):                   # remaining blocks, one call each (<=500 rows/call)
            self.load(payload[b * blk:(b + 1) * blk], dmd_type)
        c("SetRowMd", 0)
        c("SetBlkMd", 3)       # global reset ...
        c("SetBlkAd", 8)       # ... same values both reference projects use
        c("LoadControl")       # commit: mirrors take the loaded memory
        time.sleep(0.001)
        c("SetBlkMd", 0)       # back to no-op so later LoadControl calls do not reset again
        c("LoadControl")
        c("LoadControl")


def bmp_to_payload(path, geom, resize=False, invert=False, lsb_first=False):
    from PIL import Image, ImageChops, ImageOps
    name, cols, rows, _, _ = geom
    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise DmdError("cannot read image %s: %s" % (path, e))
    if img.format != "BMP":
        raise DmdError("%s is %s, not a BMP" % (path, img.format))
    print("[INFO] image: %dx%d mode=%s ; DMD: %s %dx%d" % (img.width, img.height, img.mode, name, cols, rows))
    if img.size != (cols, rows):
        if not resize:
            raise DmdError("image is %dx%d but the DMD is %dx%d. Fix the BMP, or pass --resize to "
                           "stretch it (nearest-neighbour)." % (img.width, img.height, cols, rows))
        img = img.resize((cols, rows), Image.NEAREST)
    r, g, b = img.convert("RGB").split()
    lum = ImageChops.lighter(ImageChops.lighter(r, g), b)       # any channel >= threshold -> ON
    lum = lum.point(lambda v: 255 if v >= THRESHOLD else 0)
    if invert:
        lum = ImageOps.invert(lum)
    bw = lum.convert("1", dither=Image.Dither.NONE)
    on = bw.histogram()[255]
    print("[INFO] ON pixels: %d / %d (%.1f%%)" % (on, cols * rows, 100.0 * on / (cols * rows)))
    return bw.tobytes("raw", "1;R" if lsb_first else "1")


def test_payload(kind, geom):
    _, cols, rows, _, _ = geom
    n = cols // 8 * rows
    if kind == "on":
        return b"\xff" * n
    if kind == "off":
        return b"\x00" * n
    return b"\xff" * (n // 2) + b"\x00" * (n - n // 2)  # half: top half ON


def make_test_bmp(size, out):
    """Asymmetric test image: corner square, 'F', 1-px diagonal, frame. A wrong bit
    order mirrors every 8-pixel group, which makes the diagonal visibly jagged."""
    from PIL import Image, ImageDraw
    w, h = (int(v) for v in size.lower().split("x"))
    img = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=1, width=2)
    d.rectangle([8, 8, 8 + w // 20, 8 + w // 20], fill=1)             # top-left marker
    x0, y0, t = w // 8, h // 4, max(8, w // 64)                          # 'F'
    d.rectangle([x0, y0, x0 + t, y0 + h // 2], fill=1)
    d.rectangle([x0, y0, x0 + w // 5, y0 + t], fill=1)
    d.rectangle([x0, y0 + h // 4, x0 + w // 7, y0 + h // 4 + t], fill=1)
    d.line([0, 0, w - 1, h - 1], fill=1, width=1)
    img.convert("RGB").save(out, "BMP")
    print("[OK] wrote %s (%dx%d)" % (out, w, h))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Show a BMP on a DLP Discovery 4100 DMD.")
    ap.add_argument("bmp", nargs="?", help="BMP file to display (must equal the DMD resolution)")
    ap.add_argument("--info", action="store_true", help="connect, print device info, exit")
    ap.add_argument("--regs", action="store_true", help="print control registers (read-only), exit")
    ap.add_argument("--test", choices=["on", "off", "half", "tpg"], help="built-in test pattern")
    ap.add_argument("--make-test-bmp", nargs=2, metavar=("WxH", "OUT.bmp"), help="write a test image, no hardware needed")
    ap.add_argument("--resize", action="store_true", help="stretch a wrong-size BMP to the DMD size")
    ap.add_argument("--invert", action="store_true", help="swap ON/OFF (default: white pixel = mirror ON)")
    ap.add_argument("--lsb-first", action="store_true", help="pack leftmost pixel into bit 0 instead of bit 7")
    ap.add_argument("--hold", action="store_true", help="keep this process alive after displaying (Ctrl+C to quit)")
    ap.add_argument("--dll", help="path to D4100_usb.dll")
    ap.add_argument("--fpga-bin", help="D4100_GUI_FPGA.bin; programmed first, always. Without it the file "
                    "is located automatically and loaded only if the board is in its power-on state")
    ap.add_argument("--device", type=int, default=0, help="DLL device number, starts at 0")
    a = ap.parse_args(argv)

    try:
        if a.make_test_bmp:
            make_test_bmp(*a.make_test_bmp)
            return 0
        if not (a.bmp or a.info or a.test or a.regs):
            ap.error("give a BMP path, or --info, --regs or --test")
        dev = Device(open_dll(a.dll), a.device)
        if a.fpga_bin:
            dev.program_fpga(a.fpga_bin)  # forced, even if already initialised
        if a.info:
            dev.info()
        dmd_type, geom = dev.ready(a.fpga_bin)  # loads the FPGA itself after a power-on
        print("[INFO] DMD type %d: %s %dx%d, %d blocks x %d rows" % ((dmd_type,) + geom))
        if a.regs:
            dev.regs()
            print("SUCCESS")
            return 0
        if a.info:
            print("[OK] device recognised")
            return 0
        if a.test == "tpg":
            dev.call("SetTPGEnable", 1)
            dev.call("SetPatternForce", 1)
            dev.call("SetPatternSelect", 1)
            print("[OK] internal test pattern 1 enabled (no image data sent)")
        else:
            if a.test:
                payload = test_payload(a.test, geom)
            else:
                payload = bmp_to_payload(a.bmp, geom, a.resize, a.invert, a.lsb_first)
            dev.show(payload, dmd_type, geom)
            print("[OK] frame sent to DMD: %s" % (a.test or a.bmp))
        print("SUCCESS")
        if a.hold:
            print("[INFO] holding; Ctrl+C to exit (DMD is not cleared on exit)")
            while True:
                time.sleep(1)
        return 0
    except KeyboardInterrupt:
        return 0
    except (DmdError, OSError, ValueError) as e:
        print("[ERROR] %s" % e)
        print("FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
