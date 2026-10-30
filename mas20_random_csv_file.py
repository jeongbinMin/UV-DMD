import random
import csv

# DMD(DLP Discovery 4100) 해상도. 셀 하나 = DMD 픽셀 하나.
DMD_W = 1920
DMD_H = 1080

def random_seq(min_len=15, max_len=25, alphabet="ACGT") -> str:
    L = random.randint(min_len, max_len)
    return "".join(random.choices(alphabet, k=L))

def make_random_seq_csv(
    out_path: str = f"random_sequences_{DMD_W}x{DMD_H}.csv",
    rows: int = DMD_H,
    cols: int = DMD_W,
    min_len: int = 15,
    max_len: int = 25,
    alphabet: str = "ACGT",
    seed: int | None = None,
):
    if seed is not None:
        random.seed(seed)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for _ in range(rows):
            row = [random_seq(min_len, max_len, alphabet) for _ in range(cols)]
            w.writerow(row)

if __name__ == "__main__":
    make_random_seq_csv(
        out_path=f"random_sequences_{DMD_W}x{DMD_H}.csv",
        rows=DMD_H,
        cols=DMD_W,
        min_len=15,
        max_len=25,
        alphabet="ACGT",  # 필요하면 예: "ACGTN" 또는 "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        seed=1234,        # 재현성 필요 없으면 None
    )
