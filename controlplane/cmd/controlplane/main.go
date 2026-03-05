package main // 主包

import ( // 引入包
  "context" // 上下文
  "encoding/json" // JSON 编解码
  "io" // IO 处理
  "log" // 日志
  "net" // 网络
  "net/http" // HTTP
  "os" // 环境变量
  "time" // 时间

  "google.golang.org/grpc" // gRPC

  "gopkg.inshopline.com/armor/pic-watermark/controlplane/internal/controlplane" // 控制面实现
  commonv1 "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/common/v1" // 公共协议
  controlplanev1 "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/controlplane/v1" // 控制面协议
) // 引入包结束

const maxAuditBody = int64(1 << 20) // 审计请求最大体积

// auditRecord 表示引擎上报的审计记录。 // 结构说明
type auditRecord struct { // 审计结构
  Ts           string  `json:"ts"` // 时间戳
  Event        string  `json:"event"` // 事件类型
  RequestID    string  `json:"request_id"` // 请求ID
  TenantID     string  `json:"tenant_id"` // 租户ID
  ActorID      string  `json:"actor_id"` // 操作人ID
  Scene        string  `json:"scene"` // 场景
  Source       string  `json:"source"` // 来源
  ImageHash    string  `json:"image_hash"` // 图片哈希
  WatermarkID  string  `json:"watermark_id"` // 水印ID
  StrategyID   string  `json:"strategy_id"` // 策略ID
  Success      bool    `json:"success"` // 成功标志
  Confidence   float32 `json:"confidence"` // 置信度
  Match        *bool   `json:"match"` // 匹配结果
  PayloadFormat string `json:"payload_format"` // 载荷格式
  PayloadSize  int     `json:"payload_size"` // 载荷长度
  PolicyID     string  `json:"policy_id"` // 策略ID（可选）
} // 结构结束

func main() { // 主函数
  grpcAddr := getenv("CONTROLPLANE_GRPC_ADDR", ":9090") // gRPC 地址
  httpAddr := getenv("CONTROLPLANE_HTTP_ADDR", ":8080") // HTTP 地址
  server := controlplane.NewServer() // 创建服务
  grpcServer := grpc.NewServer() // 创建 gRPC 服务器
  controlplanev1.RegisterPolicyServiceServer(grpcServer, server) // 注册策略服务
  controlplanev1.RegisterAuditServiceServer(grpcServer, server) // 注册审计服务
  lis, err := net.Listen("tcp", grpcAddr) // 监听端口
  if err != nil { // 监听失败
    log.Fatal(err) // 打印错误
  } // 监听结束
  go func() { // 启动 gRPC 协程
    log.Printf("control-plane grpc listening on %s", grpcAddr) // 启动日志
    if serveErr := grpcServer.Serve(lis); serveErr != nil { // 启动服务
      log.Fatal(serveErr) // 启动失败
    } // 启动结束
  }() // 协程结束
  mux := http.NewServeMux() // 创建路由
  mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { // 健康检查
    w.WriteHeader(http.StatusOK) // 返回状态
    _, _ = w.Write([]byte("ok")) // 写入响应
  }) // 路由结束
  mux.HandleFunc("/audit", handleAudit(server)) // 审计入口
  httpServer := &http.Server{ // 创建 HTTP 服务
    Addr:              httpAddr, // 监听地址
    Handler:           mux, // 处理器
    ReadHeaderTimeout: 5 * time.Second, // 头部超时
  } // 服务结束
  log.Printf("control-plane http listening on %s", httpAddr) // 启动日志
  if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed { // 启动监听
    log.Fatal(err) // 启动失败
  } // 启动结束
} // 主函数结束

func handleAudit(server *controlplane.Server) http.HandlerFunc { // 审计处理器
  return func(w http.ResponseWriter, r *http.Request) { // 返回处理函数
    if r.Method != http.MethodPost { // 仅允许 POST
      w.WriteHeader(http.StatusMethodNotAllowed) // 返回 405
      _, _ = w.Write([]byte("method not allowed")) // 写入响应
      return // 结束
    } // 方法判断结束
    limited := http.MaxBytesReader(w, r.Body, maxAuditBody) // 限制大小
    defer limited.Close() // 关闭 body
    data, err := io.ReadAll(limited) // 读取数据
    if err != nil { // 读取失败
      w.WriteHeader(http.StatusBadRequest) // 返回 400
      _, _ = w.Write([]byte("invalid body")) // 写入响应
      return // 结束
    } // 读取结束
    var rec auditRecord // 审计结构
    if err := json.Unmarshal(data, &rec); err != nil { // 解析 JSON
      w.WriteHeader(http.StatusBadRequest) // 返回 400
      _, _ = w.Write([]byte("invalid json")) // 写入响应
      return // 结束
    } // 解析结束
    trace := &commonv1.TraceContext{ // 构建追踪
      RequestId: rec.RequestID, // 请求ID
      TenantId:  rec.TenantID, // 租户ID
      ActorId:   rec.ActorID, // 操作人ID
      Scene:     rec.Scene, // 场景
      Timestamp: rec.Ts, // 时间戳
    } // 追踪结束
    auditReq := &controlplanev1.AuditRequest{ // 构造审计请求
      Trace:       trace, // 追踪信息
      PolicyId:    rec.PolicyID, // 策略ID
      WatermarkId: rec.WatermarkID, // 水印ID
      Success:     rec.Success, // 成功标记
    } // 审计请求结束
    ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second) // 创建超时上下文
    defer cancel() // 释放资源
    _, _ = server.Report(ctx, auditReq) // 调用控制面审计
    log.Printf("audit http event=%s watermark_id=%s success=%v", rec.Event, rec.WatermarkID, rec.Success) // 记录日志
    resp := map[string]any{"accepted": true} // 返回响应
    payload, _ := json.Marshal(resp) // 序列化响应
    w.Header().Set("Content-Type", "application/json") // 设置类型
    w.WriteHeader(http.StatusOK) // 返回状态
    _, _ = w.Write(payload) // 写入响应
  } // 处理函数结束
} // 处理器结束

func getenv(key, fallback string) string { // 读取环境变量
  if v := os.Getenv(key); v != "" { // 若存在
    return v // 返回值
  } // 判断结束
  return fallback // 返回默认
} // getenv 结束
