package controlplane

import ( // 引入包
	"context" // 上下文
	"fmt"     // 格式化
	"log"     // 日志
	"strings" // 字符处理
	"time"    // 时间

	commonv1 "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/common/v1"             // 公共协议
	controlplanev1 "gopkg.inshopline.com/armor/pic-watermark/controlplane/gen/controlplane/v1" // 控制面协议
) // 引入包结束

// Server 提供策略决策与审计服务。 // 说明
// 注意：这是 MVP 版本，仅用于联调。 // 说明
type Server struct { // 服务结构
	controlplanev1.UnimplementedPolicyServiceServer // 未实现嵌入
	controlplanev1.UnimplementedAuditServiceServer  // 未实现嵌入
} // 结构结束

// NewServer 创建控制面服务实例。 // 构造函数
func NewServer() *Server { // 创建服务
	return &Server{} // 返回实例
} // 函数结束

// Decide 根据场景输出策略与载荷。 // 决策接口
func (s *Server) Decide(ctx context.Context, req *controlplanev1.PolicyRequest) (*controlplanev1.PolicyResponse, error) { // 决策实现
	if req == nil {                                                                                                       // 判空
		return &controlplanev1.PolicyResponse{}, nil // 返回空响应
	} // 判空结束
	trace := req.Trace // 获取追踪
	if trace == nil {  // 追踪为空
		trace = &commonv1.TraceContext{} // 创建空追踪
	} // 追踪结束
	action := strings.ToLower(req.Action) // 规范化动作
	strategyID := "robust-view"           // 默认策略
	enableVisible := false                // 默认不可见
	visibleStrength := float32(0.1)       // 默认可见强度
	overlayText := "internal"             // 默认水印文字
	if action == "download" {             // 下载场景
		strategyID = "robust-download" // 下载策略
		enableVisible = true           // 开启可见
		visibleStrength = 0.3          // 提升强度
		overlayText = "download"       // 下载标识
	}                       // 下载结束
	if action == "upload" { // 上传场景
		strategyID = "robust-upload" // 上传策略
		enableVisible = false        // 上传不显示
		visibleStrength = 0.0        // 无可见强度
		overlayText = "upload"       // 上传标识
	} // 上传结束
	payloadText := fmt.Sprintf("%s|%s|%s|%s", trace.TenantId, trace.ActorId, req.ImageId, time.Now().UTC().Format(time.RFC3339Nano)) // 构造载荷文本
	payload := &commonv1.WatermarkPayload{ // 构造载荷
		Payload:       []byte(payloadText), // 载荷字节
		PayloadFormat: "raw",               // 载荷格式
	} // 载荷结束
	overlay := &commonv1.VisibleOverlay{ // 构造可见覆盖
		Text:     overlayText, // 文本
		Opacity:  0.2,         // 透明度
		FontSize: 18,          // 字号
		Position: "center",    // 位置
	} // 覆盖结束
	strength := &commonv1.EmbedStrength{ // 构造强度
		Robust:  1.0,             // 鲁棒强度
		Visible: visibleStrength, // 可见强度
	} // 强度结束
	options := &commonv1.EmbedOptions{ // 构造策略参数
		StrategyId:    strategyID,    // 策略ID
		EnableVisible: enableVisible, // 是否可见
		Overlay:       overlay,       // 覆盖参数
		Strength:      strength,      // 强度参数
	}                                                           // 参数结束
	policyID := fmt.Sprintf("policy-%d", time.Now().UnixNano()) // 生成策略ID
	resp := &controlplanev1.PolicyResponse{ // 构造响应
		PolicyId: policyID, // 策略ID
		Payload:  payload,  // 水印载荷
		Options:  options,  // 策略选项
	}                                                                                            // 响应结束
	log.Printf("policy decide action=%s policy_id=%s strategy=%s", action, policyID, strategyID) // 记录日志
	return resp, nil                                                                             // 返回响应
} // Decide 结束

// Report 接收引擎审计上报。 // 审计接口
func (s *Server) Report(ctx context.Context, req *controlplanev1.AuditRequest) (*controlplanev1.AuditResponse, error) { // 审计实现
	if req == nil {                                                                                                     // 判空
		return &controlplanev1.AuditResponse{Accepted: false}, nil // 返回拒绝
	} // 判空结束
	log.Printf("audit policy_id=%s watermark_id=%s success=%v", req.PolicyId, req.WatermarkId, req.Success) // 记录日志
	return &controlplanev1.AuditResponse{Accepted: true}, nil                                               // 返回接受
} // Report 结束
