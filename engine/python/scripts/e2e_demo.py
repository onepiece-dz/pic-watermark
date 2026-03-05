# -*- coding: utf-8 -*-  # 编码声明
import argparse  # 命令行参数
import sys  # 系统路径
from datetime import datetime, timezone  # 时间戳
from pathlib import Path  # 路径处理
import grpc  # gRPC 客户端
# 分隔  # 中文注释
ROOT = Path(__file__).resolve().parents[1]  # 引擎根目录
GEN_DIR = ROOT / "app" / "gen"  # 生成代码目录
if str(ROOT) not in sys.path:  # 确保可导入 app 包
    sys.path.insert(0, str(ROOT))  # 注入搜索路径
if str(GEN_DIR) not in sys.path:  # 确保可导入 common.v1
    sys.path.insert(0, str(GEN_DIR))  # 注入生成路径
# 分隔  # 中文注释
try:  # 尝试导入生成的 proto 代码
    from app.gen.engine.v1 import engine_pb2, engine_pb2_grpc  # 引擎协议
    from app.gen.common.v1 import common_pb2  # 公共协议
except ModuleNotFoundError as err:  # 处理未生成的情况
    raise RuntimeError("Proto stubs not found. Run: python scripts/gen_protos.py") from err  # 提示生成
# 分隔  # 中文注释
def parse_args() -> argparse.Namespace:  # 解析参数
    parser = argparse.ArgumentParser(description="E2E demo: Embed -> Extract -> Verify")  # 创建解析器
    parser.add_argument("--addr", default="127.0.0.1:50051", help="engine addr")  # 引擎地址
    parser.add_argument("--image", default="", help="input image path")  # 输入图片
    parser.add_argument("--uri", default="", help="input image uri")  # 输入 URI
    parser.add_argument("--output", default="", help="output image path")  # 输出路径
    parser.add_argument("--mime", default="image/jpeg", help="mime type")  # MIME 类型
    parser.add_argument("--payload", default="demo", help="payload string")  # 载荷字符串
    parser.add_argument("--payload-format", default="raw", help="payload format")  # 载荷格式
    parser.add_argument("--followup", default="data", choices=["data", "uri"], help="extract/verify input")  # 后续输入
    parser.add_argument("--tenant", default="demo-tenant", help="tenant id")  # 租户ID
    parser.add_argument("--actor", default="demo-actor", help="actor id")  # 操作人ID
    parser.add_argument("--scene", default="internal_view", help="scene")  # 场景
    parser.add_argument("--request-id", default="req-demo", help="request id")  # 请求ID
    return parser.parse_args()  # 返回参数
# 分隔  # 中文注释
def build_image_input(args: argparse.Namespace) -> common_pb2.ImageInput:  # 组装图片
    image_path = args.image.strip()  # 读取路径
    image_uri = args.uri.strip()  # 读取 URI
    if not image_path and not image_uri:  # 二者皆空
        raise ValueError("either --image or --uri is required")  # 抛出错误
    if image_path and image_uri:  # 二者同时提供
        raise ValueError("only one of --image or --uri is allowed")  # 抛出错误
    if image_path:  # 走本地文件
        path = Path(image_path)  # 解析输入路径
        if not path.exists():  # 检查输入是否存在
            raise FileNotFoundError(f"input image not found: {path}")  # 抛出错误
        data = path.read_bytes()  # 读取图片字节
        return common_pb2.ImageInput(data=data, mime_type=args.mime)  # 返回图片输入
    return common_pb2.ImageInput(uri=image_uri, mime_type=args.mime)  # 返回 URI 输入
# 分隔  # 中文注释
def build_trace(args: argparse.Namespace) -> common_pb2.TraceContext:  # 构建追踪
    return common_pb2.TraceContext(  # 返回追踪信息
        request_id=args.request_id,  # 请求ID
        tenant_id=args.tenant,  # 租户ID
        actor_id=args.actor,  # 操作人ID
        scene=args.scene,  # 场景标识
        timestamp=datetime.now(timezone.utc).isoformat(),  # UTC 时间
    )  # 追踪信息结束
# 分隔  # 中文注释
def build_payload(args: argparse.Namespace) -> common_pb2.WatermarkPayload:  # 构建载荷
    return common_pb2.WatermarkPayload(  # 返回载荷
        payload=args.payload.encode("utf-8"),  # 编码载荷
        payload_format=args.payload_format,  # 载荷格式
    )  # 载荷结束
# 分隔  # 中文注释
def build_options() -> common_pb2.EmbedOptions:  # 构建策略
    return common_pb2.EmbedOptions(  # 返回策略
        strategy_id="mvp",  # 策略ID
        enable_visible=False,  # 是否可见水印
    )  # 策略结束
# 分隔  # 中文注释
def resolve_output(args: argparse.Namespace) -> str:  # 输出路径
    output_path = args.output.strip()  # 读取输出
    if output_path:  # 已指定输出
        return output_path  # 直接返回
    if args.image.strip():  # 若有本地文件
        return str(Path(args.image).with_suffix(".watermarked"))  # 默认输出
    return "output.watermarked"  # URI 默认输出
# 分隔  # 中文注释
def build_followup_image(args: argparse.Namespace, embed_image: common_pb2.ImageOutput) -> common_pb2.ImageInput:  # 构建后续图片
    if args.followup == "uri" and args.uri.strip():  # 使用 URI
        return common_pb2.ImageInput(uri=args.uri.strip(), mime_type=args.mime)  # 返回 URI
    return common_pb2.ImageInput(data=embed_image.data, mime_type=embed_image.mime_type)  # 使用数据
# 分隔  # 中文注释
def main() -> None:  # 主函数
    args = parse_args()  # 解析参数
    image_input = build_image_input(args)  # 构建输入
    trace = build_trace(args)  # 构建追踪
    payload = build_payload(args)  # 构建载荷
    options = build_options()  # 构建策略
    channel = grpc.insecure_channel(args.addr)  # 创建通道
    stub = engine_pb2_grpc.EngineServiceStub(channel)  # 创建客户端
    embed_req = engine_pb2.EmbedRequest(image=image_input, payload=payload, options=options, trace=trace)  # 构建嵌入请求
    embed_resp = stub.Embed(embed_req)  # 调用 Embed
    output_path = resolve_output(args)  # 解析输出
    Path(output_path).write_bytes(embed_resp.image.data)  # 写入输出图片
    print(f"embed_ok watermark_id={embed_resp.watermark_id} output={output_path}")  # 输出结果
    followup_image = build_followup_image(args, embed_resp.image)  # 构建后续输入
    extract_req = engine_pb2.ExtractRequest(image=followup_image, trace=trace)  # 构建提取请求
    extract_resp = stub.Extract(extract_req)  # 调用 Extract
    print(f"extract_ok={extract_resp.success} confidence={extract_resp.confidence}")  # 输出提取结果
    verify_req = engine_pb2.VerifyRequest(image=followup_image, payload=payload, trace=trace)  # 构建校验请求
    verify_resp = stub.Verify(verify_req)  # 调用 Verify
    print(f"verify_match={verify_resp.match} confidence={verify_resp.confidence}")  # 输出校验结果
# 分隔  # 中文注释
if __name__ == "__main__":  # 入口保护
    main()  # 执行主函数
