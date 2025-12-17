# Dockerfile for SteadyDancer (Minimal version)
# Optimized for running SteadyDancer quanto int8 model in ComfyUI
#
# VERSION COMPATIBILITY NOTES:
# ============================
# If you encounter "got multiple values for keyword argument 'is_uncond'" errors,
# this indicates version incompatibility between ComfyUI and ComfyUI-WanVideoWrapper.
#
# To fix version conflicts:
# 1. Pin specific commits in git clone commands (e.g., git checkout <commit-hash>)
# 2. Ensure ComfyUI-WanVideoWrapper is compatible with the ComfyUI version
# 3. Update workflow JSON files to match the installed versions
# 4. Check version information printed during build for debugging
#
# Example of pinning versions:
#   git clone <repo> && cd <repo> && git checkout <commit-hash> && cd ..
#
FROM wlsdml1114/multitalk-base:1.7 as runtime

# Install basic dependencies
# Note: Using -U (upgrade) may cause version conflicts. Consider pinning versions if issues occur.
# IMPORTANT: Install NumPy < 2.0 first to prevent onnxruntime-gpu compatibility issues
# This must be done before any other packages that might install NumPy 2.x
RUN pip install "numpy<2.0"
RUN pip install "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client

# Install dependencies for hfd.sh and entrypoint.sh (used to download models and check ComfyUI)
RUN apt-get update && apt-get install -y curl aria2 wget && rm -rf /var/lib/apt/lists/*

# Copy and setup hfd.sh
COPY hfd.sh /usr/local/bin/hfd.sh
RUN chmod +x /usr/local/bin/hfd.sh

WORKDIR /

# Install ComfyUI with version control
# Note: Using latest stable version. If compatibility issues occur, 
# consider pinning to a specific commit: git checkout <commit-hash>
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && \
    # Record ComfyUI version for debugging
    echo "ComfyUI version: $(git rev-parse HEAD)" && \
    git rev-parse HEAD > /ComfyUI_VERSION.txt && \
    pip install -r requirements.txt

# Install required custom nodes for SteadyDancer
# ComfyUI-GGUF: Optional, for GGUF model loading (not used with quanto int8 model)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/city96/ComfyUI-GGUF && \
    cd ComfyUI-GGUF && \
    echo "ComfyUI-GGUF version: $(git rev-parse HEAD)" && \
    git rev-parse HEAD > /COMFYUI_GGUF_VERSION.txt && \
    pip install -r requirements.txt

# ComfyUI-WanVideoWrapper: CRITICAL - Version must be compatible with ComfyUI
# This is the most likely source of 'is_uncond' parameter conflicts
# If errors occur, try: git checkout <stable-commit-hash>
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    cd ComfyUI-WanVideoWrapper && \
    echo "ComfyUI-WanVideoWrapper version: $(git rev-parse HEAD)" && \
    git rev-parse HEAD > /COMFYUI_WANVIDEO_VERSION.txt && \
    pip install -r requirements.txt

# Required for workflow nodes (ImageResizeKJv2, GetImageSizeAndCount, etc.)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes && \
    cd ComfyUI-KJNodes && \
    echo "ComfyUI-KJNodes version: $(git rev-parse HEAD)" && \
    pip install -r requirements.txt

# Required for video processing (VHS_VideoCombine, VHS_LoadVideo)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite && \
    cd ComfyUI-VideoHelperSuite && \
    echo "ComfyUI-VideoHelperSuite version: $(git rev-parse HEAD)" && \
    pip install -r requirements.txt

# Required for pose detection in SteadyDancer workflow (PoseDetectionOneToAllAnimation)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess && \
    cd ComfyUI-WanAnimatePreprocess && \
    echo "ComfyUI-WanAnimatePreprocess version: $(git rev-parse HEAD)" && \
    pip install -r requirements.txt

# Install ONNX Runtime GPU for pose detection models (ViTPose, YOLO)
# Required for running ONNX models with GPU acceleration
# Pin versions to avoid compatibility issues
# Note: NumPy < 2.0 is already installed above, ensure it's not upgraded
RUN pip install onnx==1.16.0 onnxruntime-gpu==1.18.0 && \
    pip install --force-reinstall --no-deps "numpy<2.0" || true

# Optional but recommended for memory optimization
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap && \
    cd ComfyUI-wanBlockswap && \
    echo "ComfyUI-wanBlockswap version: $(git rev-parse HEAD)" && \
    if [ -f "requirements.txt" ]; then pip install -r requirements.txt; fi

# Create model directories
RUN mkdir -p /ComfyUI/models/diffusion_models \
             /ComfyUI/models/clip_vision \
             /ComfyUI/models/text_encoders \
             /ComfyUI/models/vae \
             /ComfyUI/models/onnx \
             /ComfyUI/models/detection \
             /ComfyUI/models/loras \
             /ComfyUI/input \
             /ComfyUI/output \
             /ComfyUI/temp

# Download required models (T5, VAE, CLIP Vision)
RUN hfd.sh Comfy-Org/Wan_2.1_ComfyUI_repackaged \
      --include "split_files/clip_vision/clip_vision_h.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wan21 && \
    mv /tmp/hfd_wan21/split_files/clip_vision/clip_vision_h.safetensors /ComfyUI/models/clip_vision/ && \
    rm -rf /tmp/hfd_wan21

RUN hfd.sh Kijai/WanVideo_comfy \
      --include "umt5-xxl-enc-bf16.safetensors" \
      --include "Wan2_1_VAE_bf16.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_wanvideo && \
    mv /tmp/hfd_wanvideo/umt5-xxl-enc-bf16.safetensors /ComfyUI/models/text_encoders/ && \
    mv /tmp/hfd_wanvideo/Wan2_1_VAE_bf16.safetensors /ComfyUI/models/vae/ && \
    # 创建 wanvideo 子目录并创建符号链接，以支持 workflow 中的 "wanvideo/Wan2_1_VAE_bf16.safetensors" 路径
    mkdir -p /ComfyUI/models/vae/wanvideo && \
    ln -sf /ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors /ComfyUI/models/vae/wanvideo/Wan2_1_VAE_bf16.safetensors && \
    rm -rf /tmp/hfd_wanvideo

# Download SteadyDancer main model (quanto int8)
RUN mkdir -p /workspace/ckpts && \
    hfd.sh DeepBeepMeep/Wan2.1 \
      --include "wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_steadydancer && \
    mv /tmp/hfd_steadydancer/wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors /workspace/ckpts/ && \
    rm -rf /tmp/hfd_steadydancer && \
    # 创建符号链接到 ComfyUI 模型目录，以支持 workflow 中的路径
    mkdir -p /ComfyUI/models/diffusion_models/WanVideo/SteadyDancer && \
    ln -sf /workspace/ckpts/wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors /ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors && \
    echo "✓ SteadyDancer quanto int8 model downloaded"

# Download pose detection models (ViTPose and YOLO) for SteadyDancer workflow
# ViTPose Huge model (needs both files)
RUN hfd.sh Kijai/vitpose_comfy \
      --include "onnx/vitpose_h_wholebody_model.onnx" \
      --include "onnx/vitpose_h_wholebody_data.bin" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_vitpose && \
    mv /tmp/hfd_vitpose/onnx/vitpose_h_wholebody_model.onnx /ComfyUI/models/onnx/ && \
    mv /tmp/hfd_vitpose/onnx/vitpose_h_wholebody_data.bin /ComfyUI/models/onnx/ && \
    rm -rf /tmp/hfd_vitpose

# YOLOv10m model for person detection
RUN hfd.sh Wan-AI/Wan2.2-Animate-14B \
      --include "process_checkpoint/det/yolov10m.onnx" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_yolo && \
    mv /tmp/hfd_yolo/process_checkpoint/det/yolov10m.onnx /ComfyUI/models/onnx/ && \
    rm -rf /tmp/hfd_yolo

# Create detection directory with symlinks to onnx models for ComfyUI compatibility
RUN mkdir -p /ComfyUI/models/detection && \
    if [ -d /ComfyUI/models/onnx ]; then \
        for file in /ComfyUI/models/onnx/*.onnx /ComfyUI/models/onnx/*.bin; do \
            if [ -f "$file" ]; then \
                ln -sf "$file" "/ComfyUI/models/detection/$(basename "$file")"; \
            fi; \
        done 2>/dev/null || true; \
    fi && \
    echo "✓ Detection directory symlinks created" && \
    ls -la /ComfyUI/models/detection/ 2>/dev/null || echo "WARNING: Detection directory is empty"

# Download LoRA model for SteadyDancer workflow
# LoRA model: lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
# Note: loras directory is already created above
RUN mkdir -p /ComfyUI/models/loras/WanVideo/Lightx2v && \
    hfd.sh Kijai/WanVideo_comfy \
      --include "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_lora && \
    mv /tmp/hfd_lora/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors /ComfyUI/models/loras/WanVideo/Lightx2v/ && \
    rm -rf /tmp/hfd_lora && \
    # 验证LoRA模型文件已下载
    ls -lh /ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors && \
    echo "✓ LoRA model downloaded successfully"

# Install project requirements if exists
# Most dependencies are already installed via custom nodes, but install any additional ones
# Ensure NumPy < 2.0 is maintained after installing project requirements
RUN if [ -f "requirements.txt" ]; then \
        pip install -r requirements.txt && \
        pip install --force-reinstall --no-deps "numpy<2.0" || true; \
    fi

# Copy project files
COPY . .
COPY extra_model_paths.yaml /ComfyUI/extra_model_paths.yaml

# Ensure workflows directory exists and is accessible
RUN mkdir -p /workflows && \
    if [ -d "workflows" ]; then \
        cp -r workflows/* /workflows/ 2>/dev/null || true; \
    fi && \
    # 验证关键文件存在
    echo "Verifying key files..." && \
    ls -la /entrypoint.sh && \
    ls -la handler.py && \
    ls -la /workflows/wanvideo_SteadyDancer_example_03.json 2>/dev/null || echo "WARNING: SteadyDancer workflow not found" && \
    # 验证 extra_model_paths.yaml 文件格式
    echo "Verifying extra_model_paths.yaml..." && \
    python -c "import yaml; f=open('/ComfyUI/extra_model_paths.yaml'); data=yaml.safe_load(f); f.close(); assert isinstance(data, dict), f'YAML must be a dict, got {type(data)}'; assert 'comfyui' in data, 'YAML must contain comfyui key'; print('✓ extra_model_paths.yaml format is valid')" || (echo "ERROR: extra_model_paths.yaml format is invalid" && cat /ComfyUI/extra_model_paths.yaml && exit 1) && \
    # 验证所有必需的模型文件已下载
    echo "Verifying model files..." && \
    test -f /ComfyUI/models/clip_vision/clip_vision_h.safetensors && echo "✓ CLIP Vision model found" || (echo "ERROR: CLIP Vision model not found" && exit 1) && \
    test -f /ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors && echo "✓ Text encoder model found" || (echo "ERROR: Text encoder model not found" && exit 1) && \
    test -f /ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors && echo "✓ VAE model found" || (echo "ERROR: VAE model not found" && exit 1) && \
    test -f /ComfyUI/models/onnx/vitpose_h_wholebody_model.onnx && echo "✓ ViTPose model found" || (echo "ERROR: ViTPose model not found" && exit 1) && \
    test -f /ComfyUI/models/onnx/vitpose_h_wholebody_data.bin && echo "✓ ViTPose data file found" || (echo "ERROR: ViTPose data file not found" && exit 1) && \
    test -f /ComfyUI/models/onnx/yolov10m.onnx && echo "✓ YOLO model found" || (echo "ERROR: YOLO model not found" && exit 1) && \
    # 验证 detection 目录的符号链接
    test -L /ComfyUI/models/detection/vitpose_h_wholebody_model.onnx && echo "✓ ViTPose symlink in detection directory" || echo "WARNING: ViTPose symlink not found in detection directory" && \
    test -L /ComfyUI/models/detection/yolov10m.onnx && echo "✓ YOLO symlink in detection directory" || echo "WARNING: YOLO symlink not found in detection directory" && \
    test -f /ComfyUI/models/loras/WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors && echo "✓ LoRA model found" || (echo "ERROR: LoRA model not found" && exit 1) && \
    # 验证 SteadyDancer quanto int8 模型
    test -f /workspace/ckpts/wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors && echo "✓ SteadyDancer quanto int8 model found" || (echo "ERROR: SteadyDancer quanto int8 model not found" && exit 1) && \
    test -L /ComfyUI/models/diffusion_models/WanVideo/SteadyDancer/wan2.1_steadydancer_14B_quanto_mbf16_int8.safetensors && echo "✓ SteadyDancer model symlink created" || echo "WARNING: SteadyDancer model symlink not found" && \
    echo "✓ All required model files verified" && \
    # 输出版本信息用于调试版本兼容性问题
    echo "" && \
    echo "========================================" && \
    echo "Version Information (for debugging):" && \
    echo "========================================" && \
    (cd /ComfyUI && echo "ComfyUI: $(git rev-parse HEAD) ($(git log -1 --format=%ci))") && \
    (cd /ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper 2>/dev/null && echo "ComfyUI-WanVideoWrapper: $(git rev-parse HEAD) ($(git log -1 --format=%ci))") || echo "ComfyUI-WanVideoWrapper: Not found" && \
    (cd /ComfyUI/custom_nodes/ComfyUI-GGUF 2>/dev/null && echo "ComfyUI-GGUF: $(git rev-parse HEAD)") || echo "ComfyUI-GGUF: Not found" && \
    (cd /ComfyUI/custom_nodes/ComfyUI-WanAnimatePreprocess 2>/dev/null && echo "ComfyUI-WanAnimatePreprocess: $(git rev-parse HEAD)") || echo "ComfyUI-WanAnimatePreprocess: Not found" && \
    (python -c "import onnx; import onnxruntime; print(f'ONNX: {onnx.__version__}'); print(f'ONNXRuntime-GPU: {onnxruntime.__version__}')" || echo "WARNING: Failed to import onnxruntime (NumPy compatibility issue, but should work at runtime)") && \
    echo "========================================" && \
    echo "If you encounter 'is_uncond' parameter conflicts:" && \
    echo "1. Check if ComfyUI-WanVideoWrapper version is compatible" && \
    echo "2. Consider pinning to specific commits in Dockerfile" && \
    echo "3. Update workflow JSON file to match current versions" && \
    echo "========================================"

RUN chmod +x /entrypoint.sh

# 设置工作目录为根目录（handler.py 所在位置）
WORKDIR /

# Set environment variables
ENV SERVER_ADDRESS=127.0.0.1
ENV COMFYUI_PORT=8188

# Expose ComfyUI port (though RunPod handles this automatically)
EXPOSE 8188

CMD ["/entrypoint.sh"]
