# -*- coding: utf-8 -*-  # 编码声明
from __future__ import annotations  # 未来注解
import hashlib  # 哈希计算
import json  # JSON 序列化
import mimetypes  # MIME 识别
import os  # 环境变量
import sys  # 系统路径
from datetime import datetime, timezone  # 时间处理
from pathlib import Path  # 路径处理
import threading  # 线程锁
import uuid  # 唯一标识
from typing import NoReturn, Optional  # 类型提示
from urllib.parse import unquote, urlparse  # URL 解析
from urllib.request import Request, urlopen  # 网络读取
import grpc  # gRPC 基础
# 分隔  # 中文注释
GEN_DIR = Path(__file__).resolve().parent / "gen"  # 生成代码目录
if str(GEN_DIR) not in sys.path:  # 确保可导入 common.v1
    sys.path.insert(0, str(GEN_DIR))  # 注入路径
# 分隔  # 中文注释
try:  # 尝试导入生成代码
    from app.gen.engine.v1 import engine_pb2, engine_pb2_grpc  # 引擎协议
    from app.gen.common.v1 import common_pb2  # 公共协议
except ModuleNotFoundError as err:  # 未生成代码
    raise RuntimeError("Proto stubs not found. Run: python scripts/gen_protos.py") from err  # 提示
# 分隔  # 中文注释
def _env_int(name: str, default: int) -> int:  # 读取整数环境变量
    value = os.getenv(name, str(default))  # 读取值
    try:  # 尝试转换
        return int(value)  # 返回整数
    except ValueError:  # 转换失败
        return default  # 返回默认
# 分隔  # 中文注释
def _env_bool(name: str, default: bool) -> bool:  # 读取布尔环境变量
    raw = os.getenv(name, "true" if default else "false").strip().lower()  # 读取并规范化
    if raw in {"1", "true", "yes", "y", "on"}:  # 真值集合
        return True  # 返回真
    if raw in {"0", "false", "no", "n", "off"}:  # 假值集合
        return False  # 返回假
    return default  # 兜底默认
# 分隔  # 中文注释
class EngineService(engine_pb2_grpc.EngineServiceServicer):  # 引擎服务
    def __init__(self) -> None:  # 初始化
        self._lock = threading.Lock()  # 线程锁
        self._audit_lock = threading.Lock()  # 审计锁
        self._payload_store = {}  # 哈希到载荷映射
        schemes = os.getenv("ENGINE_ALLOWED_URI_SCHEMES", "https,http,file")  # 允许的协议
        self._allowed_schemes = {s.strip() for s in schemes.split(",") if s.strip()}  # 解析协议
        self._uri_timeout_ms = _env_int("ENGINE_URI_TIMEOUT_MS", 3000)  # 读取超时
        self._max_bytes = _env_int("ENGINE_URI_MAX_BYTES", 10 * 1024 * 1024)  # 最大字节数
        self._file_root = os.getenv("ENGINE_FILE_ROOT", "").strip()  # 文件根目录
        self._audit_enabled = _env_bool("ENGINE_AUDIT_ENABLED", True)  # 审计开关
        self._audit_sink = os.getenv("ENGINE_AUDIT_SINK", "file").strip().lower()  # 审计输出方式
        self._audit_http_endpoint = os.getenv("ENGINE_AUDIT_HTTP_ENDPOINT", "").strip()  # HTTP 端点
        self._audit_http_timeout_ms = _env_int("ENGINE_AUDIT_HTTP_TIMEOUT_MS", 2000)  # HTTP 超时
        audit_value = os.getenv("ENGINE_AUDIT_LOG", "").strip()  # 审计路径
        self._audit_path = self._resolve_audit_path(audit_value)  # 解析路径
        self._audit_sink = self._normalize_sink(self._audit_sink, self._audit_http_endpoint)  # 规范化 sink
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _normalize_sink(sink: str, endpoint: str) -> str:  # 规范化 sink
        allowed = {"file", "stdout", "http"}  # 允许值
        if sink not in allowed:  # 非法值
            return "file"  # 回退文件
        if sink == "http" and not endpoint:  # HTTP 无端点
            return "file"  # 回退文件
        return sink  # 返回原值
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _resolve_audit_path(value: str) -> Path:  # 解析审计路径
        root = Path(__file__).resolve().parents[1]  # 引擎根目录
        if value:  # 若提供路径
            path = Path(value)  # 构建路径
            if not path.is_absolute():  # 相对路径
                path = (root / path).resolve()  # 以根目录拼接
            return path  # 返回路径
        return (root / "logs" / "engine_audit.log").resolve()  # 默认路径
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _now_iso() -> str:  # 生成时间戳
        return datetime.now(timezone.utc).isoformat()  # 返回 UTC 时间
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _abort(context, code, message: str) -> NoReturn:  # 终止请求
        context.abort(code, message)  # gRPC 中止
        raise RuntimeError(message)  # 兜底异常
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _digest(data: bytes) -> str:  # 计算哈希
        return hashlib.sha256(data).hexdigest()  # 返回摘要
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _resolve_mime(explicit: str, fallback_name: str) -> str:  # 计算 MIME
        if explicit:  # 已明确
            return explicit  # 返回指定
        guessed, _ = mimetypes.guess_type(fallback_name)  # 猜测类型
        return guessed or "application/octet-stream"  # 返回结果
# 分隔  # 中文注释
    @staticmethod  # 静态方法
    def _image_source(image) -> str:  # 解析来源
        if image is None:  # 判空
            return "unknown"  # 返回未知
        if image.data:  # 存在数据
            return "data"  # 返回 data
        if image.uri:  # 存在 URI
            return "uri"  # 返回 uri
        return "unknown"  # 兜底
# 分隔  # 中文注释
    def _ensure_audit_dir(self) -> None:  # 确保目录存在
        try:  # 尝试创建
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)  # 创建目录
        except Exception:  # 创建失败
            return  # 忽略失败
# 分隔  # 中文注释
    def _write_audit_file(self, line: str) -> None:  # 写入文件
        self._ensure_audit_dir()  # 确保目录
        with self._audit_lock:  # 加锁写入
            try:  # 尝试写入
                with self._audit_path.open("a", encoding="utf-8") as handle:  # 打开文件
                    handle.write(line + "\n")  # 追加记录
            except Exception:  # 写入失败
                return  # 忽略失败
# 分隔  # 中文注释
    def _post_audit_http(self, record: dict) -> None:  # HTTP 上报
        payload = json.dumps(record, ensure_ascii=False).encode("utf-8")  # 序列化
        req = Request(self._audit_http_endpoint, data=payload, headers={"Content-Type": "application/json"})  # 构造请求
        timeout = self._audit_http_timeout_ms / 1000.0  # 转换秒
        try:  # 尝试请求
            with urlopen(req, timeout=timeout) as _resp:  # 发送请求
                _ = _resp.read(0)  # 触发请求
        except Exception:  # 请求失败
            return  # 忽略失败
# 分隔  # 中文注释
    def _write_audit(self, line: str, record: dict) -> None:  # 写入审计
        if self._audit_sink == "stdout":  # 输出到标准输出
            print(line)  # 打印
            return  # 返回
        if self._audit_sink == "http":  # HTTP 上报
            self._post_audit_http(record)  # 调用 HTTP
            return  # 返回
        self._write_audit_file(line)  # 写文件
# 分隔  # 中文注释
    def _audit_event(  # 审计记录
        self,  # 实例
        event: str,  # 事件类型
        trace,  # 追踪信息
        image_hash: str,  # 图片哈希
        source: str,  # 数据来源
        payload: Optional[common_pb2.WatermarkPayload],  # 载荷
        success: bool,  # 是否成功
        confidence: float,  # 置信度
        match: Optional[bool],  # 是否匹配
        watermark_id: str,  # 水印ID
        strategy_id: str,  # 策略ID
    ) -> None:  # 返回空
        if not self._audit_enabled:  # 开关关闭
            return  # 直接返回
        trace_ctx = trace if trace is not None else common_pb2.TraceContext()  # 兜底追踪
        payload_size = len(payload.payload) if payload is not None else 0  # 载荷长度
        payload_format = payload.payload_format if payload is not None else ""  # 载荷格式
        record = {  # 构建记录
            "ts": self._now_iso(),  # 时间戳
            "event": event,  # 事件类型
            "request_id": trace_ctx.request_id,  # 请求ID
            "tenant_id": trace_ctx.tenant_id,  # 租户ID
            "actor_id": trace_ctx.actor_id,  # 操作人ID
            "scene": trace_ctx.scene,  # 场景
            "source": source,  # 来源
            "image_hash": image_hash,  # 图片哈希
            "watermark_id": watermark_id,  # 水印ID
            "strategy_id": strategy_id,  # 策略ID
            "success": success,  # 是否成功
            "confidence": confidence,  # 置信度
            "match": match,  # 匹配结果
            "payload_format": payload_format,  # 载荷格式
            "payload_size": payload_size,  # 载荷长度
        }  # 记录结束
        line = json.dumps(record, ensure_ascii=False)  # 序列化
        self._write_audit(line, record)  # 写入审计
# 分隔  # 中文注释
    def _read_file(self, path_value: str, context) -> tuple[bytes, str]:  # 读取文件
        raw_path = unquote(path_value)  # 反编码路径
        path = Path(raw_path).expanduser().resolve()  # 规范路径
        if self._file_root:  # 若设置根目录
            root = Path(self._file_root).expanduser().resolve()  # 规范根目录
            try:  # 尝试校验
                path.relative_to(root)  # 必须在根目录下
            except ValueError:  # 不在根目录
                self._abort(context, grpc.StatusCode.PERMISSION_DENIED, "file path outside allowed root")  # 拒绝访问
        if not path.exists():  # 文件不存在
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "file not found")  # 抛错
        data = path.read_bytes()  # 读取文件
        if len(data) > self._max_bytes:  # 超过上限
            self._abort(context, grpc.StatusCode.RESOURCE_EXHAUSTED, "file too large")  # 抛错
        mime = self._resolve_mime("", path.name)  # 解析 MIME
        return data, mime  # 返回结果
# 分隔  # 中文注释
    def _read_http(self, uri: str, context) -> tuple[bytes, str]:  # 读取网络
        req = Request(uri, headers={"User-Agent": "watermark-engine"})  # 构造请求
        timeout = self._uri_timeout_ms / 1000.0  # 转换秒
        try:  # 尝试请求
            with urlopen(req, timeout=timeout) as resp:  # 打开连接
                data = resp.read(self._max_bytes + 1)  # 读取数据
                content_type = resp.headers.get("Content-Type", "")  # 读取类型
        except Exception as fetch_err:  # 请求失败
            self._abort(context, grpc.StatusCode.UNAVAILABLE, f"failed to fetch uri: {fetch_err}")  # 返回错误
        if len(data) > self._max_bytes:  # 超过上限
            self._abort(context, grpc.StatusCode.RESOURCE_EXHAUSTED, "uri content too large")  # 抛错
        mime = content_type.split(";")[0].strip()  # 清理类型
        if not mime:  # 未提供类型
            mime = "application/octet-stream"  # 默认类型
        return data, mime  # 返回结果
# 分隔  # 中文注释
    def _resolve_image(self, image, context) -> tuple[bytes, str]:  # 解析图片
        if image is None:  # 判空
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "image is required")  # 抛错
        if image.data:  # 走数据路径
            mime = self._resolve_mime(image.mime_type, "data")  # 解析 MIME
            return image.data, mime  # 返回结果
        if image.uri:  # 走 URI 路径
            parsed = urlparse(image.uri)  # 解析 URI
            scheme = parsed.scheme or "file"  # 默认为文件
            if scheme not in self._allowed_schemes:  # 不允许协议
                self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "uri scheme not allowed")  # 抛错
            if scheme in {"http", "https"}:  # 网络路径
                data, mime = self._read_http(image.uri, context)  # 读取网络
            else:  # 文件路径
                file_path = parsed.path if parsed.scheme else image.uri  # 解析文件路径
                data, mime = self._read_file(file_path, context)  # 读取文件
            if image.mime_type:  # 若显式指定
                mime = image.mime_type  # 覆盖 MIME
            return data, mime  # 返回结果
        self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "image.data or image.uri is required")  # 抛错
# 分隔  # 中文注释
    def Embed(self, request, context):  # 嵌入接口
        data, mime = self._resolve_image(request.image, context)  # 解析图片
        output = common_pb2.ImageOutput(data=data, mime_type=mime)  # 输出内容
        digest = self._digest(output.data)  # 计算哈希
        payload = request.payload  # 读取载荷
        with self._lock:  # 加锁写入
            self._payload_store[digest] = payload  # 保存载荷
        watermark_id = f"wm_{digest[:12]}_{uuid.uuid4().hex[:8]}"  # 生成标识
        strategy_id = request.options.strategy_id if request.options is not None else ""  # 读取策略
        self._audit_event("embed", request.trace, digest, self._image_source(request.image), payload, True, 1.0, None, watermark_id, strategy_id)  # 写入审计
        return engine_pb2.EmbedResponse(image=output, watermark_id=watermark_id)  # 返回响应
# 分隔  # 中文注释
    def Extract(self, request, context):  # 提取接口
        source = self._image_source(request.image)  # 解析来源
        data, _ = self._resolve_image(request.image, context)  # 解析图片
        digest = self._digest(data)  # 计算哈希
        with self._lock:  # 加锁读取
            payload = self._payload_store.get(digest)  # 读取载荷
        if payload is None:  # 未命中
            self._audit_event("extract", request.trace, digest, source, None, False, 0.0, None, "", "")  # 写入审计
            return engine_pb2.ExtractResponse(payload=common_pb2.WatermarkPayload(), success=False, confidence=0.0)  # 返回失败
        self._audit_event("extract", request.trace, digest, source, payload, True, 1.0, None, "", "")  # 写入审计
        return engine_pb2.ExtractResponse(payload=payload, success=True, confidence=1.0)  # 返回成功
# 分隔  # 中文注释
    def Verify(self, request, context):  # 校验接口
        if not request.payload.payload:  # 缺少载荷
            self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "payload is required")  # 抛错
        source = self._image_source(request.image)  # 解析来源
        data, _ = self._resolve_image(request.image, context)  # 解析图片
        digest = self._digest(data)  # 计算哈希
        with self._lock:  # 加锁读取
            stored = self._payload_store.get(digest)  # 读取载荷
        if stored is None:  # 未命中
            self._audit_event("verify", request.trace, digest, source, request.payload, False, 0.0, False, "", "")  # 写入审计
            return engine_pb2.VerifyResponse(match=False, confidence=0.0)  # 返回失败
        match = (stored.payload == request.payload.payload) and (stored.payload_format == request.payload.payload_format)  # 比较载荷
        confidence = 1.0 if match else 0.0  # 设置置信度
        self._audit_event("verify", request.trace, digest, source, request.payload, match, confidence, match, "", "")  # 写入审计
        return engine_pb2.VerifyResponse(match=match, confidence=confidence)  # 返回结果
