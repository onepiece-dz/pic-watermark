from __future__ import annotations  # 启用前向注解
from pathlib import Path  # 路径处理
import shutil  # 工具检测
import subprocess  # 进程执行
def _tool_exists(name: str) -> bool:  # 检查工具是否存在
  return shutil.which(name) is not None  # 返回检测结果
def _run_protoc(proto_dir: Path, out_dir: Path, mappings: dict[str, str], proto_files: list[Path]) -> int:  # 执行 protoc
  args = [  # 构造基础参数
    "protoc",  # 命令名
    f"-I{proto_dir}",  # include 目录
    f"--go_out={out_dir}",  # Go 输出
    f"--go_opt=paths=source_relative",  # Go 路径规则
    f"--go-grpc_out={out_dir}",  # Go gRPC 输出
    f"--go-grpc_opt=paths=source_relative",  # Go gRPC 路径规则
  ]  # 参数结束
  for src, target in mappings.items():  # 遍历映射
    args.append(f"--go_opt=M{src}={target}")  # 设置 Go 映射
    args.append(f"--go-grpc_opt=M{src}={target}")  # 设置 Go gRPC 映射
  args.extend([str(p) for p in proto_files])  # 拼接文件列表
  result = subprocess.run(args, check=False)  # 执行命令
  return result.returncode  # 返回退出码
def main() -> int:  # 主函数
  root = Path(__file__).resolve().parents[2]  # 定位仓库根目录
  proto_dir = root / "proto"  # 协议目录
  sdk_out = root / "sdk/gen"  # SDK 输出目录
  controlplane_out = root / "controlplane/gen"  # 控制面输出目录
  if not proto_dir.exists():  # 协议目录不存在
    print(f"proto dir not found: {proto_dir}")  # 输出错误
    return 1  # 返回失败
  required = ["protoc", "protoc-gen-go", "protoc-gen-go-grpc"]  # 必需工具
  missing = [name for name in required if not _tool_exists(name)]  # 计算缺失
  if missing:  # 有缺失工具
    print("missing tools: " + ", ".join(missing))  # 输出缺失
    print("install with:")  # 输出提示
    print("  go install google.golang.org/protobuf/cmd/protoc-gen-go@latest")  # 安装 protoc-gen-go
    print("  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest")  # 安装 protoc-gen-go-grpc
    print("  ensure protoc is installed and in PATH")  # 提示 protoc
    return 1  # 返回失败
  sdk_out.mkdir(parents=True, exist_ok=True)  # 创建 SDK 目录
  controlplane_out.mkdir(parents=True, exist_ok=True)  # 创建控制面目录
  sdk_mappings = {  # SDK 映射
    "common/v1/common.proto": "gopkg.inshopline.com/armor/pic-watermark/sdk/gen/common/v1",  # common
    "engine/v1/engine.proto": "gopkg.inshopline.com/armor/pic-watermark/sdk/gen/engine/v1",  # engine
    "controlplane/v1/policy.proto": "gopkg.inshopline.com/armor/pic-watermark/sdk/gen/controlplane/v1",  # controlplane
  }  # 映射结束
  controlplane_mappings = {  # 控制面映射
    "common/v1/common.proto": "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/common/v1",  # common
    "controlplane/v1/policy.proto": "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/controlplane/v1",  # controlplane
  }  # 映射结束
  sdk_files = [  # SDK 协议文件
    proto_dir / "common/v1/common.proto",  # common
    proto_dir / "engine/v1/engine.proto",  # engine
    proto_dir / "controlplane/v1/policy.proto",  # controlplane
  ]  # 列表结束
  controlplane_files = [  # 控制面协议文件
    proto_dir / "common/v1/common.proto",  # common
    proto_dir / "controlplane/v1/policy.proto",  # controlplane
  ]  # 列表结束
  rc = _run_protoc(proto_dir, sdk_out, sdk_mappings, sdk_files)  # 生成 SDK 代码
  if rc != 0:  # 失败处理
    print("protoc failed for sdk")  # 输出错误
    return rc  # 返回错误码
  rc = _run_protoc(proto_dir, controlplane_out, controlplane_mappings, controlplane_files)  # 生成控制面代码
  if rc != 0:  # 失败处理
    print("protoc failed for controlplane")  # 输出错误
    return rc  # 返回错误码
  print(f"generated go stubs in {sdk_out} and {controlplane_out}")  # 输出成功
  return 0  # 返回成功
if __name__ == "__main__":  # 入口判断
  raise SystemExit(main())  # 退出主函数
