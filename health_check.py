#!/usr/bin/env python3
"""
健康检查脚本：验证 ComfyUI 和 handler 是否正常工作
"""
import sys
import urllib.request
import json
import time

def check_comfyui():
    """检查 ComfyUI 是否运行"""
    try:
        url = "http://127.0.0.1:8188/"
        response = urllib.request.urlopen(url, timeout=5)
        if response.status == 200:
            print("✓ ComfyUI HTTP 服务正常")
            return True
    except Exception as e:
        print(f"✗ ComfyUI HTTP 服务不可用: {e}")
        return False

def check_comfyui_api():
    """检查 ComfyUI API 是否可用"""
    try:
        url = "http://127.0.0.1:8188/object_info"
        response = urllib.request.urlopen(url, timeout=5)
        data = json.loads(response.read())
        if "WanVideoModelLoader" in data or "CheckpointLoaderSimple" in data:
            print("✓ ComfyUI API 正常")
            return True
        else:
            print("⚠ ComfyUI API 返回数据异常")
            return False
    except Exception as e:
        print(f"✗ ComfyUI API 不可用: {e}")
        return False

def check_workflow():
    """检查工作流文件是否存在"""
    import os
    workflow_path = "/workflows/wanvideo_SteadyDancer_example_03.json"
    if os.path.exists(workflow_path):
        print(f"✓ 工作流文件存在: {workflow_path}")
        return True
    else:
        print(f"✗ 工作流文件不存在: {workflow_path}")
        return False

def check_models():
    """检查关键模型文件是否存在"""
    import os
    models = [
        "/ComfyUI/models/diffusion_models/Wan21_I2V_SteadyDancer_fp16-Q5_K_M_fix_5d_tensor.gguf",
        "/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors",
        "/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors",
        "/ComfyUI/models/clip_vision/clip_vision_h.safetensors",
        "/ComfyUI/models/onnx/vitpose_h_wholebody_model.onnx",
        "/ComfyUI/models/onnx/yolov10m.onnx"
    ]
    
    all_exist = True
    for model in models:
        if os.path.exists(model):
            size_mb = os.path.getsize(model) / (1024 * 1024)
            print(f"✓ {os.path.basename(model)} ({size_mb:.1f} MB)")
        else:
            print(f"✗ {os.path.basename(model)} 不存在")
            all_exist = False
    
    return all_exist

if __name__ == "__main__":
    print("=" * 60)
    print("SteadyDancer 健康检查")
    print("=" * 60)
    
    results = []
    results.append(("ComfyUI HTTP", check_comfyui()))
    time.sleep(1)
    results.append(("ComfyUI API", check_comfyui_api()))
    results.append(("工作流文件", check_workflow()))
    results.append(("模型文件", check_models()))
    
    print("=" * 60)
    print("检查结果:")
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n✓ 所有检查通过！")
        sys.exit(0)
    else:
        print("\n✗ 部分检查失败，请查看上述错误信息")
        sys.exit(1)




