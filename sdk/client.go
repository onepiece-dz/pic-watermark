package watermark

import "context"

// Client is the SDK interface for watermark decisions and engine calls.
type Client interface {
  Decide(ctx context.Context, req PolicyRequest) (PolicyDecision, error)
  Embed(ctx context.Context, req EmbedRequest) (EmbedResult, error)
  Extract(ctx context.Context, req ExtractRequest) (ExtractResult, error)
  Verify(ctx context.Context, req VerifyRequest) (VerifyResult, error)
}

// PolicyRequest requests a policy decision from the control plane.
type PolicyRequest struct {
  Trace     TraceContext
  ImageID   string
  ActorRole string
  Action    string
}

// EmbedRequest sends the image to the engine with a policy decision.
type EmbedRequest struct {
  Image    ImageInput
  Decision PolicyDecision
  Trace    TraceContext
}

// EmbedResult is the output from the watermark engine.
type EmbedResult struct {
  Image       ImageOutput
  WatermarkID string
}

// ExtractRequest asks the engine to extract a watermark payload.
type ExtractRequest struct {
  Image ImageInput
  Trace TraceContext
}

// ExtractResult returns the extracted payload and confidence.
type ExtractResult struct {
  Payload    WatermarkPayload
  Success    bool
  Confidence float32
}

// VerifyRequest validates that the expected payload is present.
type VerifyRequest struct {
  Image   ImageInput
  Payload WatermarkPayload
  Trace   TraceContext
}

// VerifyResult is the verification outcome.
type VerifyResult struct {
  Match      bool
  Confidence float32
}
