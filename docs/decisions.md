# Decisions

- Python engine first for fast iteration and model evaluation (CPU-only).
- ONNX is the model exchange format.
- Go control plane + Go SDK act as the stable interface for business services.
- Protocols are defined in `engine/proto/*` and remain stable across engine changes.
