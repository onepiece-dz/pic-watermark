package main // 主包

import ( // 引入包
  "context" // 上下文
  "errors" // 错误处理
  "flag" // 命令行参数
  "fmt" // 格式化输出
  "log" // 日志
  "os" // 文件系统
  "path/filepath" // 路径处理
  "strings" // 字符处理
  "time" // 时间

  "google.golang.org/grpc" // gRPC
  "google.golang.org/grpc/credentials/insecure" // 明文凭证

  "gopkg.inshopline.com/armor/pic-watermark/sdk" // SDK 客户端
) // 引入包结束

var errInputMissing = errors.New("必须指定 --image 或 --uri") // 输入缺失错误
var errInputBoth = errors.New("--image 和 --uri 只能二选一") // 输入冲突错误
var errFollowupInvalid = errors.New("--followup 只能为 data 或 uri") // followup 错误

// config 保存演示参数。 // 结构说明
type config struct { // 配置结构
  policyAddr string // 控制面地址
  engineAddr string // 引擎地址
  imagePath  string // 图片路径
  imageURI   string // 图片 URI
  outputPath string // 输出路径
  mimeType   string // MIME 类型
  action     string // 动作
  scene      string // 场景
  tenant     string // 租户
  actor      string // 操作人
  role       string // 角色
  requestID  string // 请求ID
  imageID    string // 图片ID
  followup   string // 后续输入方式
} // 结构结束

func parseArgs() config { // 解析参数
  cfg := config{} // 初始化配置
  flag.StringVar(&cfg.policyAddr, "policy-addr", "127.0.0.1:9090", "控制面 gRPC 地址") // 控制面地址
  flag.StringVar(&cfg.engineAddr, "engine-addr", "127.0.0.1:50051", "引擎 gRPC 地址") // 引擎地址
  flag.StringVar(&cfg.imagePath, "image", "", "输入图片路径") // 输入路径
  flag.StringVar(&cfg.imageURI, "uri", "", "输入图片 URI") // 输入 URI
  flag.StringVar(&cfg.outputPath, "output", "", "输出图片路径") // 输出路径
  flag.StringVar(&cfg.mimeType, "mime", "image/jpeg", "图片 MIME 类型") // MIME
  flag.StringVar(&cfg.action, "action", "view", "动作: upload/view/download") // 动作
  flag.StringVar(&cfg.scene, "scene", "internal_view", "场景: internal_view/internal_download/merchant_upload") // 场景
  flag.StringVar(&cfg.tenant, "tenant", "demo-tenant", "租户 ID") // 租户
  flag.StringVar(&cfg.actor, "actor", "demo-actor", "操作人 ID") // 操作人
  flag.StringVar(&cfg.role, "role", "internal", "操作人角色") // 角色
  flag.StringVar(&cfg.requestID, "request-id", "req-demo", "请求 ID") // 请求ID
  flag.StringVar(&cfg.imageID, "image-id", "", "图片 ID") // 图片ID
  flag.StringVar(&cfg.followup, "followup", "data", "后续输入: data/uri") // followup
  flag.Parse() // 解析参数
  return cfg // 返回配置
} // 解析结束

func validateConfig(cfg config) error { // 校验参数
  hasPath := strings.TrimSpace(cfg.imagePath) != "" // 是否有路径
  hasURI := strings.TrimSpace(cfg.imageURI) != "" // 是否有 URI
  if !hasPath && !hasURI { // 都为空
    return errInputMissing // 返回错误
  } // 条件结束
  if hasPath && hasURI { // 同时存在
    return errInputBoth // 返回错误
  } // 条件结束
  if cfg.followup != "data" && cfg.followup != "uri" { // followup 非法
    return errFollowupInvalid // 返回错误
  } // 条件结束
  return nil // 返回成功
} // 校验结束

func buildTrace(cfg config) watermark.TraceContext { // 构建追踪
  return watermark.TraceContext{ // 返回追踪
    RequestID: cfg.requestID, // 请求ID
    TenantID:  cfg.tenant, // 租户
    ActorID:   cfg.actor, // 操作人
    Scene:     watermark.Scene(cfg.scene), // 场景
    Timestamp: time.Now().UTC().Format(time.RFC3339Nano), // 时间戳
  } // 追踪结束
} // 构建结束

func resolveImageID(cfg config) string { // 解析图片ID
  if strings.TrimSpace(cfg.imageID) != "" { // 已指定
    return cfg.imageID // 返回指定
  } // 条件结束
  if strings.TrimSpace(cfg.imagePath) != "" { // 有路径
    return filepath.Base(cfg.imagePath) // 返回文件名
  } // 条件结束
  if strings.TrimSpace(cfg.imageURI) != "" { // 有 URI
    return cfg.imageURI // 返回 URI
  } // 条件结束
  return "image" // 默认值
} // 函数结束

func buildImageInput(cfg config) (watermark.ImageInput, error) { // 构建输入
  if strings.TrimSpace(cfg.imagePath) != "" { // 走本地路径
    data, err := os.ReadFile(cfg.imagePath) // 读取文件
    if err != nil { // 读取失败
      return watermark.ImageInput{}, err // 返回错误
    } // 失败结束
    return watermark.ImageInput{Data: data, MimeType: cfg.mimeType}, nil // 返回数据
  } // 路径结束
  return watermark.ImageInput{URI: cfg.imageURI, MimeType: cfg.mimeType}, nil // 返回 URI
} // 构建结束

func resolveOutput(cfg config) string { // 解析输出路径
  if strings.TrimSpace(cfg.outputPath) != "" { // 已指定
    return cfg.outputPath // 返回指定
  } // 条件结束
  if strings.TrimSpace(cfg.imagePath) != "" { // 有输入路径
    ext := filepath.Ext(cfg.imagePath) // 获取扩展
    if ext == "" { // 无扩展
      return cfg.imagePath + ".watermarked" // 追加后缀
    } // 条件结束
    base := strings.TrimSuffix(cfg.imagePath, ext) // 去掉扩展
    return base + ".watermarked" // 返回路径
  } // 条件结束
  return "output.watermarked" // URI 默认输出
} // 函数结束

func ensureOutputDir(path string) error { // 确保输出目录
  dir := filepath.Dir(path) // 获取目录
  if dir == "." || dir == "" { // 当前目录
    return nil // 无需创建
  } // 条件结束
  return os.MkdirAll(dir, 0o755) // 创建目录
} // 函数结束

func buildFollowupImage(cfg config, embed watermark.ImageOutput, outputPath string) (watermark.ImageInput, error) { // 构建后续输入
  if cfg.followup == "uri" { // 使用 URI
    absPath, err := filepath.Abs(outputPath) // 绝对路径
    if err != nil { // 失败
      return watermark.ImageInput{}, err // 返回错误
    } // 条件结束
    uri := "file://" + absPath // 拼接 URI
    mime := embed.MimeType // 取输出 MIME
    if mime == "" { // 兜底 MIME
      mime = cfg.mimeType // 使用输入 MIME
    } // 条件结束
    return watermark.ImageInput{URI: uri, MimeType: mime}, nil // 返回 URI
  } // 条件结束
  return watermark.ImageInput{Data: embed.Data, MimeType: embed.MimeType}, nil // 返回数据
} // 函数结束

func main() { // 主函数
  cfg := parseArgs() // 解析参数
  if err := validateConfig(cfg); err != nil { // 校验参数
    log.Fatal(err) // 退出
  } // 校验结束
  policyConn, err := grpc.Dial(cfg.policyAddr, grpc.WithTransportCredentials(insecure.NewCredentials())) // 连接控制面
  if err != nil { // 连接失败
    log.Fatal(err) // 退出
  } // 连接结束
  defer policyConn.Close() // 关闭连接
  engineConn, err := grpc.Dial(cfg.engineAddr, grpc.WithTransportCredentials(insecure.NewCredentials())) // 连接引擎
  if err != nil { // 连接失败
    log.Fatal(err) // 退出
  } // 连接结束
  defer engineConn.Close() // 关闭连接
  client := watermark.NewGRPCClient(policyConn, engineConn) // 创建 SDK 客户端
  ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second) // 创建超时上下文
  defer cancel() // 释放资源
  trace := buildTrace(cfg) // 构建追踪
  imageID := resolveImageID(cfg) // 解析图片ID
  policyReq := watermark.PolicyRequest{ // 构造策略请求
    Trace:     trace, // 追踪信息
    ImageID:   imageID, // 图片ID
    ActorRole: cfg.role, // 角色
    Action:    cfg.action, // 动作
  } // 请求结束
  decision, err := client.Decide(ctx, policyReq) // 调用决策
  if err != nil { // 调用失败
    log.Fatal(err) // 退出
  } // 调用结束
  imageInput, err := buildImageInput(cfg) // 构建图片输入
  if err != nil { // 构建失败
    log.Fatal(err) // 退出
  } // 构建结束
  embedReq := watermark.EmbedRequest{ // 构建嵌入请求
    Image:    imageInput, // 图片
    Decision: decision, // 决策
    Trace:    trace, // 追踪
  } // 请求结束
  embedResp, err := client.Embed(ctx, embedReq) // 调用嵌入
  if err != nil { // 调用失败
    log.Fatal(err) // 退出
  } // 调用结束
  outputPath := resolveOutput(cfg) // 解析输出路径
  if err := ensureOutputDir(outputPath); err != nil { // 确保目录
    log.Fatal(err) // 退出
  } // 目录结束
  if writeErr := os.WriteFile(outputPath, embedResp.Image.Data, 0o644); writeErr != nil { // 写入输出
    log.Fatal(writeErr) // 退出
  } // 写入结束
  fmt.Printf("embed_ok watermark_id=%s output=%s\n", embedResp.WatermarkID, outputPath) // 输出结果
  followupImage, err := buildFollowupImage(cfg, embedResp.Image, outputPath) // 构建后续图片
  if err != nil { // 构建失败
    log.Fatal(err) // 退出
  } // 构建结束
  extractReq := watermark.ExtractRequest{ // 构建提取请求
    Image: followupImage, // 图片
    Trace: trace, // 追踪
  } // 请求结束
  extractResp, err := client.Extract(ctx, extractReq) // 调用提取
  if err != nil { // 调用失败
    log.Fatal(err) // 退出
  } // 调用结束
  fmt.Printf("extract_ok=%v confidence=%.2f payload=%s\n", extractResp.Success, extractResp.Confidence, string(extractResp.Payload.Payload)) // 输出提取
  verifyReq := watermark.VerifyRequest{ // 构建校验请求
    Image:   followupImage, // 图片
    Payload: decision.Payload, // 载荷
    Trace:   trace, // 追踪
  } // 请求结束
  verifyResp, err := client.Verify(ctx, verifyReq) // 调用校验
  if err != nil { // 调用失败
    log.Fatal(err) // 退出
  } // 调用结束
  fmt.Printf("verify_match=%v confidence=%.2f\n", verifyResp.Match, verifyResp.Confidence) // 输出校验
} // 主函数结束
