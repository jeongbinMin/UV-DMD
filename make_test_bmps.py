#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LabVIEW -> dmd_display.py 호출 테스트용 BMP 생성.

  step_000001.bmp      정상: 왼쪽 절반만 흰색 (방향/좌우 확인용)
  step_000002.bmp      정상: 120px 체커보드 (패턴이 바뀌었는지 눈으로 구분용)
  bad_size_500x500.bmp 실패 테스트: 크기 불일치 -> 스크립트가 FAILED / 종료코드 1 이어야 함

전체 흰색(전 미러 ON)은 일부러 만들지 않았다. 첫 테스트에서 광원 노출을 최소화하기 위함.
사용: python make_test_bmps.py <출력폴더>
"""
import os
import sys

import numpy as np
from PIL import Image

W, H = 1920, 1080


def save(arr: np.ndarray, path: str) -> None:
    Image.fromarray(arr, mode="L").save(path, format="BMP")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("사용: python make_test_bmps.py <출력폴더>")
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)

    half = np.zeros((H, W), np.uint8)
    half[:, : W // 2] = 255
    save(half, os.path.join(out, "step_000001.bmp"))

    yy, xx = np.indices((H, W))
    checker = (((yy // 120) + (xx // 120)) % 2 * 255).astype(np.uint8)
    save(checker, os.path.join(out, "step_000002.bmp"))

    save(np.zeros((500, 500), np.uint8), os.path.join(out, "bad_size_500x500.bmp"))
    print("생성 완료:", out)


if __name__ == "__main__":
    main()
