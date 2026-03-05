from __future__ import annotations  # 启用前向注解
from pathlib import Path  # 路径处理
# 分隔  # 代码分隔
def _touch(path: Path) -> None:  # 创建空文件
  path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录
  path.touch(exist_ok=True)  # 创建文件
# 分隔  # 代码分隔
def main() -> int:  # 主函数
  try:  # 捕获依赖错误
    from grpc_tools import protoc  # 导入 grpc 工具
  except Exception:  # 依赖缺失
    print("grpcio-tools is not installed. Run: pip install -r engine/python/requirements.txt")  # 提示安装
    return 1  # 返回失败
# 分隔  # 代码分隔
  root = Path(__file__).resolve().parents[3]  # 定位仓库根目录
  proto_dir = root / "engine/proto"  # 协议目录
  out_dir = root / "engine/python/app/gen"  # 输出目录
# 分隔  # 代码分隔
  out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录
# 分隔  # 代码分隔
  for pkg in [  # 需要创建的包文件
    out_dir / "__init__.py",  # 根包
    out_dir / "common/__init__.py",  # common 包
    out_dir / "common/v1/__init__.py",  # common v1 包
    out_dir / "engine/__init__.py",  # engine 包
    out_dir / "engine/v1/__init__.py",  # engine v1 包
    out_dir / "controlplane/__init__.py",  # controlplane 包
    out_dir / "controlplane/v1/__init__.py",  # controlplane v1 包
  ]:  # 列表结束
    _touch(pkg)  # 生成文件
# 分隔  # 代码分隔
  proto_files = [  # 协议文件列表
    proto_dir / "common/v1/common.proto",  # 公共协议
    proto_dir / "engine/v1/engine.proto",  # 引擎协议
    proto_dir / "controlplane/v1/policy.proto",  # 控制面协议
  ]  # 列表结束
# 分隔  # 代码分隔
  args = [  # protoc 参数
    "protoc",  # 命令名
    f"-I{proto_dir}",  # include 目录
    f"--python_out={out_dir}",  # Python 输出
    f"--grpc_python_out={out_dir}",  # gRPC Python 输出
  ] + [str(p) for p in proto_files]  # 拼接文件列表
# 分隔  # 代码分隔
  rc = protoc.main(args)  # 执行生成
  if rc != 0:  # 生成失败
    print("protoc failed")  # 输出错误
    return rc  # 返回错误码
# 分隔  # 代码分隔
  print(f"generated protobuf stubs in {out_dir}")  # 输出成功信息
  return 0  # 返回成功
# 分隔  # 代码分隔
if __name__ == "__main__":  # 入口判断
  raise SystemExit(main())  # 退出主函数
