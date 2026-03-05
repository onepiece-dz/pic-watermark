# Architecture

```mermaid
flowchart LR
  subgraph Biz["Business Services"]
    U["Upload / View / Download"] --> SDK["Go SDK"]
  end

  SDK --> CP["Go Control Plane
Policy / Keys / Audit Map"]
  SDK --> ENG["Watermark Engine (Python, CPU-only)"]
  ENG --> IMG["Object Storage / Delivery"]
  CP --> AUD["Audit Store"]
  CP --> KEY["Policy + Key Store"]

  subgraph ML["Offline Training + Evaluation (Python)"]
    ATT["Attack Simulation / Evaluation"] --> TRN["Training / Fine-tuning"]
    TRN --> EXP["Export ONNX Model Package"]
  end

  EXP --> ENG
  EXP --> CPP["C++ Engine (Later Replacement)"]
```

## Key Flows

1. Merchant upload
- SDK calls control plane for policy/trace payload.
- SDK calls engine to embed robust + fragile watermark.

1. Internal view
- SDK requests a per-request policy and payload.
- SDK calls engine to embed robust + light visible watermark.

1. Internal download
- SDK requests a per-request policy and payload.
- SDK calls engine to embed robust + strong visible watermark.

## Engine Replacement Path

- Model format: ONNX.
- Protocol remains stable via `engine/proto/*`.
- Python engine runs first; C++ engine can replace it later.
