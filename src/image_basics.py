"""OpenCV 基础：读取、缩放、标注并保存图片。"""

from argparse import ArgumentParser
from pathlib import Path

import cv2


def resize_to_width(image, target_width: int):
    """保持宽高比例，将图片缩放到指定宽度。"""
    height, width = image.shape[:2]
    scale = target_width / width
    target_height = round(height * scale)
    return cv2.resize(image, (target_width, target_height))


def process_image(input_path: Path, output_path: Path, width: int) -> None:
    image = cv2.imread(str(input_path))
    if image is None:
        raise ValueError(f"无法读取图片，请检查路径和文件格式：{input_path}")

    original_height, original_width = image.shape[:2]
    resized = resize_to_width(image, width)

    label = f"original: {original_width} x {original_height}"
    cv2.putText(
        resized,
        label,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), resized):
        raise OSError(f"图片保存失败：{output_path}")

    output_height, output_width = resized.shape[:2]
    print(f"输入图片：{input_path}")
    print(f"原始尺寸：{original_width} x {original_height}")
    print(f"输出尺寸：{output_width} x {output_height}")
    print(f"处理结果：{output_path}")


def parse_args():
    parser = ArgumentParser(description="读取、缩放、标注并保存一张图片")
    parser.add_argument("input", type=Path, help="输入图片路径")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/opencv_result.jpg"),
        help="输出图片路径",
    )
    parser.add_argument("--width", type=int, default=960, help="输出图片宽度")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_image(args.input, args.output, args.width)

