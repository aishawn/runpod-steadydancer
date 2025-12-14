#!/bin/bash

# 不立即退出，允许错误处理
set +e

# 日志函数
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "=========================================="
log "SteadyDancer Container Startup"
log "=========================================="

# 检查必要文件
log "Checking required files..."
if [ ! -f "/ComfyUI/main.py" ]; then
    log "ERROR: ComfyUI main.py not found at /ComfyUI/main.py"
    exit 1
fi

if [ ! -f "handler.py" ]; then
    log "ERROR: handler.py not found in current directory: $(pwd)"
    log "Current directory contents:"
    ls -la
    exit 1
fi

log "Required files found ✓"

# 检查工作流文件
if [ ! -f "/workflows/wanvideo_SteadyDancer_example_03.json" ]; then
    log "WARNING: SteadyDancer workflow not found at /workflows/wanvideo_SteadyDancer_example_03.json"
    log "Checking workflows directory..."
    ls -la /workflows/ 2>/dev/null || log "Workflows directory does not exist"
fi

# 启动 ComfyUI 在后台
log "Starting ComfyUI in the background..."
cd /ComfyUI
python main.py --listen 0.0.0.0 --port 8188 --use-sage-attention > /tmp/comfyui.log 2>&1 &
COMFYUI_PID=$!
log "ComfyUI started with PID: $COMFYUI_PID"

# 等待 ComfyUI 就绪（增加等待时间，因为 SteadyDancer 需要加载很多模型）
log "Waiting for ComfyUI to be ready..."
max_wait=300  # 增加到5分钟（SteadyDancer 模型加载需要更长时间）
wait_count=0
comfyui_ready=0

while [ $wait_count -lt $max_wait ]; do
    # 检查进程是否还在运行
    if ! kill -0 $COMFYUI_PID 2>/dev/null; then
        log "ERROR: ComfyUI process died!"
        log "ComfyUI logs (last 50 lines):"
        tail -50 /tmp/comfyui.log
        exit 1
    fi
    
    # 检查 HTTP 连接
    if curl -s http://127.0.0.1:8188/ > /dev/null 2>&1; then
        log "ComfyUI is ready! (waited ${wait_count}s)"
        comfyui_ready=1
        break
    fi
    
    if [ $((wait_count % 30)) -eq 0 ]; then
        log "Waiting for ComfyUI... (${wait_count}/${max_wait}s)"
        # 每30秒显示一次日志
        if [ -f /tmp/comfyui.log ]; then
            log "Recent ComfyUI output:"
            tail -5 /tmp/comfyui.log | sed 's/^/  /'
        fi
    fi
    
    sleep 2
    wait_count=$((wait_count + 2))
done

if [ $comfyui_ready -eq 0 ]; then
    log "ERROR: ComfyUI failed to start within ${max_wait} seconds"
    log "ComfyUI logs:"
    cat /tmp/comfyui.log
    exit 1
fi

# 验证 ComfyUI API 可用
log "Verifying ComfyUI API..."
if curl -s http://127.0.0.1:8188/object_info > /dev/null 2>&1; then
    log "ComfyUI API is accessible ✓"
else
    log "WARNING: ComfyUI API may not be fully ready"
    log "Waiting additional 10 seconds for model loading..."
    sleep 10
fi

# 运行健康检查（如果存在）
if [ -f "health_check.py" ]; then
    log "Running health check..."
    python health_check.py || log "WARNING: Health check failed, but continuing..."
fi

# 返回工作目录
cd /

# 启动 handler（作为前台进程，这是容器的 main process）
log "=========================================="
log "Starting RunPod handler..."
log "=========================================="
log "Handler location: $(pwd)/handler.py"
log "Python version: $(python --version)"

# 检查 runpod 是否安装
if ! python -c "import runpod" 2>/dev/null; then
    log "ERROR: runpod module not found!"
    log "Installed packages:"
    pip list | grep -i runpod || log "  (runpod not found)"
    exit 1
fi

log "RunPod module found ✓"

# 启动 handler（使用 exec 替换当前进程）
log "Executing handler.py..."
exec python handler.py