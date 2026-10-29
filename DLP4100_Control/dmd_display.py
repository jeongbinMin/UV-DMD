#!/usr/bin/env python3
"""Show one BMP on a TI DLP Discovery 4100 (DLPC410) DMD through D4100_usb.dll.

Usage examples (Windows):
    python dmd_display.py --info                    # Step 3: detect device only
    python dmd_display.py --test white              # Step 4: all mirrors ON
    python dmd_display.py --test mark               # Step 4: orientation test pattern
    python dmd_display.py "C:\\DMD\\mask.bmp"         # Step 5: show a BMP

Only the low-level DLL API of DLPU039A chapter 6 is used (GetNumDev, GetDMDTYPE,
SetBlkMd/SetRowMd/SetRowAddr/SetBlkAd, LoadData, LoadControl, ClearFifos ...).
FileToFrameBuffer / LoadToDMD / ConvertImage exist only in the ActiveX control, so the
BMP -> 1 bit/pixel conversion is done here with numpy + Pillow.

Provenance: the DMD load/commit call order follows `myLoadLive` in
https://github.com/Sharvaj/DLP-Discovery-DMD-Control (Apache License 2.0), and the
ctypes approach follows https://github.com/nadinem100/DMD_setup (no license file; no
code was copied from it). See README.md. Not verified on hardware by the author.

Exit code: 0 = success, 1 = failure. All messages are plain ASCII so that LabVIEW
System Exec.vi can read them regardless of the Windows code page.
"""
import argparse
import ctypes
import os
import struct
import sys
import time

import numpy as np
from PIL import Image

DLL_NAME = "D4100_usb.dll"

# DMDTYPE (GetDMDTYPE) -> name, width, height, rows per block  (DLPU039A 4.1 / 5.1.14)
DMD_TYPES = {
    0: ("DLP9500/DLP9500UV", 1920, 1080, 72),
    1: ("DLP7000/DLP7000UV", 1024, 768, 48),
    7: ("DLP650LNIR", 1280, 800, 50),
}
DMD_NOT_FOUND = 15


class DMDError(Exception):
    pass


# ----------------------------------------------------------------------------- DLL ---
def python_bits():
    return struct.calcsize("P") * 8


def dll_bits(path):
    """Read the PE header: 32 or 64. Lets us explain a bitness mismatch before loading."""
    with open(path, "rb") as f:
        head = f.read(4096)
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    machine = struct.unpack_from("<H", head, pe + 4)[0]
    return {0x14C: 32, 0x8664: 64}.get(machine)


def find_dll(explicit=None):
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("D4100_USB_DLL"):
        candidates.append(os.environ["D4100_USB_DLL"])
    here = os.path.dirname(os.path.abspath(__file__))
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    candidates += [
        os.path.join(here, DLL_NAME),
        os.path.join(windir, "SysWOW64", DLL_NAME),
        os.path.join(windir, "System32", DLL_NAME),
        os.path.join(r"C:\Program Files (x86)\D4100Explorer", DLL_NAME),
        os.path.join(r"C:\Program Files\D4100Explorer", DLL_NAME),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise DMDError(
        "%s not found. Searched: %s. Pass --dll PATH or copy it next to dmd_display.py."
        % (DLL_NAME, "; ".join(candidates))
    )


def load_dll(path):
    if os.name != "nt":
        raise DMDError("D4100_usb.dll is Windows-only; this is not Windows.")
    d = dll_bits(path)
    if d and d != python_bits():
        raise DMDError(
            "Bitness mismatch: %s is %d-bit but this Python is %d-bit. "
            "Use a %d-bit Python." % (path, d, python_bits(), d)
        )
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(os.path.dirname(os.path.abspath(path)))
    try:
        lib = ctypes.WinDLL(path)
    except OSError as e:
        raise DMDError(
            "Cannot load %s (%s). Error 126 usually means a missing dependency "
            "(install the 32-bit VC++ 2010 runtime and the D4100 Explorer package)." % (path, e)
        )
    declare(lib)
    return lib


def declare(lib):
    """Set argtypes/restype from DLPU039A chapter 6.

    restype matters: functions documented as `short` leave the upper half of EAX
    undefined, so the default c_int restype returns garbage (the nadinem100 repo
    notes a bogus GetFPGARev value for this reason).
    """
    s, u, i = ctypes.c_short, ctypes.c_uint, ctypes.c_int
    sig = {
        "GetNumDev": ([], s),
        "GetDLLRev": ([], u),
        "GetUsbSpeed": ([s], s),
        "GetFPGARev": ([s], u),
        "GetDMDTYPE": ([s], s),
        "LoadControl": ([s], s),
        "ClearFifos": ([s], s),
        "LoadData": ([ctypes.POINTER(ctypes.c_ubyte), u, s, s], i),
        "program_FPGA": ([ctypes.POINTER(ctypes.c_ubyte), ctypes.c_long, s], i),
    }
    for name in ("SetBlkMd", "SetBlkAd", "SetRowMd", "SetRowAddr", "SetNSFLIP",
                 "SetCOMPDATA", "SetWDT", "SetTPGEnable"):
        sig[name] = ([s, s], s)
    for name, (args, res) in sig.items():
        try:
            f = getattr(lib, name)
        except AttributeError:
            raise DMDError("%s does not export %s" % (DLL_NAME, name))
        f.argtypes, f.restype = args, res


# ----------------------------------------------------------------------- DMD driver ---
class D4100:
    def __init__(self, lib, device=0):
        self.lib = lib
        self.dev = device
        self.name = self.width = self.height = self.rows_per_block = None

    def _ok(self, name, *args):
        r = getattr(self.lib, name)(*args, self.dev)
        if r != 1:
            raise DMDError("%s%r returned %r (expected 1)" % (name, args, r))

    def connect(self):
        n = self.lib.GetNumDev()
        if n < 1:
            raise DMDError("No DLP Discovery 4100 found (GetNumDev=%d). Check USB cable, "
                           "board power (SW4) and the D4100 USB driver in Device Manager." % n)
        if self.dev >= n:
            raise DMDError("Device %d requested but only %d present (numbering starts at 0)."
                           % (self.dev, n))
        t = self.lib.GetDMDTYPE(self.dev)
        if t == DMD_NOT_FOUND:
            raise DMDError("DMD not attached or not recognized (GetDMDTYPE=15). "
                           "Check the DMD flex cable and that J2 jumpers are in place.")
        if t not in DMD_TYPES:
            raise DMDError("Unknown DMD type %d" % t)
        self.dmd_type = t
        self.name, self.width, self.height, self.rows_per_block = DMD_TYPES[t]

    def info(self):
        rev = self.lib.GetFPGARev(self.dev) & 0xFFFF
        dll = self.lib.GetDLLRev() & 0xFFFF
        return [
            "devices        : %d" % self.lib.GetNumDev(),
            "DMD type       : %d (%s, %dx%d)" % (self.dmd_type, self.name, self.width, self.height),
            "USB speed      : %s" % {0: "full (USB1.1)", 1: "high (USB2.0)"}.get(
                self.lib.GetUsbSpeed(self.dev), "error"),
            "DLL revision   : %d.%d" % (dll >> 8, dll & 0xFF),
            "APPS_FPGA rev  : %d.%d (raw 0x%04X)" % (rev >> 8, rev & 0xFF, rev),
        ]

    def program_fpga(self, bin_path):
        with open(bin_path, "rb") as f:
            data = f.read()
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        if self.lib.program_FPGA(buf, len(data), self.dev) != 1:
            raise DMDError("program_FPGA failed for %s" % bin_path)

    def prepare(self, wdt=None):
        """Bring the controller to a known state before loading data."""
        self._ok("SetTPGEnable", 0)  # factory FPGA cycles internal test patterns on power-up
        self._ok("SetNSFLIP", 0)
        self._ok("SetCOMPDATA", 0)
        if wdt is not None:
            self._ok("SetWDT", wdt)
        if self.lib.ClearFifos(self.dev) != 1:
            raise DMDError("ClearFifos failed")

    def _load(self, chunk):
        buf = (ctypes.c_ubyte * len(chunk)).from_buffer_copy(chunk)
        r = self.lib.LoadData(buf, len(chunk), self.dmd_type, self.dev)
        if r != 1:
            raise DMDError("LoadData(%d bytes) returned %r (expected 1)" % (len(chunk), r))

    def show(self, bits):
        """bits: uint8 array (height, width) of 0/1. Loads it and clocks it onto the mirrors."""
        if bits.shape != (self.height, self.width):
            raise DMDError("array %s does not match DMD %dx%d" % (bits.shape, self.width, self.height))
        data = np.packbits(bits.astype(np.uint8), axis=1).tobytes()  # MSB = left-most pixel
        bpr = self.width // 8
        blk = bpr * self.rows_per_block
        nblocks = self.height // self.rows_per_block

        self._ok("SetBlkMd", 0)    # no-op: load data only, do not reset yet
        self._ok("SetRowMd", 3)    # set-address mode
        self._ok("SetRowAddr", 0)  # start at top row
        self._load(data[:bpr])     # first row
        time.sleep(0.001)
        self._ok("SetRowMd", 1)    # increment mode: row pointer advances automatically
        self._load(data[bpr:blk])  # rest of block 1
        time.sleep(0.001)
        for b in range(1, nblocks):
            self._load(data[b * blk:(b + 1) * blk])

        # Commit: global mirror clocking pulse so DMD memory becomes visible on the mirrors.
        self._ok("SetRowMd", 0)
        self._ok("SetBlkMd", 3)
        self._ok("SetBlkAd", 8)
        if self.lib.LoadControl(self.dev) != 1:
            raise DMDError("LoadControl failed")
        time.sleep(0.001)
        self._ok("SetBlkMd", 0)
        for _ in range(2):
            if self.lib.LoadControl(self.dev) != 1:
                raise DMDError("LoadControl failed")


# ------------------------------------------------------------------------ images ---
def bmp_to_bits(path, width, height, threshold=128, invert=False, resize=False):
    """Same idea as TI's ConvertImage: bright pixel (any of R,G,B >= threshold) -> 1."""
    if not os.path.isfile(path):
        raise DMDError("File not found: %s" % path)
    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise DMDError("Cannot read image %s: %s" % (path, e))
    if img.size != (width, height):
        if not resize:
            raise DMDError("Image is %dx%d but DMD is %dx%d. Fix the image or pass --resize."
                           % (img.size[0], img.size[1], width, height))
        img = img.convert("RGB").resize((width, height), Image.NEAREST)
    bits = (np.asarray(img.convert("RGB")).max(axis=2) >= threshold).astype(np.uint8)
    return 1 - bits if invert else bits


def test_pattern(kind, width, height):
    if kind == "white":
        return np.ones((height, width), np.uint8)
    if kind == "black":
        return np.zeros((height, width), np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    if kind == "checker":
        return (((xx // 32) + (yy // 32)) % 2).astype(np.uint8)
    # "mark": asymmetric on purpose so mirroring, flipping, rotation and bit-order errors
    # are visible. Frame + solid square at top-left + big 'F' + 3px diagonal line (the line
    # becomes a saw-tooth if bits inside a byte are in the wrong order).
    m = np.zeros((height, width), np.uint8)
    m[:4, :] = m[-4:, :] = m[:, :4] = m[:, -4:] = 1
    m[10:60, 10:60] = 1
    cx, cy, s = width // 2 - 60, height // 2 - 90, 20
    m[cy:cy + 180, cx:cx + s] = 1
    m[cy:cy + s, cx:cx + 120] = 1
    m[cy + 80:cy + 80 + s, cx:cx + 90] = 1
    m[(abs(xx - yy) <= 1) & (xx > 70)] = 1
    return m


def save_bmp(bits, path):
    Image.fromarray((bits * 255).astype(np.uint8)).convert("RGB").save(path, format="BMP")


# --------------------------------------------------------------------------- main ---
def parse_size(text):
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("size must look like 1024x768")


def build_parser():
    p = argparse.ArgumentParser(description="Show a BMP on a DLP Discovery 4100 DMD.")
    p.add_argument("bmp", nargs="?", help="BMP file to display (must equal DMD resolution)")
    p.add_argument("--info", action="store_true", help="only detect the device and print info")
    p.add_argument("--test", choices=["white", "black", "checker", "mark"],
                   help="display a built-in pattern instead of a file")
    p.add_argument("--make-test-bmp", metavar="PATH", help="write the 'mark' pattern as BMP and exit")
    p.add_argument("--size", type=parse_size, default=(1920, 1080), help="size for --make-test-bmp")
    p.add_argument("--threshold", type=int, default=128, help="0-255, pixel >= threshold -> ON (128)")
    p.add_argument("--invert", action="store_true", help="swap ON/OFF after thresholding")
    p.add_argument("--resize", action="store_true", help="explicitly allow nearest-neighbour resize")
    p.add_argument("--dll", help="path to D4100_usb.dll")
    p.add_argument("--device", type=int, default=0, help="device number, 0-based (default 0)")
    p.add_argument("--fpga-bin", help="program APPS_FPGA from D4100_GUI_FPGA.bin first (optional)")
    p.add_argument("--wdt", type=int, choices=[0, 1], help="set the watchdog flag (diagnostics only)")
    p.add_argument("--hold", action="store_true", help="keep the process (USB handle) open until Ctrl+C")
    return p


def run(args):
    if args.make_test_bmp:
        w, h = args.size
        save_bmp(test_pattern("mark", w, h), args.make_test_bmp)
        print("OK: wrote %dx%d test BMP to %s" % (w, h, args.make_test_bmp))
        return
    if not (args.info or args.test or args.bmp):
        raise DMDError("Nothing to do: give a BMP path, --test KIND or --info")

    dll = find_dll(args.dll)
    print("INFO: python %d-bit, DLL %s (%s-bit)" % (python_bits(), dll, dll_bits(dll) or "?"))
    dmd = D4100(load_dll(dll), args.device)
    dmd.connect()
    for line in dmd.info():
        print("INFO: " + line)
    if args.info:
        print("OK: device detected")
        return

    # Check the file before touching the hardware so a bad path never changes the display.
    if args.test:
        bits = test_pattern(args.test, dmd.width, dmd.height)
        what = "test pattern '%s'" % args.test
    else:
        bits = bmp_to_bits(args.bmp, dmd.width, dmd.height, args.threshold, args.invert, args.resize)
        what = args.bmp
    if args.fpga_bin:
        dmd.program_fpga(args.fpga_bin)
        print("INFO: APPS_FPGA programmed from %s" % args.fpga_bin)
    dmd.prepare(args.wdt)
    dmd.show(bits)
    print("OK: displayed %s on %s (%dx%d), %d of %d mirrors ON"
          % (what, dmd.name, dmd.width, dmd.height, int(bits.sum()), bits.size))
    if args.hold:
        print("INFO: holding USB open; press Ctrl+C to exit")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except DMDError as e:
        print("ERROR: %s" % e)
        return 1
    except Exception as e:  # keep stdout parseable for LabVIEW
        print("ERROR: unexpected %s: %s" % (type(e).__name__, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
