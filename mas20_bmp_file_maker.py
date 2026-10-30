#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2D CSV(엑셀에서 저장, 셀 하나 = DMD 픽셀 하나)의 각 셀에 문자열이 들어있는 grid를 읽어서,
- 현재 남아있는 문자열들 중 최대 길이(max_len)를 찾고
- max_len을 가진 문자열들의 '첫 글자' 최빈 문자(best_char)를 선택
- best_char로 시작하는 모든 셀의 첫 글자 1개를 삭제
- 삭제가 일어난 (row, col) 위치를 흰색(미러 ON)으로 한 BMP 마스크 저장
- 위 과정을 모든 문자열이 빈 문자열이 될 때까지 반복

출력 BMP는 항상 DMD 해상도(1920x1080) 고정:
- grid(x scale)가 DMD보다 작으면 --align 위치(기본 center)에 놓고 나머지는 검정(OFF)
- grid(x scale)가 DMD보다 크면 오류로 중단 (잘라내면 엉뚱한 패턴이 나가므로)

원본(grid 크기 그대로 저장)과 알고리즘/선택 규칙/파일명은 동일하고,
200만 셀 규모에서도 빠르도록 numpy로 벡터화했다.

자동 모드:
- 인자 없이 실행하면 스크립트 폴더 내 .csv 중 가장 큰 파일을 자동 선택
- 출력 폴더는 스크립트 폴더/<csv 파일명> 으로 자동 생성
"""

from __future__ import annotations

import argparse
import glob
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image  # pip install pillow numpy

DMD_W = 1920
DMD_H = 1080


def detect_delim(line: str) -> str:
    if "," in line:
        return ","
    if "\t" in line:
        return "\t"
    return "whitespace"


def split_line(line: str, delim: str) -> List[str]:
    line = line.rstrip("\n\r")
    if delim == "whitespace":
        return re.split(r"\s+", line.strip()) if line.strip() else [""]
    parts = line.split(delim)
    return [p.strip() for p in parts]


def read_text_lines(path: str) -> List[str]:
    # 엑셀 'CSV UTF-8'은 BOM이 붙는다. utf-8만 쓰면 BOM이 첫 셀 첫 글자로 들어가므로 utf-8-sig 사용.
    # 한국어 윈도우 엑셀의 일반 'CSV'는 cp949라서 실패하면 cp949로 재시도.
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp949") as f:
            return f.readlines()


def read_grid(path: str, delim: Optional[str] = None) -> List[List[str]]:
    lines = read_text_lines(path)
    if not lines:
        return []

    d = delim if delim is not None else detect_delim(lines[0])
    grid: List[List[str]] = [split_line(ln, d) for ln in lines]

    # row 길이 통일(짧은 row는 빈 문자열로 패딩)
    max_cols = max(len(r) for r in grid) if grid else 0
    for r in grid:
        if len(r) < max_cols:
            r.extend([""] * (max_cols - len(r)))
    return grid


def check_fits_dmd(nrows: int, ncols: int, scale: int) -> None:
    w, h = ncols * scale, nrows * scale
    if w > DMD_W or h > DMD_H:
        raise SystemExit(
            f"❌ grid {ncols}x{nrows} (scale {scale} → {w}x{h}) 가 DMD {DMD_W}x{DMD_H} 보다 큽니다. "
            f"CSV를 줄이거나 --scale 을 낮추세요."
        )


def placement_offset(nrows: int, ncols: int, scale: int, align: str) -> Tuple[int, int]:
    """DMD 캔버스에서 grid 좌상단이 놓일 (x0, y0)."""
    if align == "topleft":
        return 0, 0
    return (DMD_W - ncols * scale) // 2, (DMD_H - nrows * scale) // 2


def save_bmp_mask(
    changed_flat: np.ndarray,
    nrows: int,
    ncols: int,
    out_path: str,
    scale: int = 1,
    align: str = "center",
) -> None:
    """
    changed_flat(행우선 인덱스) 위치만 255, 나머지 0인 1920x1080 그레이스케일(L) BMP 저장.
    흰색(255)=미러 ON, 검정(0)=OFF.
    """
    m = np.zeros(nrows * ncols, dtype=bool)
    m[changed_flat] = True
    m = m.reshape(nrows, ncols)
    if scale > 1:
        m = m.repeat(scale, axis=0).repeat(scale, axis=1)  # NEAREST 확대와 동일

    x0, y0 = placement_offset(nrows, ncols, scale, align)
    canvas = np.zeros((DMD_H, DMD_W), dtype=np.uint8)
    canvas[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m.astype(np.uint8) * 255

    Image.fromarray(canvas, mode="L").save(out_path, format="BMP")

    # DMD 스크립트가 크기 불일치면 오류를 내므로, 저장 직후 여기서 먼저 검증한다.
    with Image.open(out_path) as chk:
        if chk.size != (DMD_W, DMD_H):
            raise RuntimeError(f"BMP 크기 오류 {chk.size} != {(DMD_W, DMD_H)}: {out_path}")


@dataclass
class StepInfo:
    step: int
    max_len: int
    chosen_char: str
    changed_count: int
    bmp_path: str


def run_process(
    grid: List[List[str]],
    out_dir: str,
    scale: int = 1,
    align: str = "center",
    max_steps: Optional[int] = None,
    save_final_grid: bool = True,
    save_sequence_order: bool = True,
) -> List[StepInfo]:
    os.makedirs(out_dir, exist_ok=True)
    nrows = len(grid)
    ncols = len(grid[0]) if nrows else 0
    check_fits_dmd(nrows, ncols, scale)

    # 모든 문자열을 하나의 평면 배열로 이어 붙이고, 셀별 시작 위치/길이/소비 개수만 추적한다.
    cells = [s for row in grid for s in row]
    lens = np.fromiter((len(s) for s in cells), dtype=np.int32, count=len(cells))
    joined = "".join(cells)
    if joined.isascii():
        flat = np.frombuffer(joined.encode("ascii"), dtype=np.uint8)
    else:
        flat = np.frombuffer(joined.encode("utf-32-le"), dtype="<u4")
    starts = np.cumsum(lens, dtype=np.int64) - lens
    pos = np.zeros(len(cells), dtype=np.int32)  # 각 셀에서 이미 소비한 글자 수

    steps: List[StepInfo] = []
    chosen_chars: List[str] = []

    step = 0
    while True:
        remaining = lens - pos
        max_len = int(remaining.max()) if remaining.size else 0
        if max_len == 0:  # 모든 셀이 빔
            break

        step += 1
        if max_steps is not None and step > max_steps:
            break

        # 최대 길이 셀들의 첫 글자 최빈값. 동률이면 스캔 순서(행우선)상 먼저 나온 글자.
        top = np.flatnonzero(remaining == max_len)
        firsts = flat[starts[top] + pos[top]]
        uniq, first_idx, counts = np.unique(firsts, return_index=True, return_counts=True)
        best = uniq[np.lexsort((first_idx, -counts))[0]]

        # 길이와 무관하게, best로 시작하는 모든 셀의 첫 글자 1개 삭제
        alive = np.flatnonzero(remaining > 0)
        changed = alive[flat[starts[alive] + pos[alive]] == best]
        pos[changed] += 1

        chosen = chr(int(best))
        chosen_chars.append(chosen)
        bmp_name = f"step_{step:06d}{chosen}.bmp"
        bmp_path = os.path.join(out_dir, bmp_name)
        save_bmp_mask(changed, nrows, ncols, bmp_path, scale=scale, align=align)

        steps.append(StepInfo(step, max_len, chosen, int(changed.size), bmp_path))
        print(f"step {step}: max_len={max_len} char={chosen} changed={changed.size}")

    # ===== 출력물 저장 =====
    # 1) 최종 grid 저장 (정상 종료면 전부 빈 문자열)
    if save_final_grid:
        final_path = os.path.join(out_dir, "final_grid.txt")
        with open(final_path, "w", encoding="utf-8") as f:
            for i in range(nrows):
                base = i * ncols
                f.write("\t".join(cells[base + j][int(pos[base + j]):] for j in range(ncols)) + "\n")

    # 2) step 로그 저장
    log_path = os.path.join(out_dir, "steps_log.tsv")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("step\tmax_len\tchosen_char\tchanged_count\tbmp_path\n")
        for s in steps:
            f.write(f"{s.step}\t{s.max_len}\t{s.chosen_char}\t{s.changed_count}\t{s.bmp_path}\n")

    # 3) 시퀀스 순서 저장
    if save_sequence_order:
        order_txt = os.path.join(out_dir, "sequence_order.txt")
        with open(order_txt, "w", encoding="utf-8") as f:
            f.write("".join(chosen_chars) + "\n")

        order_tsv = os.path.join(out_dir, "sequence_order.tsv")
        with open(order_tsv, "w", encoding="utf-8") as f:
            f.write("step\tchosen_char\tmax_len\tchanged_count\n")
            for s in steps:
                f.write(f"{s.step}\t{s.chosen_char}\t{s.max_len}\t{s.changed_count}\n")

    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", help="2D 문자열 CSV 파일 경로 (미지정 시 자동 탐색)")
    ap.add_argument("--outdir", help="출력 폴더 (미지정 시 스크립트 폴더/<csv 파일명>)")
    ap.add_argument("--delim", default=None,
                    help="구분자: ',' 또는 '\\t' 또는 'whitespace'. 미지정 시 자동추정")
    ap.add_argument("--scale", type=int, default=1,
                    help="셀 하나를 scale x scale 픽셀로 확대(기본 1: 셀 1개 = DMD 픽셀 1개)")
    ap.add_argument("--align", choices=["center", "topleft"], default="center",
                    help="grid가 1920x1080보다 작을 때 놓을 위치(기본 center)")
    ap.add_argument("--max_steps", type=int, default=None, help="최대 반복 횟수(디버그용)")
    ap.add_argument("--no_order", action="store_true", help="sequence_order 파일 저장 안 함")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    infile = args.infile
    if infile is None:
        csv_files = glob.glob(os.path.join(script_dir, "*.csv"))
        if not csv_files:
            raise SystemExit("❌ 같은 폴더에 CSV 파일이 없습니다.")
        csv_files.sort(key=lambda f: os.path.getsize(f), reverse=True)
        infile = csv_files[0]
        print(f"📄 자동 선택된 입력 파일: {infile}")

    outdir = args.outdir
    if outdir is None:
        base = os.path.splitext(os.path.basename(infile))[0]
        outdir = os.path.join(script_dir, base)
        print(f"📁 자동 생성 출력 폴더: {outdir}")

    grid = read_grid(infile, delim=args.delim)
    if not grid:
        raise SystemExit("❌ 입력 파일이 비어 있습니다.")
    print(f"grid: {len(grid[0])}열 x {len(grid)}행 → DMD {DMD_W}x{DMD_H}")

    steps = run_process(
        grid=grid,
        out_dir=outdir,
        scale=max(1, args.scale),
        align=args.align,
        max_steps=args.max_steps,
        save_final_grid=True,
        save_sequence_order=(not args.no_order),
    )

    print(f"✅ 완료: 총 {len(steps)} step 처리")
    if steps:
        last = steps[-1]
        print(f"마지막 step: {last.step}, 선택 문자={last.chosen_char}, 변경={last.changed_count}")
        if not args.no_order:
            print("🧾 sequence_order.txt / sequence_order.tsv 저장 완료")


if __name__ == "__main__":
    main()
