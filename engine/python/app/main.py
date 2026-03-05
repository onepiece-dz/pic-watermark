# -*- coding: utf-8 -*-  # 编码声明
from __future__ import annotations  # 未来注解
import os  # 环境变量
import sys  # 系统路径
from concurrent import futures  # 线程池
from pathlib import Path  # 路径处理
import grpc  # gRPC 服务
# 分隔  # 中文注释
GEN_DIR = Path(__file__).resolve().parent / "gen"  # 生成代码目录
if str(GEN_DIR) not in sys.path:  # 确保可导入 common.v1
    sys.path.insert(0, str(GEN_DIR))  # 注入搜索路径
# 分隔  # 中文注释
from app.service import EngineService  # 引擎实现
from app.gen.engine.v1 import engine_pb2_grpc  # gRPC 注册
# 分隔  # 中文注释
def serve() -> None:  # 启动服务
    addr = os.getenv("ENGINE_ADDR", "0.0.0.0:50051")  # 监听地址
    max_workers = int(os.getenv("ENGINE_MAX_WORKERS", "8"))  # 线程数
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))  # 创建服务端
    engine_pb2_grpc.add_EngineServiceServicer_to_server(EngineService(), server)  # 注册服务
    server.add_insecure_port(addr)  # 绑定端口
    server.start()  # 启动服务
    print(f"watermark engine listening on {addr}")  # 启动日志
    server.wait_for_termination()  # 阻塞等待
# 分隔  # 中文注释
if __name__ == "__main__":  # 入口保护
    serve()  # 启动入口
