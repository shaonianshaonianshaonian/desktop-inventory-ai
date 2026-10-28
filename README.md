# 桌面物品清点：传统视觉模型与多模态大模型对比

本项目使用同一组桌面图片，对比两种视觉方案：

1. YOLO（可选接入 SAM）检测、定位并统计桌面物品。
2. 视觉大模型识别图片内容并生成结构化物品清单。

## 项目进度

- [x] 01 建立项目和 Git 仓库
- [x] 02 OpenCV 读取与展示图片
- [x] 03 YOLO 目标检测
- [ ] 04 检测结果统计与可视化
- [ ] 05 SAM 图像分割
- [ ] 06 视觉大模型调用
- [ ] 07 双方案对比界面与实验
- [ ] 08 文档、运行视频与最终验收

## 目录

```text
desktop-inventory-ai/
├─ data/
│  ├─ input/       # 测试图片
│  └─ output/      # 模型输出
├─ src/             # 项目源代码
├─ docs/            # 项目说明与实验记录
├─ .gitignore
└─ README.md
```

## 当前阶段

YOLO 目标检测已经通过本地照片验证。下一步整理检测结果，并分析漏检和误检。

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

## 隐私约定

- `data/input/` 中的原始照片仅在本机处理，不提交到 Git 仓库。
- `data/output/` 中带检测框的结果图片也不提交到 Git 仓库。
- 项目代码只执行本地 YOLO 推理，不调用图片上传接口。
- 向 GitHub/Gitee 提交前，必须先运行 `git status`，确认没有私人图片。
