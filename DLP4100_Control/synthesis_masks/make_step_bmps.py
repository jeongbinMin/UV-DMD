#!/usr/bin/env python3
"""Sequence grid CSV -> one mask BMP per synthesis cycle (step), sized for the DMD.

    python make_step_bmps.py
    python make_step_bmps.py random_sequences_1920x1080.csv --outdir out_bmp

Algorithm (greedy common-supersequence heuristic, same as the user's
mas20_bmp_file_maker.py):
  1. max_len = longest remaining string over the whole grid.
  2. best = most frequent FIRST letter among the strings of length max_len
     (ties: the letter met first when scanning row by row).
  3. Every cell whose string starts with `best` (any length) loses that first letter.
     Those cells are the ones exposed in this cycle -> white (255) in the step BMP.
  4. Repeat until every string is empty.
The chosen letters, in order, are the synthesis order (sequence_order.txt). Every
string is a subsequence of that order, so exposing the BMPs in step order builds
each cell's sequence, read from its FIRST letter to its last.

The file is named step_<6-digit step><base letter>.bmp, e.g. step_000001A.bmp, which is the
name the LabVIEW program builds (folder + "\\step_" + zero-padded step + letter + ".bmp").
The BMP has exactly the grid size (1920x1080 -> the DMD), 8-bit grey, 0 / 255, so it
goes straight into:  python dmd_display.py step_000001A.bmp
"""
import argparse
import csv
import os

from PIL import Image  # pip install pillow

DMD_COLS, DMD_ROWS = 1920, 1080


def read_grid(path, rows, cols):
    with open(path, newline="", encoding="utf-8") as f:
        grid = [[s.strip() for s in r] for r in csv.reader(f)]
    while grid and not grid[-1]:  # blank lines at the end
        grid.pop()
    if len(grid) != rows:
        raise SystemExit("[ERROR] %s has %d rows, expected %d" % (path, len(grid), rows))
    for i, r in enumerate(grid):
        if len(r) != cols:
            raise SystemExit("[ERROR] row %d has %d columns, expected %d" % (i + 1, len(r), cols))
    return grid


def next_step(grid):
    """One cycle. Returns (max_len, letter, [(row, col), ...]) or None when all strings are empty."""
    max_len = 0
    for row in grid:
        for s in row:
            if len(s) > max_len:
                max_len = len(s)
    if max_len == 0:
        return None
    counts = {}  # insertion order = first-seen order, used for ties
    for row in grid:
        for s in row:
            if len(s) == max_len:
                counts[s[0]] = counts.get(s[0], 0) + 1
    letter, best = None, -1
    for c, n in counts.items():
        if n > best:
            letter, best = c, n
    changed = []
    for i, row in enumerate(grid):
        for j, s in enumerate(row):
            if s and s[0] == letter:
                row[j] = s[1:]
                changed.append((i, j))
    return max_len, letter, changed


def write_mask(changed, rows, cols, path):
    """Save the step mask and read it back: the file must hold exactly the exposed cells."""
    buf = bytearray(rows * cols)
    for r, c in changed:
        buf[r * cols + c] = 255
    Image.frombytes("L", (cols, rows), bytes(buf)).save(path, format="BMP")
    back = Image.open(path)
    if back.size != (cols, rows) or back.convert("L").tobytes() != bytes(buf):
        raise SystemExit("[ERROR] %s does not match the exposed cells" % path)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Make one DMD mask BMP per synthesis step from a sequence CSV.")
    ap.add_argument("infile", nargs="?", default=os.path.join(here, "random_sequences_1920x1080.csv"))
    ap.add_argument("--outdir", help="default: <csv name without .csv>_bmp next to the CSV")
    ap.add_argument("--rows", type=int, default=DMD_ROWS, help="default 1080")
    ap.add_argument("--cols", type=int, default=DMD_COLS, help="default 1920")
    ap.add_argument("--no-base", action="store_true",
                    help="leave the base letter out of the file name: step_000001.bmp "
                         "(default: step_000001A.bmp, the name the LabVIEW program builds)")
    ap.add_argument("--max-steps", type=int, default=None, help="stop early (debugging)")
    a = ap.parse_args()

    if not os.path.isfile(a.infile):
        raise SystemExit("[ERROR] CSV not found: %s (make one with make_random_csv.py)" % a.infile)
    outdir = a.outdir or os.path.splitext(a.infile)[0] + "_bmp"
    os.makedirs(outdir, exist_ok=True)
    grid = read_grid(a.infile, a.rows, a.cols)
    total_bases = sum(len(s) for row in grid for s in row)
    longest = max(len(s) for row in grid for s in row)
    print("[INFO] %s: %d x %d cells, %d bases, longest %d" % (a.infile, a.cols, a.rows, total_bases, longest))

    order, log, exposed = [], [], 0
    step = 0
    while True:
        if a.max_steps is not None and step >= a.max_steps:
            break
        res = next_step(grid)
        if res is None:
            break
        step += 1
        max_len, letter, changed = res
        name = "step_%06d%s.bmp" % (step, "" if a.no_base else letter)
        write_mask(changed, a.rows, a.cols, os.path.join(outdir, name))
        order.append(letter)
        log.append((step, letter, max_len, len(changed), name))
        exposed += len(changed)
        if step % 10 == 0:
            print("[INFO] step %d ..." % step)

    with open(os.path.join(outdir, "sequence_order.txt"), "w", encoding="utf-8") as f:
        f.write("".join(order) + "\n")
    with open(os.path.join(outdir, "steps_log.tsv"), "w", encoding="utf-8") as f:
        f.write("step\tbase\tmax_len\texposed_cells\tbmp\n")
        for row in log:
            f.write("\t".join(str(v) for v in row) + "\n")

    complete = a.max_steps is None
    if complete and exposed != total_bases:  # cannot happen; guards against a future edit
        raise SystemExit("[ERROR] exposed %d cells but the grid has %d bases" % (exposed, total_bases))
    print("[OK] %d steps -> %s" % (step, outdir))
    print("[INFO] lower bound %d (longest string), naive ACGT x %d = %d" % (longest, longest, 4 * longest))
    print("[INFO] synthesis order: %s%s" % ("".join(order[:60]), "..." if len(order) > 60 else ""))
    print("SUCCESS" if complete else "[WARN] stopped early by --max-steps")


if __name__ == "__main__":
    main()
