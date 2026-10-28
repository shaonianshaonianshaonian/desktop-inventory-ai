# 桌面物品清点：传统视觉模型与多模态大模型对比

本项目使用同一组桌面图片，对比两种视觉方案：

1. YOLO（可选接入 SAM）检测、定位并统计桌面物品。
2. 视觉大模型识别图片内容并生成结构化物品清单。

## 项目进度

- [x] 01 建立项目和 Git 仓库
- [x] 02 OpenCV 读取与展示图片
- [ ] 03 YOLO 目标检测
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

OpenCV 图片处理已经通过真实照片验证。下一步使用 YOLO 完成目标检测。

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
