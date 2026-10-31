# 桌面物品清点：传统视觉模型与多模态大模型对比

本项目使用同一组桌面图片，对比两种视觉方案：

1. YOLO（可选接入 SAM）检测、定位并统计桌面物品。
2. 视觉大模型识别图片内容并生成结构化物品清单。

第三阶段在原有模型对比基础上增加 FastAPI 后端、SQLAlchemy 运行记录、
Streamlit 前端、Docker Compose 与 nginx 反向代理，形成可部署的完整 Web 应用。

## 项目进度

- [x] 01 建立项目和 Git 仓库
- [x] 02 OpenCV 读取与展示图片
- [x] 03 YOLO 目标检测
- [x] 04 检测结果统计与可视化
- [x] 05 SAM 图像分割
- [x] 06 视觉大模型调用
- [x] 07 双方案对比界面与实验
- [x] 08 文档、运行视频与最终验收
- [x] 09 FastAPI 文件上传与模型接口
- [x] 10 SQLAlchemy 分析记录
- [x] 11 Streamlit 前后端联通
- [x] 12 Docker Compose 与 nginx 配置
- [x] 13 Linux 容器部署与最终验收

## 目录

```text
desktop-inventory-ai/
├─ backend/          # FastAPI、SQLAlchemy 和模型流水线
├─ data/
│  ├─ input/       # 测试图片
│  └─ output/      # 模型输出
├─ deploy/           # nginx 配置
├─ models/           # 本地模型权重（不提交 Git）
├─ src/             # 项目源代码
├─ docs/            # 项目说明与实验记录
├─ compose.yaml
├─ Dockerfile
├─ .gitignore
└─ README.md
```

## 当前阶段

二阶段模型功能和三阶段 Web 部署均已完成。项目已经在 VirtualBox 的 Ubuntu
环境中通过 Docker Compose 启动，并完成 nginx、Streamlit、FastAPI、SQLAlchemy、
YOLO、MobileSAM 与 Windows 本机 Ollama 的完整联调。

## 环境要求

- Windows 10/11
- Ubuntu 26.04 LTS（VirtualBox）
- Python 3.12
- Git
- Docker Engine 与 Docker Compose
- Ollama 0.12.7 或更高版本
- 本地模型 `qwen3-vl:4b`
- 建议使用 NVIDIA GPU；本项目在 8 GB 显存环境完成验证

## 快速启动

先启动 Ollama，然后双击：

```text
start_app.bat
```

也可以在已启用虚拟环境的终端运行：

```powershell
python src/run_web.py
```

本地地址：

- Streamlit 页面：`http://127.0.0.1:8501`
- FastAPI 文档：`http://127.0.0.1:8000/docs`
- FastAPI 健康检查：`http://127.0.0.1:8000/api/health`

完整项目说明与个人感悟见 [`docs/project-report.md`](docs/project-report.md)。

## OpenCV 基础练习

安装依赖：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

将一张桌面照片放入 `data/input/desk.jpg`，然后运行：

```powershell
python src/image_basics.py data/input/desk.jpg
```

程序会在 `data/output/opencv_result.jpg` 生成缩放和标注后的图片。

## YOLO 目标检测

安装新增依赖后运行：

```powershell
python src/yolo_detect.py data/input/desk.jpg
```

首次运行会自动下载轻量预训练模型 `yolo26n.pt`，检测结果保存到
`data/output/yolo_result.jpg`。

程序还会生成 `data/output/yolo_detections.json`，其中包含类别、置信度、
边界框和类别数量，供后续与视觉大模型结果比较。

## MobileSAM 提示式分割

先运行 YOLO 生成边界框，再运行：

```powershell
python src/sam_segment.py data/input/desk.jpg
```

程序读取 `data/output/yolo_detections.json` 中的边界框，把它们作为提示交给
MobileSAM，并在本地生成 `sam_result.jpg` 和 `sam_masks.json`。

## 本地视觉大模型

启动 Ollama 并确认已安装 `qwen3-vl:4b` 后运行：

```powershell
python src/vlm_inventory.py data/input/desk.jpg
```

程序只连接本机的 `127.0.0.1:11434`，并将结构化物品清单保存到
`data/output/vlm_inventory.json`。

## 启动完整 Web 应用

确保 Ollama 正在运行，然后执行：

```powershell
python src/run_web.py
```

浏览器会打开本地地址 `http://127.0.0.1:8501`。选择图片后点击“运行两种方案”，
前端会把图片提交到 FastAPI，后端依次运行 YOLO、MobileSAM 和 Qwen3-VL，
再将结果与 SQLAlchemy 分析记录返回页面。

## Docker 部署

Linux 部署步骤见 [`docs/deployment.md`](docs/deployment.md)。容器架构包含：

```text
nginx :8080 -> Streamlit :8501 -> FastAPI :8000
                                      |
                                      +-> YOLO / MobileSAM
                                      +-> Ollama Qwen3-VL
                                      +-> SQLite
```

本项目已在 Ubuntu 26.04.1 LTS 中完成实际验证：三个容器均正常运行，健康检查返回
`api: ok` 和 `ollama: ok`，网页可以上传图片并展示属于同一次分析的三种输出及动态统计。

## 隐私约定

- `data/input/` 中的原始照片仅在本机处理，不提交到 Git 仓库。
- `data/output/` 中带检测框的结果图片也不提交到 Git 仓库。
- 图片只上传到本项目的本地 FastAPI，不发送给在线模型或第三方接口。
- SQLite 数据库、模型权重、输入图片和输出结果均不提交 Git。
- 向 GitHub/Gitee 提交前，必须先运行 `git status`，确认没有私人图片。
