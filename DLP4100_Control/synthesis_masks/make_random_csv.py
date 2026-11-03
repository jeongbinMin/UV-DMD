#!/usr/bin/env python3
"""Random sequence grid for the DMD: 1080 rows x 1920 columns, one sequence per cell.

One cell = one micromirror. The grid has exactly the DMD resolution so the BMPs made
from it by make_step_bmps.py can be sent to dmd_display.py without any resizing.

    python make_random_csv.py
    python make_random_csv.py --out my.csv --min-len 15 --max-len 25 --seed 1234

Based on the user's mas20_random_csv_file.py: same sequence generation, but sized to
the DMD by default and with the options on the command line.
"""
import argparse
import csv
import os
import random

DMD_COLS, DMD_ROWS = 1920, 1080  # DLP9500 / DLP9500UV, GetDMDTYPE() = 0


def random_seq(rng, min_len, max_len, alphabet):
    return "".join(rng.choices(alphabet, k=rng.randint(min_len, max_len)))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Make a random sequence CSV (one sequence per DMD pixel).")
    ap.add_argument("--out", default=os.path.join(here, "random_sequences_1920x1080.csv"))
    ap.add_argument("--rows", type=int, default=DMD_ROWS, help="default 1080 (DMD height)")
    ap.add_argument("--cols", type=int, default=DMD_COLS, help="default 1920 (DMD width)")
    ap.add_argument("--min-len", type=int, default=15)
    ap.add_argument("--max-len", type=int, default=25)
    ap.add_argument("--alphabet", default="ACGT")
    ap.add_argument("--seed", type=int, default=1234, help="same seed -> same CSV (default 1234)")
    ap.add_argument("--no-seed", action="store_true", help="different random CSV every run")
    a = ap.parse_args()

    if a.rows < 1 or a.cols < 1:
        raise SystemExit("[ERROR] --rows and --cols must be >= 1")
    if not 1 <= a.min_len <= a.max_len:
        raise SystemExit("[ERROR] need 1 <= --min-len <= --max-len")
    if not a.alphabet:
        raise SystemExit("[ERROR] --alphabet is empty")

    rng = random.Random(None if a.no_seed else a.seed)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for _ in range(a.rows):
            w.writerow([random_seq(rng, a.min_len, a.max_len, a.alphabet) for _ in range(a.cols)])

    print("[OK] wrote %s" % a.out)
    print("[INFO] grid %d columns x %d rows, length %d-%d, alphabet %s, seed %s"
          % (a.cols, a.rows, a.min_len, a.max_len, a.alphabet, "none" if a.no_seed else a.seed))
    if (a.cols, a.rows) != (DMD_COLS, DMD_ROWS):
        print("[WARN] not 1920x1080: BMPs of this size will be rejected by dmd_display.py")


if __name__ == "__main__":
    main()
