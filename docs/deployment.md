# Linux 与 Docker 部署

## 服务架构

```text
浏览器
  |
  v
nginx:8080
  |
  +--> Streamlit:8501
  |       |
  |       v
  +--> FastAPI:8000
          |
          +--> YOLO + MobileSAM
          +--> Windows Ollama / Qwen3-VL
          +--> SQLite 分析记录
```

## 目录准备

模型权重不会进入镜像或 Git。启动容器前将文件放入：

```text
models/yolo26n.pt
models/mobile_sam.pt
```

复制环境变量示例：

```bash
cp .env.example .env
```

VirtualBox NAT 模式下，Windows 主机通常可通过 `10.0.2.2` 访问，因此默认配置为：

```text
OLLAMA_BASE_URL=http://10.0.2.2:11434
```

实际部署前必须先确认 Windows Ollama 只在可信的虚拟机网络中提供服务，
并由 Windows 防火墙限制访问范围。

## 构建与启动

```bash
docker compose build
docker compose up -d
docker compose ps
```

查看日志：

```bash
docker compose logs -f api
docker compose logs -f web
docker compose logs -f nginx
```

停止服务：

```bash
docker compose down
```

## 验证地址

- Web 页面：`http://<Ubuntu-IP>:8080`
- FastAPI 文档：`http://<Ubuntu-IP>:8000/docs`
- 健康检查：`http://<Ubuntu-IP>:8000/api/health`

## 验收检查

1. nginx、web、api 三个容器均为运行状态。
2. 健康检查返回 API 正常并能访问指定 Ollama 模型。
3. 页面能上传图片并展示原图、YOLO 检测图和 MobileSAM 分割图。
4. Qwen3-VL 能返回结构化物品清单。
5. 最近分析记录中能看到成功或失败状态。
6. 更换图片或请求失败后不会混用上一轮结果。
