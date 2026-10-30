"""读取 YOLO 边界框，并用 MobileSAM 生成物体分割掩膜。"""

from argparse import ArgumentParser
import json
import os
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(PROJECT_ROOT / ".ultralytics"))

from ultralytics import SAM


def load_detections(json_path: Path):
    if not json_path.exists():
        raise FileNotFoundError(f"YOLO 结果文件不存在：{json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    detections = data.get("detections", [])
    if not detections:
        raise ValueError("YOLO 结果中没有可用于提示 SAM 的边界框")

    boxes = [item["box"] for item in detections]
    return detections, boxes


def segment_objects(
    input_path: Path,
    detections_path: Path,
    output_path: Path,
    json_path: Path,
    model_name: str,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"输入图片不存在：{input_path}")

    detections, boxes = load_detections(detections_path)
    model = SAM(model_name)
    results = model.predict(source=str(input_path), bboxes=boxes, verbose=False)
    result = results[0]

    if result.masks is None:
        raise RuntimeError("SAM 没有生成分割掩膜")

    mask_areas = result.masks.data.sum(dim=(1, 2)).cpu().tolist()
    segments = []
    for index, area in enumerate(mask_areas):
        detection = detections[index] if index < len(detections) else {}
        segments.append(
            {
                "source_class": detection.get("class", "unknown"),
                "source_confidence": detection.get("confidence"),
                "source_box": detection.get("box"),
                "mask_pixel_area": round(float(area)),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mask_image = result.plot()
    if not cv2.imwrite(str(output_path), mask_image):
        raise OSError(f"分割结果保存失败：{output_path}")

    summary = {
        "model": model_name,
        "prompt_type": "YOLO bounding boxes",
        "mask_count": len(mask_areas),
        "segments": segments,
    }
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"读取 YOLO 边界框：{len(boxes)} 个")
    print(f"生成 SAM 掩膜：{len(mask_areas)} 个")
    for index, segment in enumerate(segments, start=1):
        print(
            f"- 掩膜 {index}: {segment['source_class']}, "
            f"像素面积 {segment['mask_pixel_area']}"
        )
    print(f"结果图片：{output_path}")
    print(f"结构化结果：{json_path}")


def parse_args():
    parser = ArgumentParser(description="使用 YOLO 框提示 MobileSAM 分割物体")
    parser.add_argument("input", type=Path, help="输入图片路径")
    parser.add_argument(
        "--detections",
        type=Path,
        default=Path("data/output/yolo_detections.json"),
        help="YOLO 结构化检测结果",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/sam_result.jpg"),
        help="SAM 分割结果图片",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=Path("data/output/sam_masks.json"),
        help="SAM 结构化分割结果",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("SAM_MODEL", "mobile_sam.pt"),
        help="MobileSAM 或 SAM 模型名称",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    segment_objects(
        args.input,
        args.detections,
        args.output,
        args.json,
        args.model,
    )

