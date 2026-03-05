# Python 水印引擎（CPU-only）

该服务实现 `engine/proto/engine/v1/engine.proto` 的 gRPC 接口，用于嵌入/提取/校验水印。当前为 Python 引擎，后续可被 C++ 引擎替换而不影响 SDK 与控制面。

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 生成 protobuf 代码

```bash
python scripts/gen_protos.py
```

3. 启动引擎

```bash
python -m app.main
```

## 客户端脚本

Embed：
```bash
python scripts/embed_client.py --image /path/to/input.png --output /path/to/output.png
python scripts/embed_client.py --uri file:///path/to/input.png --output /path/to/output.png
```

Extract：
```bash
python scripts/extract_client.py --image /path/to/output.png
python scripts/extract_client.py --uri file:///path/to/output.png
```

Verify：
```bash
python scripts/verify_client.py --image /path/to/output.png --payload demo
python scripts/verify_client.py --uri file:///path/to/output.png --payload demo
```

端到端演示：
```bash
python scripts/e2e_demo.py --image /path/to/input.png
python scripts/e2e_demo.py --uri file:///path/to/input.png --followup uri
```

## 审计日志

- 默认开启，写入 `engine/python/logs/engine_audit.log`（JSONL）。
- 可通过环境变量控制：
  - `ENGINE_AUDIT_ENABLED`：是否启用（默认 true）
  - `ENGINE_AUDIT_SINK`：输出方式（`file` / `stdout` / `http`，默认 file）
  - `ENGINE_AUDIT_LOG`：日志路径（相对路径以 `engine/python` 为根）
  - `ENGINE_AUDIT_HTTP_ENDPOINT`：HTTP 上报地址（仅 `http` 模式）
  - `ENGINE_AUDIT_HTTP_TIMEOUT_MS`：HTTP 超时（默认 2000ms）

## 审计闭环示例

启动控制面 HTTP：
```bash
go run ./controlplane/cmd/controlplane
```

引擎上报到控制面：
```bash
ENGINE_AUDIT_SINK=http \
ENGINE_AUDIT_HTTP_ENDPOINT=http://127.0.0.1:8080/audit \
python -m app.main
```

## 说明
- MVP 的 Embed 为透传逻辑，仅用于打通链路。
- `image.data` 与 `image.uri` 均支持。
- `ENGINE_ALLOWED_URI_SCHEMES` 控制协议白名单，默认 `https,http,file`。
- `ENGINE_FILE_ROOT` 可限制 file 协议读取根目录。
- `ENGINE_URI_MAX_BYTES` 控制最大读取字节数，默认 10MB。
- `ENGINE_URI_TIMEOUT_MS` 控制 URI 读取超时，默认 3000ms。
