"""使用预训练 YOLO 模型检测图片中的物体并生成统计结果。"""

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO


def detect_objects(
    input_path: Path,
    output_path: Path,
    model_name: str,
    confidence: float,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"输入图片不存在：{input_path}")

    model = YOLO(model_name)
    results = model.predict(source=str(input_path), conf=confidence, verbose=False)
    result = results[0]

    counts: Counter[str] = Counter()
    if result.boxes is not None:
        for box in result.boxes:
            class_id = int(box.cls.item())
            class_name = result.names[class_id]
            score = float(box.conf.item())
            counts[class_name] += 1

            left, top, right, bottom = box.xyxy[0].tolist()
            print(
                f"检测到：{class_name:<15} "
                f"置信度：{score:.2f} "
                f"边界框：({left:.0f}, {top:.0f}, {right:.0f}, {bottom:.0f})"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotated_image = result.plot()
    if not cv2.imwrite(str(output_path), annotated_image):
        raise OSError(f"检测结果保存失败：{output_path}")

    print("\n物品统计：")
    if counts:
        for class_name, count in counts.most_common():
            print(f"- {class_name}: {count}")
    else:
        print("- 没有检测到置信度达到阈值的物体")
    print(f"\n结果图片：{output_path}")


def parse_args():
    parser = ArgumentParser(description="使用 YOLO 检测图片中的物体")
    parser.add_argument("input", type=Path, help="输入图片路径")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/yolo_result.jpg"),
        help="检测结果图片路径",
    )
    parser.add_argument(
        "--model",
        default="yolo26n.pt",
        help="Ultralytics 模型名称或本地模型路径",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.25,
        help="最低置信度阈值，范围为 0 到 1",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    detect_objects(args.input, args.output, args.model, args.confidence)

