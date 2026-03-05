#!/bin/bash

# gRPC二方API库相对于当前脚本的文件路径
working_directory=$(dirname "$0")

cd "$working_directory" || exit 1
echo working_directory="$(pwd)"

if [ ! -f "go.mod" ]; then
  echo no go.mod in "$(pwd)"
  exit 1
fi

module=$(grep '^module' go.mod | head -1)
module_path=${module#*"module "}
echo module_path="$module_path"

# package specification: https://protobuf.dev/reference/go/go-generated/#package
find . -type f -name "*.proto" | while read f; do
  f_rel=${f#./}
  dir=$(dirname "$f_rel")
  
  cmd="protoc \
    --proto_path=. \
    --go_out=../gen/ \
    --go_opt=module=$module_path \
    --go_opt=M$f_rel=$module_path/$dir \
    --go-grpc_out=require_unimplemented_servers=false:../gen/ \
    --go-grpc_opt=module=$module_path \
    --go-grpc_opt=M$f_rel=$module_path/$dir \
    $f_rel"
  echo command="$cmd"

  mkdir -p ../gen/"$dir"
  eval "$cmd"
done
