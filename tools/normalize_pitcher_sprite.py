"""Normalize pitcher atlases without losing limbs that cross cell borders."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPECS = (
    ("pitcher-right-overhand-30.png", "pitcher-right-overhand-30-normalized.png", "sprite30-normalized-frames", 6, 5),
    ("pitcher-right-underhand.png", "pitcher-right-underhand-normalized.png", "underhand12-normalized-frames", 4, 3),
)


def normalize(source_name: str, output_name: str, frames_name: str, cols: int, rows: int) -> None:
    source_path = ROOT / "game/assets" / source_name
    output_path = ROOT / "game/assets" / output_name
    frames_path = ROOT / "diagnostic_output" / frames_name
    source = Image.open(source_path).convert("RGBA")
    cell_width, cell_height = source.width // cols, source.height // rows
    if cell_width != cell_height or source.size != (cols * cell_width, rows * cell_height):
        raise ValueError(f"{source_name}: atlas is not an exact square-cell {cols}x{rows} grid")
    cell = cell_width
    margin = max(12, round(cell * .05))
    ground_y = cell - margin
    rgba = np.asarray(source)
    alpha = rgba[:, :, 3]
    _, labels = cv2.connectedComponents((alpha > 24).astype(np.uint8), 8)

    chosen = []
    bounds = []
    for index in range(cols * rows):
        col, row = index % cols, index // cols
        x0, y0 = col * cell, row * cell
        inset = labels[y0 + margin : y0 + cell - margin // 2, x0 + margin : x0 + cell - margin]
        ids, counts = np.unique(inset[inset > 0], return_counts=True)
        label = int(ids[np.argmax(counts)])
        ys, xs = np.where(labels == label)
        chosen.append(label)
        bounds.append((int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)))

    max_width = max(right - left for left, _, right, _ in bounds)
    max_height = max(bottom - top for _, top, _, bottom in bounds)
    scale = min((cell - 2 * margin) / max_width, (cell - 2 * margin) / max_height)

    atlas = Image.new("RGBA", source.size)
    frames_path.mkdir(parents=True, exist_ok=True)
    for index, (label, bbox) in enumerate(zip(chosen, bounds)):
        left, top, right, bottom = bbox
        mask = labels[top:bottom, left:right] == label
        crop = rgba[top:bottom, left:right].copy()
        crop[:, :, 3] = np.where(mask, crop[:, :, 3], 0)
        pose = Image.fromarray(crop, "RGBA")
        size = (max(1, round(pose.width * scale)), max(1, round(pose.height * scale)))
        pose = pose.resize(size, Image.Resampling.LANCZOS)

        frame = Image.new("RGBA", (cell, cell))
        x = (cell - pose.width) // 2
        y = ground_y - pose.height
        frame.alpha_composite(pose, (x, y))
        frame.save(frames_path / f"frame-{index + 1:02d}.png")
        atlas.alpha_composite(frame, ((index % cols) * cell, (index // cols) * cell))

    atlas.save(output_path)
    print(f"saved {output_path}")
    print(f"uniform scale={scale:.4f}, source max={max_width}x{max_height}, ground={ground_y}")


def main() -> None:
    for spec in SPECS:
        normalize(*spec)


if __name__ == "__main__":
    main()
