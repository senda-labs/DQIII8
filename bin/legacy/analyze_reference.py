#!/usr/bin/env python3
"""
Analyzes the reference image and extracts technical descriptors
to guide the mathematical generator.
No AI libraries — only numpy and PIL.
"""

import json
import sys

import numpy as np
from PIL import Image


def analyze(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # 1. Dominant palette — 5 colors via simple quantization
    pixels = arr.reshape(-1, 3)
    # Reduce to 32-blocks to group similar colors
    quantized = (pixels // 32 * 32).astype(int)
    colors, counts = np.unique(
        quantized.view(np.dtype((np.void, quantized.dtype.itemsize * 3))),
        return_counts=True,
    )
    top5_idx = counts.argsort()[-5:][::-1]
    palette = []
    for idx in top5_idx:
        color = quantized[
            np.all(
                quantized
                == quantized[
                    np.where(
                        np.all(
                            quantized == np.frombuffer(colors[idx], dtype=quantized.dtype),
                            axis=1,
                        )
                    )[0][0]
                ],
                axis=1,
            )
        ][0].tolist()
        palette.append(
            {
                "rgb": color,
                "hex": "#{:02x}{:02x}{:02x}".format(*color),
                "weight": float(counts[top5_idx[list(top5_idx).index(idx)]]) / len(pixels),
            }
        )

    # 2. Vertical distribution — brightness per third
    gray = arr.mean(axis=2)
    third = h // 3
    distribution = {
        "top_third_brightness": float(gray[:third].mean()),
        "middle_third_brightness": float(gray[third : 2 * third].mean()),
        "bottom_third_brightness": float(gray[2 * third :].mean()),
    }

    # 3. Textural complexity per region (standard deviation)
    texture = {
        "top_complexity": float(gray[:third].std()),
        "middle_complexity": float(gray[third : 2 * third].std()),
        "bottom_complexity": float(gray[2 * third :].std()),
    }

    # 4. Tonal range
    tonal = {
        "min_brightness": float(gray.min()),
        "max_brightness": float(gray.max()),
        "mean_brightness": float(gray.mean()),
        "contrast": float(gray.max() - gray.min()),
    }

    # 5. Color temperature (R vs B ratio)
    r_mean = float(arr[:, :, 0].mean())
    b_mean = float(arr[:, :, 2].mean())
    temperature = "warm" if r_mean > b_mean else "cool"

    return {
        "palette": palette,
        "distribution": distribution,
        "texture": texture,
        "tonal": tonal,
        "color_temperature": temperature,
        "dominant_hue": "blue" if b_mean > r_mean else "red",
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/root/jarvis/tasks/reference_image.jpg"
    result = analyze(path)
    print(json.dumps(result, indent=2))
