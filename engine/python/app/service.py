# -*- coding: utf-8 -*-
# 导入未来注解支持，用于类型提示
from __future__ import annotations
# 导入哈希库，用于生成摘要
import hashlib
# 导入JSON库，用于处理审计日志
import json
# 导入MIME类型库，用于猜测文件类型
import mimetypes
# 导入OS库，用于与操作系统交互，如环境变量
import os
# 导入系统库，用于路径操作
import sys
# 导入日期时间库，用于生成时间戳
from datetime import datetime, timezone
# 导入路径处理库
from pathlib import Path
# 导入线程库，用于线程安全
import threading
# 导入UUID库，用于生成唯一ID
import uuid
# 导入类型提示
from typing import NoReturn, Optional, Literal
# 导入gRPC库
import grpc
# 导入IO库，用于内存中的二进制流
from io import BytesIO
# 导入URL解析库
from urllib.parse import urlparse, unquote
# 导入URL请求库
from urllib.request import Request, urlopen

# --- 第三方库 ---
# 导入Pillow库，用于图像处理
from PIL import Image, ImageDraw, ImageFont
# 导入NumPy库，用于数值计算
import numpy as np
# 导入OpenCV库，用于高级图像处理
import cv2
# 导入PyTorch库
import torch
# 导入PyTorch视觉库的函数
import torchvision.transforms.functional as TF

# --- 水印库 ---
# 导入传统频域水印库
from blind_watermark import BlindWatermark
# 导入一个基于深度学习的隐形水印库
from invisible_watermark.invisible_watermark import InvisibleWatermark
# 导入Meta AI的SEAL隐形水印库
import seal

# --- 生成的Proto存根 ---
# 定义生成的gRPC代码目录
GEN_DIR = Path(__file__).resolve().parent / "gen"
# 如果生成目录不在系统路径中，则添加
if str(GEN_DIR) not in sys.path:
    sys.path.insert(0, str(GEN_DIR))

try:
    # 尝试导入生成的gRPC服务和消息定义
    from app.gen.engine.v1 import engine_pb2, engine_pb2_grpc
    from app.gen.common.v1 import common_pb2
except ModuleNotFoundError as err:
    # 如果导入失败，说明protobuf代码未生成，抛出运行时错误
    raise RuntimeError("Proto stubs not found. Run: python scripts/gen_protos.py") from err

# --- 类型定义 ---
# 定义水印策略的字面量类型
WatermarkStrategy = Literal["meta_seal", "blind_watermark", "invisible_watermark", "internal_dct"]

# --- 环境变量帮助函数 ---
# 从环境变量读取整数，带默认值
def _env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except (ValueError, TypeError): return default

# 从环境变量读取布尔值，带默认值
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}

# --- 主引擎服务类 ---
class EngineService(engine_pb2_grpc.EngineServiceServicer):
    # 服务初始化方法
    def __init__(self) -> None:
        # 初始化线程锁，用于保护共享资源
        self._lock = threading.Lock()
        self._audit_lock = threading.Lock()
        # 获取允许的URI协议方案
        schemes = os.getenv("ENGINE_ALLOWED_URI_SCHEMES", "https,http,file")
        self._allowed_schemes = {s.strip() for s in schemes.split(",") if s.strip()}
        # 获取URI读取超时时间（毫秒）
        self._uri_timeout_ms = _env_int("ENGINE_URI_TIMEOUT_MS", 5000)
        # 获取最大允许文件大小（字节）
        self._max_bytes = _env_int("ENGINE_URI_MAX_BYTES", 50 * 1024 * 1024)
        # 获取允许访问的文件根目录
        self._file_root = os.getenv("ENGINE_FILE_ROOT", "").strip()

        # 初始化水印模型（懒加载）
        # 检查是否有可用的CUDA设备，否则使用CPU
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        # 初始化 'invisible_watermark' 模型为空
        self._iw_model: Optional[InvisibleWatermark] = None
        # 初始化 'meta-seal' 编码器为空
        self._seal_encoder: Optional[seal.Encoder] = None
        # 初始化 'meta-seal' 解码器为空
        self._seal_decoder: Optional[seal.Decoder] = None
        # 调用模型初始化方法
        self._init_models()

        # 内部DCT算法的强度参数 (已弃用)
        self.dct_alpha = 0.05

        # 审计功能设置
        # 是否启用审计
        self._audit_enabled = _env_bool("ENGINE_AUDIT_ENABLED", True)
        # 审计日志输出目标 (file, stdout, http)
        self._audit_sink = os.getenv("ENGINE_AUDIT_SINK", "file").strip().lower()
        # 审计HTTP端点地址
        self._audit_http_endpoint = os.getenv("ENGINE_AUDIT_HTTP_ENDPOINT", "").strip()
        # 审计HTTP请求超时时间
        self._audit_http_timeout_ms = _env_int("ENGINE_AUDIT_HTTP_TIMEOUT_MS", 2000)
        # 审计日志文件路径
        audit_value = os.getenv("ENGINE_AUDIT_LOG", "").strip()
        # 解析完整的审计日志路径
        self._audit_path = self._resolve_audit_path(audit_value)
        # 规范化审计输出目标
        self._audit_sink = self._normalize_sink(self._audit_sink, self._audit_http_endpoint)

    # 模型初始化方法
    def _init_models(self):
        print(f"Initializing watermarking models on device: {self.device}") # 打印模型初始化信息和使用的设备
        try:
            # 初始化 invisible-watermark 模型
            self._iw_model = InvisibleWatermark(self.device)
            # 从预训练权重加载 meta-seal 编码器
            self._seal_encoder = seal.Encoder.from_pretrained("unifyai/meta-seal-tiny-v1", device=self.device)
            # 从预训练权重加载 meta-seal 解码器
            self._seal_decoder = seal.Decoder.from_pretrained("unifyai/meta-seal-tiny-v1", device=self.device)
            print("All models loaded successfully.") # 打印模型加载成功信息
        except Exception as e:
            # 如果加载失败，打印错误到标准错误流
            print(f"Error loading models: {e}", file=sys.stderr)

    # --- 主要策略分发器 ---

    # 嵌入隐形水印的核心分发方法
    def _embed_invisible(self, strategy: WatermarkStrategy, image_data: bytes, payload: bytes) -> bytes:
        try:
            # 根据策略ID调用不同的嵌入方法
            if strategy == "meta_seal": return self._embed_seal(image_data, payload)
            if strategy == "blind_watermark": return self._embed_bw(image_data, payload)
            # invisible_watermark 库需要字符串格式的payload
            if strategy == "invisible_watermark": return self._embed_iw(image_data, payload.decode('utf-8'))
            if strategy == "internal_dct": return self._embed_internal_dct(image_data, payload)
            # 如果策略未知，则抛出值错误
            raise ValueError(f"Unknown invisible watermark strategy: {strategy}")
        except Exception as e:
            # 捕获任何异常并包装成运行时错误
            raise RuntimeError(f"Embedding failed for strategy '{strategy}': {e}")

    # 提取隐形水印的核心分发方法
    def _extract_invisible(self, image_data: bytes) -> tuple[bytes, WatermarkStrategy]:
        # 按照从最鲁棒到最不鲁棒的顺序尝试所有策略
        for strategy in ["meta_seal", "blind_watermark", "invisible_watermark", "internal_dct"]:
            try:
                # 依次调用每个策略的提取方法
                if strategy == "meta_seal": return self._extract_seal(image_data), strategy
                if strategy == "blind_watermark": return self._extract_bw(image_data), strategy
                # invisible_watermark 提取出的是字符串，需要编码
                if strategy == "invisible_watermark": return self._extract_iw(image_data).encode('utf-8'), strategy
                if strategy == "internal_dct": return self._extract_internal_dct(image_data), strategy
            except (RuntimeError, ValueError, seal.SealError):
                # 如果当前策略失败，则继续尝试下一个
                continue
        # 如果所有策略都失败，则抛出值错误
        raise ValueError("Could not extract watermark with any available strategy.")

    # --- 终极可见水印实现 (背景反色渐变) ---

    def _apply_visible_watermark(self, image_data: bytes, options: common_pb2.VisibleWatermarkOptions) -> bytes:
        try:
            # 1. 使用Pillow准备蒙版
            # 从二进制数据打开图片，并确保为RGB格式
            original_pil = Image.open(BytesIO(image_data)).convert("RGB")
            # 创建一个与原图同样大小的黑色（值为0）蒙版，用于绘制水印形状
            mask_pil = Image.new("L", original_pil.size, 0)
            # 在蒙版上创建一个绘图对象
            draw = ImageDraw.Draw(mask_pil)
            # 获取或设置字体大小
            font_size = options.font_size or 36
            try:
                # 尝试加载arial字体
                font = ImageFont.truetype("arial.ttf", font_size)
            except IOError:
                # 如果失败，加载默认字体
                font = ImageFont.load_default()

            # 计算文字的边界框
            text_bbox = draw.textbbox((0,0), options.text, font=font)
            # 获取文字的宽度和高度
            text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
            # 定义边距
            margin = 10
            # 定义预设位置的坐标映射
            pos_map = {
                "top_left": (margin, margin),
                "top_right": (original_pil.width - text_w - margin, margin),
                "bottom_left": (margin, original_pil.height - text_h - margin),
                "bottom_right": (original_pil.width - text_w - margin, original_pil.height - text_h - margin),
                "center": ((original_pil.width - text_w) // 2, (original_pil.height - text_h) // 2)
            }
            # 获取用户指定的位置，默认为右下角
            position = pos_map.get(options.position, pos_map["bottom_right"])
            # 在蒙版上的指定位置绘制白色（值为255）文字
            draw.text(position, options.text, font=font, fill=255)

            # 2. 转换为NumPy进行像素级操作
            # 将Pillow图像转换为NumPy数组，并指定数据类型为32位浮点数以便计算
            img_np = np.array(original_pil, dtype=np.float32)
            # 将蒙版Pillow图像转换为布尔类型的NumPy数组
            mask_np = np.array(mask_pil, dtype=bool)

            # 3. 创建反色渐变水印
            # 提取水印区域对应的背景像素
            background = img_np[mask_np]
            # 计算背景像素的反色
            inverted_background = 255.0 - background
            
            # 4. 将反色水印与原始背景混合
            # 获取不透明度，默认为0.5
            opacity = options.opacity or 0.5
            # 根据不透明度公式进行混合
            blended_watermark = background * (1 - opacity) + inverted_background * opacity
            
            # 5. 将混合后的水印放回主图像
            img_np[mask_np] = blended_watermark
            
            # 6. 完成并编码
            # 将浮点数组裁剪到0-255范围，并转换为8位无符号整数
            final_img_np = np.clip(img_np, 0, 255).astype(np.uint8)
            # 从NumPy数组创建最终的Pillow图像
            final_pil = Image.fromarray(final_img_np, 'RGB')
            # 创建一个内存中的二进制流
            buffer = BytesIO()
            # 将最终图像以PNG格式保存到内存流中
            final_pil.save(buffer, format="PNG")
            # 返回内存流的字节内容
            return buffer.getvalue()

        except Exception as e:
            # 捕获任何异常并包装为运行时错误
            raise RuntimeError(f"Failed to apply gradient visible watermark: {e}")

    # --- 隐形水印库的包装器 ---
    
    # Meta-SEAL嵌入方法的包装器
    def _embed_seal(self, image_data: bytes, payload: bytes) -> bytes:
        if not self._seal_encoder: raise RuntimeError("Meta-SEAL encoder not initialized.") # 检查编码器是否已初始化
        # 将图像数据转换为PyTorch张量
        image = TF.to_tensor(Image.open(BytesIO(image_data)).convert("RGB")).to(self.device)
        # 将负载字节串转换为SEAL的消息对象
        message = seal.Message.from_bytes(payload)
        # 使用编码器将消息嵌入图像
        watermarked_image = self._seal_encoder(image, message)
        # 将加水印后的张量图像转换为PNG格式的字节串
        return seal.vision.to_bytes(watermarked_image, format="png")

    # Meta-SEAL提取方法的包装器
    def _extract_seal(self, image_data: bytes) -> bytes:
        if not self._seal_decoder: raise RuntimeError("Meta-SEAL decoder not initialized.") # 检查解码器是否已初始化
        # 将图像数据转换为PyTorch张量
        image = TF.to_tensor(Image.open(BytesIO(image_data)).convert("RGB")).to(self.device)
        # 使用解码器从图像中提取消息
        extracted_message = self._seal_decoder(image)
        # 将提取的SEAL消息对象转换为字节串
        return extracted_message.to_bytes()

    # blind_watermark嵌入方法的包装器
    def _embed_bw(self, image_data: bytes, payload: bytes) -> bytes:
        # 定义临时输入输出文件路径
        in_path, out_path = f"/tmp/{uuid.uuid4()}.png", f"/tmp/{uuid.uuid4()}.png"
        try:
            # 将图像数据写入临时文件
            Path(in_path).write_bytes(image_data)
            # 初始化blind_watermark
            bwm = BlindWatermark(password_img=1, password_wm=1)
            # 嵌入水印，注意payload需要是字符串
            bwm.embed(in_path, wm_content=payload.decode('utf-8'), out_file=out_path)
            # 读取加水印后的文件内容
            return Path(out_path).read_bytes()
        finally:
            # 清理临时文件
            if os.path.exists(in_path): os.remove(in_path)
            if os.path.exists(out_path): os.remove(out_path)

    # blind_watermark提取方法的包装器
    def _extract_bw(self, image_data: bytes) -> bytes:
        # 定义临时输入文件路径
        in_path = f"/tmp/{uuid.uuid4()}.png"
        try:
            # 将图像数据写入临时文件
            Path(in_path).write_bytes(image_data)
            # 初始化blind_watermark
            bwm = BlindWatermark(password_img=1, password_wm=1)
            # 获取水印长度，对于提取是必要的
            wm_len = len(bwm.wm_bit)
            # 提取水印内容，指定长度和模式
            payload = bwm.extract(in_path, wm_shape=wm_len, mode='str')
            # 将提取的字符串负载编码为字节串
            return payload.encode('utf-8')
        finally:
            # 清理临时文件
            if os.path.exists(in_path): os.remove(in_path)

    # invisible-watermark嵌入方法的包装器
    def _embed_iw(self, image_data: bytes, payload: str) -> bytes:
        if not self._iw_model: raise RuntimeError("InvisibleWatermark model not initialized.") # 检查模型是否已初始化
        # 从字节数据打开图像
        img = Image.open(BytesIO(image_data)).convert("RGB")
        # 使用模型编码水印
        wm_image = self._iw_model.encode(img, payload)
        # 将加水印后的图像保存到内存流
        buffer = BytesIO(); wm_image.save(buffer, format='PNG'); return buffer.getvalue()

    # invisible-watermark提取方法的包装器
    def _extract_iw(self, image_data: bytes) -> str:
        if not self._iw_model: raise RuntimeError("InvisibleWatermark model not initialized.") # 检查模型是否已初始化
        # 从字节数据打开图像
        img = Image.open(BytesIO(image_data))
        # 使用模型解码水印
        return self._iw_model.decode(img)

    # 内部DCT嵌入方法（已弃用）
    def _embed_internal_dct(self, image_data: bytes, payload: bytes) -> bytes: return image_data # 不做任何操作，直接返回原图
    # 内部DCT提取方法（已弃用）
    def _extract_internal_dct(self, image_data: bytes) -> bytes: raise ValueError("DCT deprecated") # 抛出错误表示已弃用

    # --- gRPC 服务方法 ---

    # Embed gRPC方法实现
    def Embed(self, request: engine_pb2.EmbedRequest, context):
        # 解析输入图像
        data, _ = self._resolve_image(request.image, context)
        # 初始化策略ID为空
        strategy = ""
        
        # 1. 如果有负载，则应用隐形水印
        if request.payload and request.payload.payload:
            # 获取策略ID，默认为meta_seal
            strategy = request.options.strategy_id or "meta_seal"
            try:
                # 调用隐形水印嵌入方法
                data = self._embed_invisible(strategy, data, request.payload.payload)
            except (RuntimeError, ValueError) as e:
                # 如果失败，中断请求
                self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, str(e))
        
        # 2. 如果请求，则应用可见水印
        if request.options and request.options.enable_visible:
            try:
                # 调用可见水印应用方法
                data = self._apply_visible_watermark(data, request.options.visible_options)
            except RuntimeError as e:
                # 如果失败，中断请求
                self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, str(e))

        # 3. 准备并返回响应
        # 创建图像输出对象
        output = common_pb2.ImageOutput(data=data, mime_type="image/png")
        # 计算最终图像的摘要
        digest = self._digest(output.data)
        # 根据策略生成水印ID前缀
        strategy_prefix = {"meta_seal": "msl", "blind_watermark": "bw", "invisible_watermark": "iw"}.get(strategy, "none")
        # 根据是否启用可见水印生成前缀
        vis_prefix = "vis" if request.options.enable_visible else "invis"
        # 组合成最终的水印ID
        watermark_id = f"wm_{vis_prefix}_{strategy_prefix}_{digest[:10]}"
        
        # 记录审计事件
        self._audit_event("embed", request.trace, digest, self._image_source(request.image), request.payload, True, 1.0, None, watermark_id, strategy)
        # 返回Embed响应
        return engine_pb2.EmbedResponse(image=output, watermark_id=watermark_id)

    # Extract gRPC方法实现
    def Extract(self, request, context):
        # 获取图像来源、数据和摘要
        source, data, digest = self._image_source(request.image), *self._resolve_image(request.image, context), self._digest(self._resolve_image(request.image, context)[0])
        try:
            # 调用隐形水印提取方法
            extracted_payload, strategy = self._extract_invisible(data)
            # 构造负载对象，设置成功状态和置信度
            payload, success, confidence = common_pb2.WatermarkPayload(payload=extracted_payload), True, 1.0
        except (RuntimeError, ValueError):
            # 如果提取失败，返回空负载和失败状态
            payload, success, confidence, strategy = common_pb2.WatermarkPayload(), False, 0.0, ""

        # 记录审计事件
        self._audit_event("extract", request.trace, digest, source, payload, success, confidence, None, "", strategy)
        # 返回Extract响应
        return engine_pb2.ExtractResponse(payload=payload, success=success, confidence=confidence)

    # Verify gRPC方法实现
    def Verify(self, request, context):
        # 校验负载不能为空
        if not request.payload.payload: self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "payload is required")
        # 获取图像来源、数据和摘要
        source, data, digest = self._image_source(request.image), *self._resolve_image(request.image, context), self._digest(self._resolve_image(request.image, context)[0])
        try:
            # 提取隐形水印
            extracted_payload, strategy = self._extract_invisible(data)
            # 比较提取的负载和请求的负载是否匹配
            match = (extracted_payload == request.payload.payload)
            # 根据匹配结果设置置信度
            confidence = 1.0 if match else 0.0
        except (RuntimeError, ValueError):
            # 如果提取失败，则不匹配
            match, confidence, strategy = False, 0.0, ""

        # 记录审计事件
        self._audit_event("verify", request.trace, digest, source, request.payload, match, confidence, match, "", strategy)
        # 返回Verify响应
        return engine_pb2.VerifyResponse(match=match, confidence=confidence)

    # --- 实用工具 & I/O 方法 (已优化) ---
    
    # 解析图像输入（数据或URI）
    def _resolve_image(self, image, context) -> tuple[bytes, str]:
        # 如果图像数据已提供，直接返回
        if image.data: return image.data, self._resolve_mime(image.mime_type, "data.bin")
        # 如果URI也未提供，则中断
        if not image.uri: self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, "Image must have `data` or `uri`")
        # 解析URI
        parsed = urlparse(image.uri)
        # 获取协议方案，默认为'file'
        scheme = parsed.scheme or "file"
        # 检查协议是否在允许列表中
        if scheme not in self._allowed_schemes: self._abort(context, grpc.StatusCode.INVALID_ARGUMENT, f"URI scheme '{scheme}' not allowed")
        # 根据协议方案读取HTTP或文件
        data, mime = self._read_http(image.uri, context) if scheme in {"http", "https"} else self._read_file(parsed.path if parsed.scheme else image.uri, context)
        # 返回数据和MIME类型
        return data, image.mime_type or mime

    # 从文件系统读取文件
    def _read_file(self, path_value: str, context) -> tuple[bytes, str]:
        try:
            # 解析和规范化路径
            path = Path(unquote(path_value)).expanduser().resolve()
            # 检查路径是否在允许的根目录内（如果设置了根目录）
            if self._file_root and not path.is_relative_to(Path(self._file_root).expanduser().resolve()): self._abort(context, grpc.StatusCode.PERMISSION_DENIED, "File path outside allowed root")
            # 检查路径是否为文件
            if not path.is_file(): self._abort(context, grpc.StatusCode.NOT_FOUND, "Path is not a file")
            # 读取文件字节
            data = path.read_bytes()
            # 检查文件大小是否超限
            if len(data) > self._max_bytes: self._abort(context, grpc.StatusCode.RESOURCE_EXHAUSTED, "File is too large")
            # 返回数据和猜测的MIME类型
            return data, self._resolve_mime("", path.name)
        except Exception as e:
            # 捕获异常并中断
            self._abort(context, grpc.StatusCode.INTERNAL, f"File read error: {e}")

    # 从HTTP/HTTPS地址读取数据
    def _read_http(self, uri: str, context) -> tuple[bytes, str]:
        # 设置User-Agent头
        headers = {"User-Agent": "watermark-engine/2.2"}
        try:
            # 发起HTTP请求
            with urlopen(Request(uri, headers=headers), timeout=self._uri_timeout_ms / 1000.0) as resp:
                # 读取内容，最多读取max_bytes + 1个字节以检查是否超限
                data = resp.read(self._max_bytes + 1)
                # 如果读取的字节数超限，则中断
                if len(data) > self._max_bytes: self._abort(context, grpc.StatusCode.RESOURCE_EXHAUSTED, "URI content is too large")
                # 从响应头获取MIME类型
                mime = resp.headers.get("Content-Type", "").split(";")[0].strip()
                # 返回数据和MIME类型
                return data, mime or "application/octet-stream"
        except Exception as e:
            # 捕获异常并中断
            self._abort(context, grpc.StatusCode.UNAVAILABLE, f"Failed to fetch URI: {e}")

    # 解析MIME类型
    @staticmethod
    def _resolve_mime(explicit: str, fallback_name: str) -> str:
        # 如果明确指定了MIME类型，则使用它；否则根据文件名猜测
        return explicit or mimetypes.guess_type(fallback_name)[0] or "application/octet-stream"

    # --- 审计方法 ---
    # (这些方法的实现细节保持不变，只加上注释)
    
    @staticmethod
    def _now_iso() -> str: 
        """获取当前UTC时间的ISO格式字符串"""
        return datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def _abort(context, code, message: str) -> NoReturn: 
        """中断gRPC请求并抛出异常"""
        context.abort(code, message)
        raise RuntimeError(message)
    
    @staticmethod
    def _digest(data: bytes) -> str: 
        """计算数据的SHA256摘要"""
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def _normalize_sink(sink: str, endpoint: str) -> str:
        """规范化审计输出目标"""
        allowed = {"file", "stdout", "http"}
        if sink not in allowed or (sink == "http" and not endpoint):
            return "file"
        return sink
    
    @staticmethod
    def _resolve_audit_path(value: str) -> Path:
        """解析审计日志文件的绝对路径"""
        root = Path(__file__).resolve().parents[2] # 根目录是 app 的上上级
        path = Path(value) if value else root / "logs" / "engine_audit.log"
        return path if path.is_absolute() else root / path
    
    def _ensure_audit_dir(self):
        """确保审计日志目录存在"""
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    
    def _write_audit_file(self, line: str):
        """将审计日志行写入文件"""
        self._ensure_audit_dir()
        with self._audit_lock:
            try:
                with self._audit_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass # 写入失败则忽略
    
    def _post_audit_http(self, record: dict):
        """通过HTTP POST发送审计记录"""
        try:
            payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
            req = Request(self._audit_http_endpoint, data=payload, headers={"Content-Type": "application/json"})
            urlopen(req, timeout=self._audit_http_timeout_ms / 1000.0)
        except Exception:
            pass # 发送失败则忽略
            
    def _write_audit(self, line: str, record: dict):
        """根据配置写入审计日志"""
        if self._audit_sink == "stdout":
            print(line, flush=True)
        elif self._audit_sink == "http":
            self._post_audit_http(record)
        else:
            self._write_audit_file(line)
            
    def _audit_event(self, event: str, trace, image_hash: str, source: str, payload: Optional[common_pb2.WatermarkPayload], success: bool, confidence: float, match: Optional[bool], watermark_id: str, strategy_id: str):
        """记录一个完整的审计事件"""
        if not self._audit_enabled:
            return
        trace_ctx = trace or common_pb2.TraceContext()
        record = {
            "ts": self._now_iso(), "event": event, "request_id": trace_ctx.request_id,
            "tenant_id": trace_ctx.tenant_id, "actor_id": trace_ctx.actor_id, "scene": trace_ctx.scene,
            "source": source, "image_hash": image_hash, "watermark_id": watermark_id, "strategy_id": strategy_id,
            "success": success, "confidence": confidence, "match": match,
            "payload_format": payload.payload_format if payload else "", "payload_size": len(payload.payload) if payload else 0,
        }
        self._write_audit(json.dumps(record, ensure_ascii=False), record)

    def _image_source(self, image) -> str:
        """获取图像来源的字符串表示"""
        if image.uri:
            return image.uri
        if image.data:
            return f"data:({len(image.data)} bytes)"
        return "empty"
