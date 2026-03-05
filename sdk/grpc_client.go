package watermark // SDK 包

import ( // 引入包
	"context"                                                                                  // 上下文
	"errors"                                                                                   // 错误处理
	"google.golang.org/grpc"                                                                   // gRPC
	commonv1 "gopkg.inshopline.com/armor/pic-watermark/engine/proto/gen/common/v1"             // 公共协议
	controlplanev1 "gopkg.inshopline.com/armor/pic-watermark/engine/proto/gen/controlplane/v1" // 控制面协议
	enginev1 "gopkg.inshopline.com/armor/pic-watermark/engine/proto/gen/engine/v1"             // 引擎协议
	"strings"                                                                                  // 字符处理
) // 引入包结束

var errPolicyClientMissing = errors.New("policy client not set") // 策略客户端缺失
var errEngineClientMissing = errors.New("engine client not set") // 引擎客户端缺失

// GRPCClient 实现 SDK 的 gRPC 客户端。 // 结构说明
type GRPCClient struct { // 客户端结构
	policy controlplanev1.PolicyServiceClient // 策略客户端
	audit  controlplanev1.AuditServiceClient  // 审计客户端
	engine enginev1.EngineServiceClient       // 引擎客户端
} // 结构结束

// NewGRPCClient 创建 gRPC 客户端。 // 构造函数
func NewGRPCClient(policyConn *grpc.ClientConn, engineConn *grpc.ClientConn) *GRPCClient { // 创建客户端
	var policyClient controlplanev1.PolicyServiceClient // 策略客户端
	var auditClient controlplanev1.AuditServiceClient   // 审计客户端
	if policyConn != nil {                              // 若有策略连接
		policyClient = controlplanev1.NewPolicyServiceClient(policyConn) // 创建策略客户端
		auditClient = controlplanev1.NewAuditServiceClient(policyConn)   // 创建审计客户端
	} // 条件结束
	var engineClient enginev1.EngineServiceClient // 引擎客户端
	if engineConn != nil {                        // 若有引擎连接
		engineClient = enginev1.NewEngineServiceClient(engineConn) // 创建引擎客户端
	} // 条件结束
	return &GRPCClient{ // 返回实例
		policy: policyClient, // 策略客户端
		audit:  auditClient,  // 审计客户端
		engine: engineClient, // 引擎客户端
	} // 返回结束
} // 构造函数结束

// Decide 调用控制面获取策略。 // 方法说明
func (c *GRPCClient) Decide(ctx context.Context, req PolicyRequest) (PolicyDecision, error) { // 决策方法
	if c.policy == nil {                                                                      // 判空
		return PolicyDecision{}, errPolicyClientMissing // 返回错误
	} // 判空结束
	protoReq := &controlplanev1.PolicyRequest{ // 构造请求
		Trace:     toProtoTrace(req.Trace), // 追踪信息
		ImageId:   req.ImageID,             // 图片ID
		ActorRole: req.ActorRole,           // 角色
		Action:    req.Action,              // 动作
	}                                           // 请求结束
	resp, err := c.policy.Decide(ctx, protoReq) // 调用 RPC
	if err != nil {                             // 错误处理
		return PolicyDecision{}, err // 返回错误
	} // 错误结束
	return fromProtoPolicy(resp), nil // 返回结果
} // 方法结束

// Embed 调用引擎进行嵌入。 // 方法说明
func (c *GRPCClient) Embed(ctx context.Context, req EmbedRequest) (EmbedResult, error) { // 嵌入方法
	if c.engine == nil {                                                                 // 判空
		return EmbedResult{}, errEngineClientMissing // 返回错误
	} // 判空结束
	protoReq := &enginev1.EmbedRequest{ // 构造请求
		Image:   toProtoImageInput(req.Image),              // 图片
		Payload: toProtoPayload(req.Decision.Payload),      // 载荷
		Options: toProtoEmbedOptions(req.Decision.Options), // 策略
		Trace:   toProtoTrace(req.Trace),                   // 追踪
	}                                          // 请求结束
	resp, err := c.engine.Embed(ctx, protoReq) // 调用 RPC
	if err != nil {                            // 错误处理
		c.reportAudit(ctx, req.Trace, req.Decision.PolicyID, "", false) // 上报失败
		return EmbedResult{}, err                                       // 返回错误
	} // 错误结束
	c.reportAudit(ctx, req.Trace, req.Decision.PolicyID, resp.WatermarkId, true) // 上报成功
	return EmbedResult{ // 返回结果
		Image:       fromProtoImageOutput(resp.Image), // 输出图片
		WatermarkID: resp.WatermarkId,                 // 水印ID
	}, nil // 返回结束
} // 方法结束

// Extract 调用引擎提取载荷。 // 方法说明
func (c *GRPCClient) Extract(ctx context.Context, req ExtractRequest) (ExtractResult, error) { // 提取方法
	if c.engine == nil {                                                                       // 判空
		return ExtractResult{}, errEngineClientMissing // 返回错误
	} // 判空结束
	protoReq := &enginev1.ExtractRequest{ // 构造请求
		Image: toProtoImageInput(req.Image), // 图片
		Trace: toProtoTrace(req.Trace),      // 追踪
	}                                            // 请求结束
	resp, err := c.engine.Extract(ctx, protoReq) // 调用 RPC
	if err != nil {                              // 错误处理
		return ExtractResult{}, err // 返回错误
	} // 错误结束
	return ExtractResult{ // 返回结果
		Payload:    fromProtoPayload(resp.Payload), // 载荷
		Success:    resp.Success,                   // 成功标志
		Confidence: resp.Confidence,                // 置信度
	}, nil // 返回结束
} // 方法结束

// Verify 调用引擎校验载荷。 // 方法说明
func (c *GRPCClient) Verify(ctx context.Context, req VerifyRequest) (VerifyResult, error) { // 校验方法
	if c.engine == nil {                                                                    // 判空
		return VerifyResult{}, errEngineClientMissing // 返回错误
	} // 判空结束
	protoReq := &enginev1.VerifyRequest{ // 构造请求
		Image:   toProtoImageInput(req.Image), // 图片
		Payload: toProtoPayload(req.Payload),  // 载荷
		Trace:   toProtoTrace(req.Trace),      // 追踪
	}                                           // 请求结束
	resp, err := c.engine.Verify(ctx, protoReq) // 调用 RPC
	if err != nil {                             // 错误处理
		return VerifyResult{}, err // 返回错误
	} // 错误结束
	return VerifyResult{ // 返回结果
		Match:      resp.Match,      // 匹配结果
		Confidence: resp.Confidence, // 置信度
	}, nil // 返回结束
} // 方法结束

// reportAudit 上报审计结果。 // 辅助方法
func (c *GRPCClient) reportAudit(ctx context.Context, trace TraceContext, policyID string, watermarkID string, success bool) { // 上报实现
	if c.audit == nil {                                                                                                        // 判空
		return // 直接返回
	} // 判空结束
	protoReq := &controlplanev1.AuditRequest{ // 构造请求
		Trace:       toProtoTrace(trace), // 追踪信息
		PolicyId:    policyID,            // 策略ID
		WatermarkId: watermarkID,         // 水印ID
		Success:     success,             // 成功标记
	}                                    // 请求结束
	_, _ = c.audit.Report(ctx, protoReq) // 忽略错误
} // 方法结束

// toProtoTrace 转换追踪信息。 // 转换函数
func toProtoTrace(trace TraceContext) *commonv1.TraceContext { // 转换实现
	return &commonv1.TraceContext{ // 返回结构
		RequestId: trace.RequestID,     // 请求ID
		TenantId:  trace.TenantID,      // 租户ID
		ActorId:   trace.ActorID,       // 操作人ID
		Scene:     string(trace.Scene), // 场景
		Timestamp: trace.Timestamp,     // 时间戳
	} // 返回结束
} // 转换结束

// toProtoImageInput 转换图片输入。 // 转换函数
func toProtoImageInput(image ImageInput) *commonv1.ImageInput { // 转换实现
	input := &commonv1.ImageInput{ // 创建输入
		MimeType: image.MimeType, // MIME
	}                        // 输入结束
	if len(image.Data) > 0 { // 优先使用数据
		input.Source = &commonv1.ImageInput_Data{Data: image.Data} // 设置 data
		return input                                               // 返回
	} // 条件结束
	uri := strings.TrimSpace(image.URI) // 读取 URI
	if uri != "" {                      // URI 非空
		input.Source = &commonv1.ImageInput_Uri{Uri: uri} // 设置 uri
	} // 条件结束
	return input // 返回输入
} // 转换结束

// toProtoPayload 转换载荷。 // 转换函数
func toProtoPayload(payload WatermarkPayload) *commonv1.WatermarkPayload { // 转换实现
	return &commonv1.WatermarkPayload{ // 返回结构
		Payload:       payload.Payload,       // 载荷数据
		PayloadFormat: payload.PayloadFormat, // 载荷格式
	} // 返回结束
} // 转换结束

// toProtoEmbedOptions 转换嵌入选项。 // 转换函数
func toProtoEmbedOptions(options EmbedOptions) *commonv1.EmbedOptions { // 转换实现
	overlay := &commonv1.VisibleOverlay{ // 构造覆盖
		Text:     options.Overlay.Text,            // 文本
		Opacity:  options.Overlay.Opacity,         // 透明度
		FontSize: int32(options.Overlay.FontSize), // 字号
		Position: options.Overlay.Position,        // 位置
	} // 覆盖结束
	strength := &commonv1.EmbedStrength{ // 构造强度
		Robust:  options.Strength.Robust,  // 鲁棒强度
		Visible: options.Strength.Visible, // 可见强度
	} // 强度结束
	return &commonv1.EmbedOptions{ // 返回结构
		StrategyId:    options.StrategyID,    // 策略ID
		EnableVisible: options.EnableVisible, // 是否可见
		Overlay:       overlay,               // 覆盖
		Strength:      strength,              // 强度
	} // 返回结束
} // 转换结束

// fromProtoPayload 转换载荷。 // 转换函数
func fromProtoPayload(payload *commonv1.WatermarkPayload) WatermarkPayload { // 转换实现
	if payload == nil {                                                      // 判空
		return WatermarkPayload{} // 返回空
	} // 判空结束
	return WatermarkPayload{ // 返回结构
		Payload:       payload.Payload,       // 载荷数据
		PayloadFormat: payload.PayloadFormat, // 载荷格式
	} // 返回结束
} // 转换结束

// fromProtoOptions 转换嵌入选项。 // 转换函数
func fromProtoOptions(options *commonv1.EmbedOptions) EmbedOptions { // 转换实现
	if options == nil {                                              // 判空
		return EmbedOptions{} // 返回空
	} // 判空结束
	overlay := VisibleOverlay{} // 初始化覆盖
	if options.Overlay != nil { // 覆盖存在
		overlay = VisibleOverlay{ // 转换覆盖
			Text:     options.Overlay.Text,          // 文本
			Opacity:  options.Overlay.Opacity,       // 透明度
			FontSize: int(options.Overlay.FontSize), // 字号
			Position: options.Overlay.Position,      // 位置
		} // 覆盖结束
	} // 覆盖判断结束
	strength := EmbedStrength{}  // 初始化强度
	if options.Strength != nil { // 强度存在
		strength = EmbedStrength{ // 转换强度
			Robust:  options.Strength.Robust,  // 鲁棒强度
			Visible: options.Strength.Visible, // 可见强度
		} // 强度结束
	} // 强度判断结束
	return EmbedOptions{ // 返回结构
		StrategyID:    options.StrategyId,    // 策略ID
		EnableVisible: options.EnableVisible, // 是否可见
		Overlay:       overlay,               // 覆盖
		Strength:      strength,              // 强度
	} // 返回结束
} // 转换结束

// fromProtoPolicy 转换策略响应。 // 转换函数
func fromProtoPolicy(resp *controlplanev1.PolicyResponse) PolicyDecision { // 转换实现
	if resp == nil {                                                       // 判空
		return PolicyDecision{} // 返回空
	} // 判空结束
	return PolicyDecision{ // 返回结构
		PolicyID: resp.PolicyId,                  // 策略ID
		Payload:  fromProtoPayload(resp.Payload), // 载荷
		Options:  fromProtoOptions(resp.Options), // 策略选项
	} // 返回结束
} // 转换结束

// fromProtoImageOutput 转换图片输出。 // 转换函数
func fromProtoImageOutput(image *commonv1.ImageOutput) ImageOutput { // 转换实现
	if image == nil {                                                // 判空
		return ImageOutput{} // 返回空
	} // 判空结束
	return ImageOutput{ // 返回结构
		Data:     image.Data,     // 数据
		MimeType: image.MimeType, // MIME
	} // 返回结束
} // 转换结束
