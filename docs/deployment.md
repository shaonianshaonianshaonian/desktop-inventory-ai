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
          +--> Redis 消息队列
                  |
                  +--> Celery Worker
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

必须编辑 `.env`，把 `JWT_SECRET` 换成至少 32 位随机字符串。该文件已被 Git 忽略。
可以用下面的命令生成随机值，再复制到 `.env`：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
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

如果 VirtualBox 使用 NAT 网络，Windows 主机不能直接访问虚拟机的 `10.0.2.x`
地址。可以在 Windows 中为正在运行的虚拟机添加端口转发：

```cmd
"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" controlvm "Ubuntu" natpf1 "desktop-web,tcp,127.0.0.1,8080,,8080"
```

随后从 Windows 浏览器访问 `http://127.0.0.1:8080`。端口转发只负责浏览器访问，
模型仍由虚拟机通过 `10.0.2.2:11434` 调用 Windows 本机 Ollama。

## 验收检查

1. nginx、web、api、worker、redis 五个容器均为运行状态。
2. 健康检查返回 API、队列与 Ollama 正常。
3. 页面能上传图片并展示原图、YOLO 检测图和 MobileSAM 分割图。
4. Qwen3-VL 能返回结构化物品清单。
5. 最近分析记录中能看到成功或失败状态。
6. 更换图片或请求失败后不会混用上一轮结果。
7. 未登录请求返回 401，其他用户无法读取历史记录和图片。
8. 页面可以查询 queued/running/succeeded/failed/timed_out/cancelled 状态并取消任务。

## 异步任务与中断

- API 上传成功后返回 HTTP 202 和分析编号，不等待模型推理。
- Redis 保存队列消息，独立 Celery Worker 负责耗时模型进程。
- `ANALYSIS_TIMEOUT_SECONDS` 控制总推理时限，默认 900 秒。
- 取消运行中任务时，API 将状态改为 `cancelling`，Worker 在最多约 0.5 秒内
  终止当前模型子进程，最终记录为 `cancelled`。
- YOLO 检测数为 0 时不会调用 SAM，SAM 掩膜数写为 0，Qwen3-VL 继续运行。
- Qwen3-VL 的场景、物品、数量、置信度和依据必须通过严格校验；负数、0、
  布尔值、浮点数、字符串数量、缺字段和错误回复均会使任务失败。

## 登录与资源权限

- `/api/auth/register` 创建用户，密码使用 PBKDF2-SHA256 加盐散列保存。
- `/api/auth/token` 签发有过期时间的 HS256 JWT。
- 分析创建、状态、历史、取消和图片接口都要求 Bearer JWT。
- 查询记录时同时匹配 `analysis_id` 与 `owner_id`，跨用户请求统一返回 404。
- 输入图片不再通过公共静态目录暴露，而是由受保护接口鉴权后返回。

## 版本验证记录

项目已在 VirtualBox Ubuntu 26.04.1 LTS 中完成部署验证：

- `api` 与 `redis` 状态为 `healthy`，`worker`、`web` 与 `nginx` 正常运行；
- `/api/health` 返回 `api: ok`、`queue: ok`、`ollama: ok` 和 `qwen3-vl:4b`；
- nginx 的 `8080` 入口返回 HTTP 200；
- Windows 浏览器通过 NAT 端口转发正常打开页面；
- 图片上传后，YOLO、MobileSAM、Qwen3-VL 均完成处理；
- 当前图片的检测数、掩膜数和清单物品数由后端结果动态计算；
- 登录、异步任务提交与本人历史记录访问正常；
- 成功记录写入 SQLite，并可在“最近分析记录”中查看；
- 14 项自动化测试覆盖零检测、输出校验、超时、中断、JWT 和跨用户权限。
