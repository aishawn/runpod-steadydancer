# Dockerfile for SteadyDancer-GGUF (Minimal version)
# Optimized for running MCG-NJU/SteadyDancer-GGUF model in ComfyUI
FROM wlsdml1114/multitalk-base:1.7 as runtime

# Install basic dependencies
RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client

# Install dependencies for hfd.sh and entrypoint.sh (used to download models and check ComfyUI)
RUN apt-get update && apt-get install -y curl aria2 wget && rm -rf /var/lib/apt/lists/*

# Copy and setup hfd.sh
COPY hfd.sh /usr/local/bin/hfd.sh
RUN chmod +x /usr/local/bin/hfd.sh

WORKDIR /

# Install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd /ComfyUI && \
    pip install -r requirements.txt

# Install required custom nodes for SteadyDancer-GGUF
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/city96/ComfyUI-GGUF && \
    cd ComfyUI-GGUF && \
    pip install -r requirements.txt

RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    cd ComfyUI-WanVideoWrapper && \
    pip install -r requirements.txt

# Required for workflow nodes (ImageResizeKJv2, GetImageSizeAndCount, etc.)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-KJNodes && \
    cd ComfyUI-KJNodes && \
    pip install -r requirements.txt

# Required for video processing (VHS_VideoCombine, VHS_LoadVideo)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite && \
    cd ComfyUI-VideoHelperSuite && \
    pip install -r requirements.txt

# Required for pose detection in SteadyDancer workflow (PoseDetectionOneToAllAnimation)
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess && \
    cd ComfyUI-WanAnimatePreprocess && \
    pip install -r requirements.txt

# Install ONNX Runtime GPU for pose detection models (ViTPose, YOLO)
# Required for running ONNX models with GPU acceleration
RUN pip install onnx onnxruntime-gpu

# Optional but recommended for memory optimization
RUN cd /ComfyUI/custom_nodes && \
    git clone https://github.com/orssorbit/ComfyUI-wanBlockswap

# Create model directories
RUN mkdir -p /ComfyUI/models/diffusion_models \
             /ComfyUI/models/clip_vision \
             /ComfyUI/models/text_encoders \
             /ComfyUI/models/vae \
             /ComfyUI/models/onnx \
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

# Download SteadyDancer-GGUF model (Q5_K_M version for best quality/size balance)
# Alternative versions: Q4_K_M (10.9GB), Q6_K (13.7GB)
# Model page: https://huggingface.co/MCG-NJU/SteadyDancer-GGUF
RUN hfd.sh MCG-NJU/SteadyDancer-GGUF \
      --include "Wan21_I2V_SteadyDancer_fp16-Q5_K_M_fix_5d_tensor.gguf" \
      --tool aria2c \
      -x 8 -j 8 \
      --local-dir /tmp/hfd_steadydancer && \
    mv /tmp/hfd_steadydancer/Wan21_I2V_SteadyDancer_fp16-Q5_K_M_fix_5d_tensor.gguf /ComfyUI/models/diffusion_models/ && \
    rm -rf /tmp/hfd_steadydancer

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

# Install project requirements if exists
# Most dependencies are already installed via custom nodes, but install any additional ones
RUN if [ -f "requirements.txt" ]; then \
        pip install -r requirements.txt; \
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
    ls -la /workflows/wanvideo_SteadyDancer_example_03.json 2>/dev/null || echo "WARNING: SteadyDancer workflow not found"

RUN chmod +x /entrypoint.sh

# 设置工作目录为根目录（handler.py 所在位置）
WORKDIR /

# Set environment variables
ENV SERVER_ADDRESS=127.0.0.1
ENV COMFYUI_PORT=8188

# Expose ComfyUI port (though RunPod handles this automatically)
EXPOSE 8188

CMD ["/entrypoint.sh"]
