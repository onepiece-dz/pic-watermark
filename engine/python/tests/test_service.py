# -*- coding: utf-8 -*-
# 导入pytest框架
import pytest
# 导入gRPC库，用于测试异常情况
import grpc
# 导入pathlib库，用于路径操作
from pathlib import Path
# 导入我们自己的服务和辅助函数
from app.service import EngineService
from tests.helpers import create_test_image
# 导入生成的protobuf消息类型
from app.gen.common.v1 import common_pb2
from app.gen.engine.v1 import engine_pb2

# --- 测试夹具 (Fixtures) ---

@pytest.fixture(scope="module")
def service() -> EngineService:
    """提供一个EngineService的单例，在所有测试中共享，以加速模型加载。"""
    return EngineService()

@pytest.fixture
def mock_context():
    """模拟gRPC的上下文对象，用于测试中断言。"""
    class MockContext:
        def abort(self, code, details):
            raise grpc.RpcError(f"{code}: {details}")
    return MockContext()

# --- 核心功能测试 ---

# 定义一个参数化列表，包含所有要测试的隐形水印策略
invisible_strategies = ["meta_seal", "blind_watermark", "invisible_watermark"]

@pytest.mark.parametrize("strategy", invisible_strategies)
def test_invisible_watermark_e2e(service: EngineService, mock_context, strategy: str):
    """对每种隐形水印策略进行端到端的嵌入和提取测试。"""
    # 1. 准备数据
    original_image_data = create_test_image()
    payload_data = b"test_payload_123!@#$"

    # 2. 构造嵌入请求
    embed_request = engine_pb2.EmbedRequest(
        image=common_pb2.ImageInput(data=original_image_data),
        payload=common_pb2.WatermarkPayload(payload=payload_data),
        options=engine_pb2.EmbedOptions(strategy_id=strategy)
    )

    # 3. 执行嵌入
    embed_response = service.Embed(embed_request, mock_context)
    watermarked_image_data = embed_response.image.data

    # 断言：加水印后的图片与原图不同
    assert original_image_data != watermarked_image_data, "Watermarked image should be different from the original."

    # 4. 构造提取请求
    extract_request = engine_pb2.ExtractRequest(
        image=common_pb2.ImageInput(data=watermarked_image_data)
    )

    # 5. 执行提取
    extract_response = service.Extract(extract_request, mock_context)

    # 6. 断言结果
    assert extract_response.success is True, "Extraction should be successful."
    assert extract_response.payload.payload == payload_data, "Extracted payload must match the original."

def test_visible_watermark_application(service: EngineService, mock_context):
    """测试背景反色渐变可见水印是否被应用。"""
    # 1. 准备数据
    original_image_data = create_test_image()
    watermark_text = "Test Visible WM"

    # 2. 构造嵌入请求（只开启可见水印）
    embed_request = engine_pb2.EmbedRequest(
        image=common_pb2.ImageInput(data=original_image_data),
        options=engine_pb2.EmbedOptions(
            enable_visible=True,
            visible_options=common_pb2.VisibleWatermarkOptions(
                text=watermark_text,
                opacity=0.7,
                position="center"
            )
        )
    )

    # 3. 执行嵌入
    embed_response = service.Embed(embed_request, mock_context)
    watermarked_image_data = embed_response.image.data

    # 4. 断言
    # 只是简单地检查图片数据是否已改变，因为精确的像素验证很复杂
    assert original_image_data != watermarked_image_data, "Applying visible watermark should alter the image data."

def test_combined_watermarking(service: EngineService, mock_context):
    """测试同时应用隐形和可见水印。"""
    # 1. 准备数据
    original_image_data = create_test_image()
    payload_data = b"combined_test"

    # 2. 构造嵌入请求（同时开启两种水印）
    embed_request = engine_pb2.EmbedRequest(
        image=common_pb2.ImageInput(data=original_image_data),
        payload=common_pb2.WatermarkPayload(payload=payload_data),
        options=engine_pb2.EmbedOptions(
            strategy_id="meta_seal",
            enable_visible=True,
            visible_options=common_pb2.VisibleWatermarkOptions(text="Combined")
        )
    )

    # 3. 执行嵌入
    embed_response = service.Embed(embed_request, mock_context)

    # 4. 构造提取请求
    extract_request = engine_pb2.ExtractRequest(image=embed_response.image)
    extract_response = service.Extract(extract_request, mock_context)

    # 5. 断言
    assert extract_response.success is True, "Extraction from combined watermarking should succeed."
    assert extract_response.payload.payload == payload_data, "Payload from combined watermarking should match."

def test_verify_method(service: EngineService, mock_context):
    """测试Verify方法的功能。"""
    # 1. 嵌入一个水印
    original_image_data = create_test_image()
    payload_data = b"verify_this"
    embed_request = engine_pb2.EmbedRequest(
        image=common_pb2.ImageInput(data=original_image_data),
        payload=common_pb2.WatermarkPayload(payload=payload_data),
        options=engine_pb2.EmbedOptions(strategy_id="meta_seal")
    )
    embed_response = service.Embed(embed_request, mock_context)

    # 2. 使用正确的负载进行验证
    verify_request_correct = engine_pb2.VerifyRequest(
        image=embed_response.image,
        payload=common_pb2.WatermarkPayload(payload=payload_data)
    )
    verify_response_correct = service.Verify(verify_request_correct, mock_context)
    assert verify_response_correct.match is True, "Verification should succeed with the correct payload."

    # 3. 使用错误的负载进行验证
    verify_request_wrong = engine_pb2.VerifyRequest(
        image=embed_response.image,
        payload=common_pb2.WatermarkPayload(payload=b"wrong_payload")
    )
    verify_response_wrong = service.Verify(verify_request_wrong, mock_context)
    assert verify_response_wrong.match is False, "Verification should fail with the wrong payload."

# --- 异常和边缘情况测试 ---

def test_invalid_strategy(service: EngineService, mock_context):
    """测试当提供无效策略ID时，服务是否会优雅地失败。"""
    with pytest.raises(grpc.RpcError) as e:
        service.Embed(engine_pb2.EmbedRequest(
            image=common_pb2.ImageInput(data=create_test_image()),
            payload=common_pb2.WatermarkPayload(payload=b"some_data"),
            options=engine_pb2.EmbedOptions(strategy_id="non_existent_strategy")
        ), mock_context)
    # 断言gRPC状态码是否为 INVALID_ARGUMENT
    # 注意：实际的状态码在异常的字符串表示中，这是一个简化的检查
    assert "INVALID_ARGUMENT" in str(e.value), "Should fail with INVALID_ARGUMENT for an unknown strategy."

def test_file_uri_resolution(service: EngineService, mock_context, tmp_path: Path):
    """测试从本地文件URI加载图像的功能。"""
    # 1. 创建一个临时图片文件
    image_data = create_test_image()
    temp_file = tmp_path / "test_image.png"
    temp_file.write_bytes(image_data)

    # 2. 使用 file:// URI 构造请求
    request = engine_pb2.EmbedRequest(
        image=common_pb2.ImageInput(uri=temp_file.as_uri()),
        options=engine_pb2.EmbedOptions(enable_visible=True, visible_options=common_pb2.VisibleWatermarkOptions(text="URI Test"))
    )

    # 3. 执行嵌入并断言
    response = service.Embed(request, mock_context)
    assert response.image.data is not None, "Image data should be populated after reading from URI."
    assert image_data != response.image.data, "Image should be modified after URI read and watermarking."
