# pic-watermark

跨境电商图片水印平台，用于商家上传、内部查看与下载的防侵权、追责与审计场景。

## 组件
- `controlplane`：控制面 Go 模块（含 `cmd/controlplane` 与 `internal/controlplane`）
- `sdk`：Go SDK 模块（`sdk`）
- `engine/python`：Python 引擎（CPU-only，当前）
- `engine/cpp`：C++ 引擎占位（后续替换）
- `engine/proto`：gRPC/Protobuf 协议定义
- `docs`：架构与设计文档
- `controlplane/configs`：控制面配置示例
- `engine/python/configs`：引擎配置示例
- `engine/python/models`：模型包存放目录

## Go 多模块说明
- 本仓库使用多模块结构：`controlplane`、`sdk`。
- 根目录提供 `go.work` 用于本地联调。

## 文档
- 架构图与流程：`docs/architecture.md`
- 决策记录：`docs/decisions.md`

## 代码生成
- Python 代码：`python engine/python/scripts/gen_protos.py`
- Go 代码：`python engine/scripts/gen_protos_go.py`
