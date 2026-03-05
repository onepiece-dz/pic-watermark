package watermark

// Scene identifies the business scenario for a watermark decision.
type Scene string

const (
  SceneMerchantUpload  Scene = "merchant_upload"
  SceneInternalView    Scene = "internal_view"
  SceneInternalDownload Scene = "internal_download"
)

// ImageInput carries the original image data or a resolvable URI.
type ImageInput struct {
  Data     []byte
  URI      string
  MimeType string
}

// ImageOutput carries the watermarked image result.
type ImageOutput struct {
  Data     []byte
  MimeType string
}

// TraceContext maps requests to audit and tracing identifiers.
type TraceContext struct {
  RequestID string
  TenantID  string
  ActorID   string
  Scene     Scene
  Timestamp string
}

// VisibleOverlay controls the visible watermark text overlay.
type VisibleOverlay struct {
  Text     string
  Opacity  float32
  FontSize int
  Position string
}

// EmbedStrength controls robustness vs visible strength.
type EmbedStrength struct {
  Robust  float32
  Visible float32
}

// EmbedOptions are decided by the control plane.
type EmbedOptions struct {
  StrategyID   string
  EnableVisible bool
  Overlay      VisibleOverlay
  Strength     EmbedStrength
}

// WatermarkPayload carries a traceable payload.
type WatermarkPayload struct {
  Payload       []byte
  PayloadFormat string
}

// PolicyDecision contains the policy result for an embed action.
type PolicyDecision struct {
  PolicyID string
  Payload  WatermarkPayload
  Options  EmbedOptions
}
