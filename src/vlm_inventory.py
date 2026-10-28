"""通过本机 Ollama 调用 Qwen3-VL，生成结构化物品清单。"""

from argparse import ArgumentParser
import base64
import json
from pathlib import Path

import cv2
import requests


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["name", "count", "confidence", "reason"],
            },
        },
    },
    "required": ["scene", "items"],
}

PROMPT = """请观察这张图片，生成桌面物品清单。
要求：
1. 只统计图片中清晰可见、可以单独拿起的主要物品。
2. 同类物品合并并给出数量。
3. 不要把桌面、地面、墙面等背景计入物品清单。
4. 使用具体、常见的中文物品名称，不要猜测品牌。
5. confidence 只能是 high、medium 或 low。
6. reason 用一句简短中文说明判断依据。
7. 严格按照给定 JSON Schema 返回，不要添加额外文字。
"""


def image_to_base64(image_path: Path, max_side: int) -> str:
    if not image_path.exists():
        raise FileNotFoundError(f"输入图片不存在：{image_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"无法读取图片：{image_path}")

    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )

    success, encoded = cv2.imencode(
        ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90]
    )
    if not success:
        raise RuntimeError("图片内存编码失败")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def request_inventory(
    image_path: Path, model_name: str, timeout: int, max_side: int
) -> dict:
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": PROMPT,
                "images": [image_to_base64(image_path, max_side)],
            }
        ],
        "format": OUTPUT_SCHEMA,
        "options": {"temperature": 0},
        "stream": False,
    }

    try:
        response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as error:
        raise RuntimeError(
            "无法连接本机 Ollama，请先启动 Ollama，再重新运行程序"
        ) from error
    except requests.Timeout as error:
        raise RuntimeError("本地模型响应超时，可以增大 --timeout 后重试") from error
    except requests.HTTPError as error:
        raise RuntimeError(
            f"Ollama 请求失败（HTTP {response.status_code}）：{response.text}"
        ) from error

    api_result = response.json()
    content = api_result.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Ollama 没有返回可解析的模型内容")

    try:
        inventory = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"模型返回的内容不是有效 JSON：{content}") from error

    if not isinstance(inventory.get("items"), list):
        raise RuntimeError("模型结果缺少 items 列表")
    return inventory


def main() -> None:
    parser = ArgumentParser(description="使用本机 Qwen3-VL 生成物品清单")
    parser.add_argument("input", type=Path, help="输入图片路径")
    parser.add_argument("--model", default="qwen3-vl:4b", help="Ollama 模型名称")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/vlm_inventory.json"),
        help="结构化物品清单路径",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="本地模型响应超时秒数",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=1600,
        help="发送给本地模型前的最大图片边长",
    )
    args = parser.parse_args()

    inventory = request_inventory(
        args.input, args.model, args.timeout, args.max_side
    )
    result = {
        "model": args.model,
        "endpoint": OLLAMA_CHAT_URL,
        "processing": "local",
        **inventory,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"场景：{inventory['scene']}")
    print("物品清单：")
    for item in inventory["items"]:
        print(
            f"- {item['name']}: {item['count']}，"
            f"置信度 {item['confidence']}，依据：{item['reason']}"
        )
    print(f"结构化结果：{args.output}")
    print(f"处理方式：本机 Ollama（{OLLAMA_CHAT_URL}）")


if __name__ == "__main__":
    main()

