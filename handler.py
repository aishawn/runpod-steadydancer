import runpod
from runpod.serverless.utils import rp_upload
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request as urllib_request
import urllib.parse as urllib_parse
import urllib.error as urllib_error
import binascii # Base64 에러 처리를 위해 import
import subprocess
import time
import shutil
# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())
def to_nearest_multiple_of_16(value):
    """주어진 값을 가장 가까운 16의 배수로 보정, 최소 16 보장"""
    try:
        numeric_value = float(value)
    except Exception:
        raise Exception(f"width/height 값이 숫자가 아닙니다: {value}")
    adjusted = int(round(numeric_value / 16.0) * 16)
    if adjusted < 16:
        adjusted = 16
    return adjusted
def process_input(input_data, temp_dir, output_filename, input_type):
    """입력 데이터를 처리하여 파일 경로를 반환하는 함수"""
    if input_type == "path":
        # 경로인 경우 그대로 반환
        logger.info(f"📁 경로 입력 처리: {input_data}")
        return input_data
    elif input_type == "url":
        # URL인 경우 다운로드
        logger.info(f"🌐 URL 입력 처리: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        # Base64인 경우 디코딩하여 저장
        logger.info(f"🔢 Base64 입력 처리")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"지원하지 않는 입력 타입: {input_type}")

        
def download_file_from_url(url, output_path):
    """URL에서 파일을 다운로드하는 함수"""
    try:
        # wget을 사용하여 파일 다운로드
        result = subprocess.run([
            'wget', '-O', output_path, '--no-verbose', url
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ URL에서 파일을 성공적으로 다운로드했습니다: {url} -> {output_path}")
            return output_path
        else:
            logger.error(f"❌ wget 다운로드 실패: {result.stderr}")
            raise Exception(f"URL 다운로드 실패: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ 다운로드 시간 초과")
        raise Exception("다운로드 시간 초과")
    except Exception as e:
        logger.error(f"❌ 다운로드 중 오류 발생: {e}")
        raise Exception(f"다운로드 중 오류 발생: {e}")


def save_base64_to_file(base64_data, temp_dir, output_filename):
    """Base64 데이터를 파일로 저장하는 함수"""
    try:
        # Base64 문자열 디코딩
        decoded_data = base64.b64decode(base64_data)
        
        # 디렉토리가 존재하지 않으면 생성
        os.makedirs(temp_dir, exist_ok=True)
        
        # 파일로 저장
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
        
        logger.info(f"✅ Base64 입력을 '{file_path}' 파일로 저장했습니다.")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64 디코딩 실패: {e}")
        raise Exception(f"Base64 디코딩 실패: {e}")
    
def queue_prompt(prompt, is_mega_model=False):
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    if is_mega_model:
        # RapidAIO Mega (V2.5).json 验证
        if "597" in prompt and "widgets_values" in prompt["597"]:
            image_path_check = prompt["597"]["widgets_values"][0] if prompt["597"]["widgets_values"] else None
            logger.info(f"  节点597的image = {image_path_check}")
        if "591" in prompt and "widgets_values" in prompt["591"]:
            prompts_check = prompt["591"]["widgets_values"][0] if prompt["591"]["widgets_values"] else None
            logger.info(f"  节点591的Multi_prompts = {prompts_check[:100] if prompts_check and len(prompts_check) > 100 else prompts_check}...")
        if "572" in prompt and "widgets_values" in prompt["572"]:
            widgets = prompt["572"]["widgets_values"]
            logger.info(f"  节点572的strength = {widgets[3] if len(widgets) > 3 else 'N/A'} (I2V mode)")
    else:
        # 标准 workflow 验证
        if "541" in prompt and "inputs" in prompt["541"]:
            fun_or_fl2v = prompt["541"]["inputs"].get("fun_or_fl2v_model")
            logger.info(f"  节点541的fun_or_fl2v_model = {fun_or_fl2v} (类型: {type(fun_or_fl2v).__name__})")
        if "244" in prompt and "inputs" in prompt["244"]:
            image_path_check = prompt["244"]["inputs"].get("image")
            logger.info(f"  节点244的image = {image_path_check}")
    
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib_request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        response = urllib_request.urlopen(req)
        return json.loads(response.read())
    except urllib_error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"HTTP Error {e.code}: {e.reason}")
        logger.error(f"Error response: {error_body}")
        try:
            error_json = json.loads(error_body)
            logger.error(f"Error details: {json.dumps(error_json, indent=2)}")
        except:
            pass
        raise Exception(f"ComfyUI API 错误 ({e.code}): {error_body}")

def get_image(filename, subfolder, folder_type):
    url = f"http://{server_address}:8188/view"
    logger.info(f"Getting image from: {url}")
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib_parse.urlencode(data)
    with urllib_request.urlopen(f"{url}?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    logger.info(f"Getting history from: {url}")
    with urllib_request.urlopen(url) as response:
        return json.loads(response.read())

def get_videos(ws, prompt, is_mega_model=False):
    prompt_id = queue_prompt(prompt, is_mega_model)['prompt_id']
    output_videos = {}
    error_info = None
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
            elif message['type'] == 'execution_error':
                # 捕获执行错误
                error_data = message.get('data', {})
                error_info = error_data.get('error', 'Unknown execution error')
                error_type = error_data.get('type', '')
                node_id = error_data.get('node_id', '')
                
                # 检查是否是 OOM 错误
                if 'OutOfMemoryError' in str(error_info) or 'OOM' in str(error_info):
                    logger.error(f"❌ GPU 内存不足 (OOM) 错误 - 节点: {node_id}, 类型: {error_type}")
                    logger.error(f"错误详情: {error_info}")
                    logger.error("建议: 1) 减小图像分辨率 (width/height) 2) 减少帧数 (length) 3) 缩短提示词长度")
                else:
                    logger.error(f"Execution error received - 节点: {node_id}, 类型: {error_type}, 错误: {error_info}")
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    
    # 检查是否有错误信息
    if 'error' in history:
        error_info = history['error']
        if isinstance(error_info, dict):
            error_info = error_info.get('message', str(error_info))
        
        # 检查是否是 OOM 错误
        error_str = str(error_info)
        if 'OutOfMemoryError' in error_str or 'OOM' in error_str or 'allocation' in error_str.lower():
            logger.error(f"❌ GPU 内存不足 (OOM) 错误")
            logger.error(f"错误详情: {error_info}")
            logger.error("建议解决方案:")
            logger.error("  1. 减小图像分辨率 (width/height) - 当前值可能过大")
            logger.error("  2. 减少视频帧数 (length) - 当前值可能过大")
            logger.error("  3. 缩短提示词长度 - 过长的提示词会消耗更多内存")
            logger.error("  4. 降低 batch_size (如果可配置)")
            raise Exception(f"GPU 内存不足 (OOM): {error_info}. 请尝试减小分辨率、帧数或提示词长度。")
        else:
            logger.error(f"Error in history: {error_info}")
            raise Exception(f"ComfyUI execution error: {error_info}")
    
    # 检查 outputs 是否存在
    if 'outputs' not in history:
        if error_info:
            raise Exception(f"ComfyUI execution error: {error_info}")
        raise Exception("No outputs found in execution history")
    
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        # 支持多种视频输出格式：gifs (标准 workflow) 和 videos (VHS_VideoCombine)
        video_list = None
        if 'gifs' in node_output:
            video_list = node_output['gifs']
        elif 'videos' in node_output:
            video_list = node_output['videos']
        
        if video_list:
            for video in video_list:
                # fullpath를 이용하여 직접 파일을 읽고 base64로 인코딩
                if 'fullpath' in video:
                    with open(video['fullpath'], 'rb') as f:
                        video_data = base64.b64encode(f.read()).decode('utf-8')
                    videos_output.append(video_data)
                elif 'filename' in video:
                    # 如果没有 fullpath，尝试使用 filename 和 subfolder
                    subfolder = video.get('subfolder', '')
                    folder_type = video.get('type', 'output')
                    filename = video['filename']
                    try:
                        video_bytes = get_image(filename, subfolder, folder_type)
                        video_data = base64.b64encode(video_bytes).decode('utf-8')
                        videos_output.append(video_data)
                    except Exception as e:
                        logger.warning(f"无法读取视频文件 {filename}: {e}")
        output_videos[node_id] = videos_output

    return output_videos

def get_available_models():
    """获取 ComfyUI 中可用的模型列表"""
    try:
        url = f"http://{server_address}:8188/object_info"
        with urllib_request.urlopen(url, timeout=5) as response:
            object_info = json.loads(response.read())
            models = []
            
            # 首先尝试 WanVideoModelLoader（用于标准 workflow）
            if "WanVideoModelLoader" in object_info:
                loader_info = object_info["WanVideoModelLoader"]
                # 尝试不同的返回格式
                if "model" in loader_info:
                    wan_models = loader_info["model"]
                elif "input" in loader_info and "required" in loader_info["input"]:
                    if "model" in loader_info["input"]["required"]:
                        wan_models = loader_info["input"]["required"]["model"]
                    else:
                        wan_models = []
                else:
                    wan_models = []
                
                # 处理嵌套列表的情况
                if wan_models and isinstance(wan_models, list) and len(wan_models) > 0:
                    if isinstance(wan_models[0], list):
                        wan_models = wan_models[0]
                    wan_models = [m for m in wan_models if isinstance(m, str)]
                    models.extend(wan_models)
            
            # 同时检查 CheckpointLoaderSimple（用于 RapidAIO Mega (V2.5).json）
            if "CheckpointLoaderSimple" in object_info:
                loader_info = object_info["CheckpointLoaderSimple"]
                checkpoint_models = []
                
                # 调试：打印 CheckpointLoaderSimple 的结构
                logger.debug(f"CheckpointLoaderSimple loader_info keys: {list(loader_info.keys())}")
                
                # 尝试多种方式获取模型列表
                if "input" in loader_info:
                    if "required" in loader_info["input"]:
                        if "ckpt_name" in loader_info["input"]["required"]:
                            checkpoint_models = loader_info["input"]["required"]["ckpt_name"]
                            logger.debug(f"CheckpointLoaderSimple ckpt_name from required: {checkpoint_models}")
                    # 也检查 optional
                    if "optional" in loader_info["input"]:
                        if "ckpt_name" in loader_info["input"]["optional"]:
                            optional_models = loader_info["input"]["optional"]["ckpt_name"]
                            logger.debug(f"CheckpointLoaderSimple ckpt_name from optional: {optional_models}")
                
                # 直接检查是否有 ckpt_name 字段
                if "ckpt_name" in loader_info:
                    checkpoint_models = loader_info["ckpt_name"]
                    logger.debug(f"CheckpointLoaderSimple ckpt_name direct: {checkpoint_models}")
                
                # 处理嵌套列表的情况
                if checkpoint_models and isinstance(checkpoint_models, list) and len(checkpoint_models) > 0:
                    if isinstance(checkpoint_models[0], list):
                        checkpoint_models = checkpoint_models[0]
                    checkpoint_models = [m for m in checkpoint_models if isinstance(m, str)]
                    models.extend(checkpoint_models)
                    logger.info(f"CheckpointLoaderSimple 找到 {len(checkpoint_models)} 个模型: {checkpoint_models}")
                else:
                    logger.warning(f"CheckpointLoaderSimple 模型列表为空，可能模型不在标准路径中")
            
            # 去重
            models = list(set(models))
            
            if models:
                logger.info(f"可用模型列表: {models}")
            return models if models else []
    except Exception as e:
        logger.warning(f"获取可用模型列表失败: {e}")
        return []

def update_model_in_prompt(prompt, node_id, available_models):
    """更新 prompt 中指定节点的模型名称，如果模型不存在则使用第一个可用模型"""
    if node_id not in prompt:
        return False
    
    node = prompt[node_id]
    if "inputs" not in node or "model" not in node["inputs"]:
        return False
    
    current_model = node["inputs"]["model"]
    logger.info(f"节点 {node_id} 配置文件中的模型: {current_model}")
    
    # 如果当前模型在可用列表中，不需要更新
    if current_model in available_models:
        logger.info(f"节点 {node_id} 使用配置文件中的模型: {current_model}")
        return False
    
    # 优先选择 I2V 相关的模型（包含 I2V 关键字）
    i2v_models = [m for m in available_models if "I2V" in m.upper() or "i2v" in m.lower()]
    if i2v_models:
        new_model = i2v_models[0]
        logger.info(f"节点 {node_id} 模型更新: {current_model} -> {new_model} (配置文件中的模型不在可用列表中，已自动替换为 I2V 模型)")
        node["inputs"]["model"] = new_model
        return True
    
    # 如果没有 I2V 模型，使用第一个可用模型
    if available_models:
        new_model = available_models[0]
        logger.info(f"节点 {node_id} 模型更新: {current_model} -> {new_model} (配置文件中的模型不在可用列表中，已自动替换为第一个可用模型)")
        node["inputs"]["model"] = new_model
        return True
    
    return False

def load_workflow(workflow_path):
    """加载并验证工作流JSON文件"""
    if not os.path.exists(workflow_path):
        raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
    
    file_size = os.path.getsize(workflow_path)
    logger.info(f"加载工作流文件: {workflow_path} (大小: {file_size} 字节)")
    
    if file_size == 0:
        raise ValueError(f"工作流文件为空: {workflow_path}")
    
    try:
        with open(workflow_path, 'r', encoding='utf-8') as file:
            content = file.read()
            # 检查文件内容是否看起来像JSON（以{或[开头）
            content_stripped = content.strip()
            if not content_stripped.startswith(('{', '[')):
                # 显示前500个字符以便调试
                preview = content[:500] if len(content) > 500 else content
                logger.error(f"文件内容不是有效的JSON格式。前500字符: {preview}")
                raise ValueError(f"工作流文件不是有效的JSON格式: {workflow_path}")
            
            return json.loads(content)
    except json.JSONDecodeError as e:
        # 显示错误位置附近的内容
        with open(workflow_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            error_line = e.lineno - 1 if e.lineno > 0 else 0
            start_line = max(0, error_line - 2)
            end_line = min(len(lines), error_line + 3)
            context = ''.join(lines[start_line:end_line])
            logger.error(f"JSON解析错误 (行 {e.lineno}, 列 {e.colno}):\n{context}")
        raise ValueError(f"工作流文件JSON格式错误: {workflow_path} - {str(e)}")
    except Exception as e:
        logger.error(f"加载工作流文件时发生错误: {workflow_path} - {str(e)}")
        raise

def ensure_model_in_checkpoints(model_name):
    """确保模型文件在 checkpoints 目录中，如果不在则创建符号链接"""
    model_name = os.path.basename(model_name)  # 只取文件名
    
    # 可能的模型路径
    possible_paths = [
        "/ComfyUI/models/diffusion_models/" + model_name,
        "/workspace/models/" + model_name,
        "/ComfyUI/models/checkpoints/" + model_name,
    ]
    
    # 目标路径
    target_path = "/ComfyUI/models/checkpoints/" + model_name
    target_dir = "/ComfyUI/models/checkpoints"
    
    # 如果目标文件已存在，检查是否是有效的符号链接或文件
    if os.path.exists(target_path):
        # 检查是否是符号链接
        if os.path.islink(target_path):
            link_target = os.readlink(target_path)
            if os.path.exists(link_target):
                logger.info(f"模型文件符号链接已存在: {target_path} -> {link_target}")
                return True
            else:
                logger.warning(f"符号链接目标不存在，将重新创建: {link_target}")
                os.remove(target_path)
        elif os.path.isfile(target_path):
            logger.info(f"模型文件已存在于 checkpoints 目录: {target_path}")
            return True
    
    # 确保目标目录存在
    os.makedirs(target_dir, exist_ok=True)
    
    # 查找模型文件
    source_path = None
    for path in possible_paths:
        if os.path.exists(path):
            source_path = path
            logger.info(f"找到模型文件: {source_path}")
            break
    
    if source_path:
        try:
            # 创建符号链接
            if os.path.exists(target_path):
                os.remove(target_path)  # 如果已存在，先删除
            os.symlink(source_path, target_path)
            logger.info(f"已创建符号链接: {target_path} -> {source_path}")
            
            # 等待一小段时间，让文件系统同步
            time.sleep(0.5)
            
            # 验证符号链接是否创建成功
            if os.path.exists(target_path) and os.path.islink(target_path):
                logger.info(f"符号链接验证成功: {target_path}")
                return True
            else:
                logger.warning(f"符号链接创建后验证失败，尝试复制文件")
                # 如果符号链接验证失败，尝试复制文件
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.copy2(source_path, target_path)
                logger.info(f"已复制模型文件: {source_path} -> {target_path}")
                return True
        except Exception as e:
            logger.warning(f"创建符号链接失败: {e}，尝试复制文件")
            try:
                # 如果符号链接失败，尝试复制文件
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.copy2(source_path, target_path)
                logger.info(f"已复制模型文件: {source_path} -> {target_path}")
                return True
            except Exception as e2:
                logger.error(f"复制模型文件也失败: {e2}")
                return False
    else:
        logger.warning(f"未找到模型文件: {model_name}，在以下路径中查找: {possible_paths}")
        return False

def handler(job):
    """
    处理视频生成任务
    
    支持多提示词模式生成更长视频（基于 Hugging Face 讨论）:
    - 提示词可以是字符串（用换行符分隔）或数组
    - 每个提示词生成一个 batch，最终拼接成完整视频
    - 对于 MEGA 模型：使用最后 12 帧作为下一个 batch 的指导，保持角色一致性
    - 总视频长度 = length (每个 batch 的帧数) × 提示词数量
    - 例如：length=81 (约5秒), 4个提示词 = 约20秒视频
    
    参考: https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne/discussions/100
    """
    job_input = job.get("input", {})

    # 记录job_input，但排除base64数据以避免日志过长
    log_input = {k: v for k, v in job_input.items() if k not in ["image_base64", "end_image_base64"]}
    if "image_base64" in job_input:
        log_input["image_base64"] = f"<base64 data, length: {len(job_input['image_base64'])}>"
    if "end_image_base64" in job_input:
        log_input["end_image_base64"] = f"<base64 data, length: {len(job_input['end_image_base64'])}>"
    logger.info(f"Received job input: {log_input}")
    task_id = f"task_{uuid.uuid4()}"

    # 이미지 입력 처리 (image_path, image_url, image_base64 중 하나만 사용)
    image_path = None
    if "image_path" in job_input:
        image_path = process_input(job_input["image_path"], task_id, "input_image.jpg", "path")
    elif "image_url" in job_input:
        image_path = process_input(job_input["image_url"], task_id, "input_image.jpg", "url")
    elif "image_base64" in job_input:
        image_path = process_input(job_input["image_base64"], task_id, "input_image.jpg", "base64")
    else:
        # 기본값 사용
        image_path = "/example_image.png"
        logger.info("기본 이미지 파일을 사용합니다: /example_image.png")

    # 엔드 이미지 입력 처리 (end_image_path, end_image_url, end_image_base64 중 하나만 사용)
    end_image_path_local = None
    if "end_image_path" in job_input:
        end_image_path_local = process_input(job_input["end_image_path"], task_id, "end_image.jpg", "path")
    elif "end_image_url" in job_input:
        end_image_path_local = process_input(job_input["end_image_url"], task_id, "end_image.jpg", "url")
    elif "end_image_base64" in job_input:
        end_image_path_local = process_input(job_input["end_image_base64"], task_id, "end_image.jpg", "base64")
    
    # LoRA 설정 확인 - 배열로 받아서 처리
    lora_pairs = job_input.get("lora_pairs", [])
    
    # 최대 4개 LoRA까지 지원
    lora_count = min(len(lora_pairs), 4)
    if lora_count > len(lora_pairs):
        logger.warning(f"LoRA 개수가 {len(lora_pairs)}개입니다. 최대 4개까지만 지원됩니다. 처음 4개만 사용합니다.")
        lora_pairs = lora_pairs[:4]
    
    # 首先，确保 MEGA/AIO 模型文件在 checkpoints 目录中（如果存在）
    # 这样 CheckpointLoaderSimple 就能找到模型
    mega_model_name = "wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors"
    if os.path.exists(f"/ComfyUI/models/diffusion_models/{mega_model_name}"):
        logger.info(f"检测到 MEGA/AIO 模型文件，确保其在 checkpoints 目录中")
        if ensure_model_in_checkpoints(mega_model_name):
            # 等待 ComfyUI 重新扫描模型目录（如果它支持动态扫描）
            # 注意：ComfyUI 通常在启动时扫描，但我们可以等待一下
            logger.info("等待 ComfyUI 识别新添加的模型文件...")
            time.sleep(2)  # 等待 2 秒让 ComfyUI 有机会重新扫描
    
    # 获取可用模型列表，用于检测 MEGA/AIO 模型
    available_models = get_available_models()
    
    # 检测是否为 MEGA/AIO 模型（支持 I2V 和 T2V 的 all-in-one 模型）
    is_mega_model = False
    if available_models:
        for model_name in available_models:
            model_name_lower = model_name.lower()
            if "mega" in model_name_lower or "aio" in model_name_lower or "all-in-one" in model_name_lower or "allinone" in model_name_lower:
                is_mega_model = True
                mega_model_name = model_name
                logger.info(f"检测到 MEGA/AIO 模型: {model_name}, 将使用 Rapid-AIO-Mega workflow")
                
                # 再次确保模型文件在 checkpoints 目录中（用于 CheckpointLoaderSimple）
                ensure_model_in_checkpoints(model_name)
                break
    
    # 워크플로우 파일 선택
    # 检查是否使用 SteadyDancer workflow
    use_steadydancer = job_input.get("use_steadydancer", False)
    if use_steadydancer:
        workflow_file = "/workflows/wanvideo_SteadyDancer_example_03.json"
        logger.info(f"Using SteadyDancer workflow")
    elif is_mega_model:
        workflow_file = "/RapidAIO Mega (V2.5).json"
        logger.info(f"Using Rapid-AIO-Mega workflow for MEGA/AIO model")
    else:
        workflow_file = "/new_Wan22_flf2v_api.json" if end_image_path_local else "/new_Wan22_api.json"
        logger.info(f"Using {'FLF2V' if end_image_path_local else 'single'} workflow with {lora_count} LoRA pairs")
    
    workflow_data = load_workflow(workflow_file)
    
    # 提前获取 length 值，因为在转换 workflow 时可能会用到
    length = job_input.get("length", 81)
    
    # 转换 workflow 格式：如果使用 nodes 数组格式，转换为节点 ID key 格式
    # SteadyDancer workflow 和 MEGA workflow 都使用 nodes 数组格式
    if "nodes" in workflow_data:
        # RapidAIO Mega (V2.5).json 使用 nodes 数组格式，需要转换
        prompt = {}
        
        # 预先计算 comfyui-logic 节点的值（避免依赖插件）
        logic_node_values = {}
        if is_mega_model:
            # 节点592: Seconds/batch = length / 16
            logic_node_values["592"] = int(length / 16.0)
            # 节点593: Megapixel
            logic_node_values["593"] = job_input.get("megapixel", 0.5)
            # 节点585: Overlapping Frames
            # MEGA 模型推荐使用 1 帧重叠，且 VHS_DuplicateImages 节点要求 multiply_by >= 1
            logic_node_values["585"] = job_input.get("overlapping_frames", 1)
            logger.info(f"预计算 logic 节点值: 592={logic_node_values['592']}, 593={logic_node_values['593']}, 585={logic_node_values['585']}")
        
        # 首先建立 link_id 到 [node_id, output_index] 的映射
        # 同时建立 GetNode/SetNode 和 PrimitiveNode 的映射关系
        links_map = {}
        setnode_to_getnode_map = {}  # SetNode ID -> {name: value, ...}
        getnode_to_setnode_map = {}  # GetNode ID -> SetNode ID
        primitivenode_values = {}  # PrimitiveNode ID -> value (从 widgets_values 获取)
        skipped_node_ids = set()  # 记录被跳过的节点 ID
        
        # 第一遍：收集 SetNode 的值和 GetNode 的映射关系
        # 优化：分两次扫描，先扫描SetNode和PrimitiveNode，再扫描GetNode建立映射
        # 第一次扫描：收集SetNode和PrimitiveNode
        for node in workflow_data["nodes"]:
            node_id = str(node["id"])
            node_type = node.get("type", "")
            
            if node_type == "SetNode":
                # SetNode 存储值：从 inputs 获取值，从 title 或 widgets_values 获取名称
                setnode_name = node.get("title", "").replace("Set_", "")
                if not setnode_name and node.get("widgets_values"):
                    setnode_name = node["widgets_values"][0] if isinstance(node["widgets_values"], list) else ""
                
                # 从 inputs 获取实际值（如果有链接）
                setnode_value = None
                if "inputs" in node and isinstance(node["inputs"], list):
                    for input_item in node["inputs"]:
                        if isinstance(input_item, dict) and "link" in input_item and input_item["link"] is not None:
                            # SetNode 有输入链接，需要从源节点获取值
                            setnode_value = node_id  # 标记为需要从源节点获取
                            break
                
                if setnode_name:
                    if node_id not in setnode_to_getnode_map:
                        setnode_to_getnode_map[node_id] = {}
                    setnode_to_getnode_map[node_id][setnode_name] = setnode_value
                    logger.info(f"记录 SetNode {node_id} 存储的值: {setnode_name}")
            
            elif node_type == "PrimitiveNode":
                # PrimitiveNode 存储原始值：从 widgets_values 获取值
                if node.get("widgets_values") and isinstance(node["widgets_values"], list) and len(node["widgets_values"]) > 0:
                    primitivenode_values[node_id] = node["widgets_values"][0]
                    logger.info(f"记录 PrimitiveNode {node_id} 的值: {node['widgets_values'][0]}")
        
        # 第二次扫描：建立GetNode到SetNode的映射
        for node in workflow_data["nodes"]:
            node_id = str(node["id"])
            node_type = node.get("type", "")
            
            if node_type == "GetNode":
                # GetNode 获取值：从 widgets_values 获取名称
                getnode_name = node.get("title", "").replace("Get_", "")
                if not getnode_name and node.get("widgets_values"):
                    getnode_name = node["widgets_values"][0] if isinstance(node["widgets_values"], list) else ""
                
                # 查找对应的 SetNode（通过名称匹配）
                if getnode_name:
                    for setnode_id, setnode_values in setnode_to_getnode_map.items():
                        if getnode_name in setnode_values:
                            getnode_to_setnode_map[node_id] = setnode_id
                            logger.info(f"GetNode {node_id} ({getnode_name}) 映射到 SetNode {setnode_id}")
                            break
                    # 如果未找到对应的SetNode，记录警告
                    if node_id not in getnode_to_setnode_map:
                        logger.warning(f"GetNode {node_id} ({getnode_name}) 未找到对应的 SetNode，可能导致链接解析失败")
        
        # 建立 links_map，处理 GetNode/SetNode 的链接
        if "links" in workflow_data:
            for link in workflow_data["links"]:
                # link 格式: [link_id, source_node_id, source_output_index, target_node_id, target_input_index, type]
                if len(link) >= 6:
                    link_id = link[0]
                    source_node_id = str(link[1])
                    source_output_index = link[2]
                    target_node_id = str(link[3])
                    target_input_index = link[4]
                    
                    # 如果源节点是 PrimitiveNode，值会直接传递，不需要链接
                    if source_node_id in primitivenode_values:
                        # PrimitiveNode 的值会在处理节点输入时直接使用，这里标记为特殊值
                        links_map[link_id] = ["__PRIMITIVE__", primitivenode_values[source_node_id]]
                        logger.info(f"链接 {link_id}: PrimitiveNode {source_node_id} 的值 = {primitivenode_values[source_node_id]}")
                    # 如果源节点是 SetNode，找到 SetNode 的输入链接
                    elif source_node_id in setnode_to_getnode_map:
                        # SetNode 的输出链接，需要找到 SetNode 的输入源
                        for setnode in workflow_data["nodes"]:
                            if str(setnode["id"]) == source_node_id and "inputs" in setnode:
                                for input_item in setnode.get("inputs", []):
                                    if isinstance(input_item, dict) and "link" in input_item and input_item["link"] is not None:
                                        # 找到 SetNode 的源链接
                                        setnode_link_id = input_item["link"]
                                        # 查找这个链接的源节点
                                        for link_item in workflow_data.get("links", []):
                                            if len(link_item) >= 6 and link_item[0] == setnode_link_id:
                                                actual_source_id = str(link_item[1])
                                                actual_source_output = link_item[2]
                                                links_map[link_id] = [actual_source_id, actual_source_output]
                                                logger.info(f"链接 {link_id}: SetNode {source_node_id} -> 实际源节点 {actual_source_id}")
                                                break
                                        break
                                break
                    # 如果源节点是 GetNode，找到对应的 SetNode 的源
                    elif source_node_id in getnode_to_setnode_map:
                        setnode_id = getnode_to_setnode_map[source_node_id]
                        # 查找 SetNode 的输入链接
                        for setnode in workflow_data["nodes"]:
                            if str(setnode["id"]) == setnode_id and "inputs" in setnode:
                                for input_item in setnode.get("inputs", []):
                                    if isinstance(input_item, dict) and "link" in input_item and input_item["link"] is not None:
                                        # 找到 SetNode 的源链接
                                        setnode_link_id = input_item["link"]
                                        # 查找这个链接的源节点
                                        for link_item in workflow_data.get("links", []):
                                            if len(link_item) >= 6 and link_item[0] == setnode_link_id:
                                                actual_source_id = str(link_item[1])
                                                actual_source_output = link_item[2]
                                                links_map[link_id] = [actual_source_id, actual_source_output]
                                                logger.info(f"链接 {link_id}: GetNode {source_node_id} -> SetNode {setnode_id} -> 实际源节点 {actual_source_id}")
                                                break
                                        break
                                break
                    else:
                        # 正常链接
                        links_map[link_id] = [source_node_id, source_output_index]
        
        # 第二遍：转换节点，跳过不需要的节点
        for node in workflow_data["nodes"]:
            node_id = str(node["id"])
            
            # 跳过 comfyui-logic 节点（592, 593, 585），直接内联它们的值
            if node_id in logic_node_values:
                logger.info(f"跳过 logic 节点 {node_id}，将直接内联其值")
                skipped_node_ids.add(node_id)
                continue
            
            # 跳过 Note 和 MarkdownNote 节点（注释节点，ComfyUI API 不支持）
            node_type = node.get("type", "")
            if node_type == "Note" or node_type == "MarkdownNote" or (isinstance(node_type, str) and (node_type.startswith("Note") or node_type.startswith("Markdown"))):
                logger.info(f"跳过 {node_type} 节点 {node_id}（注释节点，不参与执行）")
                skipped_node_ids.add(node_id)
                continue
            
            # 跳过 GetNode 和 SetNode 节点（comfyui-logic 插件节点，可能未安装）
            # 这些节点仅用于 workflow 内部值传递，实际执行时会通过链接直接传递值
            if node_type == "GetNode" or node_type == "SetNode":
                logger.info(f"跳过 {node_type} 节点 {node_id}（逻辑节点，不参与执行）")
                skipped_node_ids.add(node_id)
                continue
            
            # 跳过 PrimitiveNode 节点（comfyui-logic 插件节点，可能未安装）
            # PrimitiveNode 用于定义原始值（数字、字符串等），值会通过链接传递到目标节点
            # 在 SteadyDancer workflow 中，节点 123 (cfg) 和 124 (seed) 是 PrimitiveNode
            # 它们的值已经在节点配置时直接设置到目标节点的 inputs 中，所以可以安全跳过
            if node_type == "PrimitiveNode":
                logger.info(f"跳过 {node_type} 节点 {node_id}（原始值节点，值已通过链接传递）")
                skipped_node_ids.add(node_id)
                continue
            
            # 创建符合 ComfyUI API 格式的节点对象
            converted_node = {}
            # 复制所有字段
            for key, value in node.items():
                if key != "id":  # 排除 id 字段
                    if key == "inputs":
                        # 转换 inputs 数组为 inputs 对象
                        converted_inputs = {}
                        # 获取节点的 widgets_values（如果存在）
                        widgets_values = node.get("widgets_values", [])
                        
                        # widgets_values 可能是列表或字典
                        # 如果是字典（如 VHS_VideoCombine），需要按 input 名称匹配
                        # 如果是列表，按顺序匹配有 widget 的 inputs
                        widgets_values_is_dict = isinstance(widgets_values, dict)
                        
                        if not widgets_values_is_dict:
                            # 确保是列表
                            if not isinstance(widgets_values, list):
                                widgets_values = []
                        
                        # widgets_values 按 inputs 顺序包含所有有 widget 的输入值（不管是否有 link）
                        # 需要按 inputs 顺序遍历，但只对有 widget 的输入从 widgets_values 获取值
                        widget_index = 0
                        if isinstance(value, list):
                            for input_index, input_item in enumerate(value):
                                if isinstance(input_item, dict) and "name" in input_item:
                                    input_name = input_item["name"]
                                    has_widget = "widget" in input_item
                                    has_link = "link" in input_item and input_item["link"] is not None
                                    
                                    if has_link:
                                        # 如果有 link，转换为 [node_id, output_index] 格式
                                        link_id = input_item["link"]
                                        if link_id in links_map:
                                            source_node_id, source_output_index = links_map[link_id]
                                            # 如果源节点是 PrimitiveNode，直接使用值
                                            if source_node_id == "__PRIMITIVE__":
                                                converted_inputs[input_name] = source_output_index  # source_output_index 存储的是实际值
                                                logger.info(f"节点{node_id}.{input_name}: 使用 PrimitiveNode 的值 = {source_output_index}")
                                            # 如果源节点被跳过（GetNode/SetNode/Note等），尝试找到实际源节点
                                            elif source_node_id in skipped_node_ids:
                                                # 如果源节点是 SetNode，查找 SetNode 的输入链接
                                                if source_node_id in setnode_to_getnode_map:
                                                    # SetNode 的输出，需要找到 SetNode 的输入源
                                                    for setnode in workflow_data["nodes"]:
                                                        if str(setnode["id"]) == source_node_id and "inputs" in setnode:
                                                            for setnode_input in setnode.get("inputs", []):
                                                                if isinstance(setnode_input, dict) and "link" in setnode_input and setnode_input["link"] is not None:
                                                                    setnode_link_id = setnode_input["link"]
                                                                    if setnode_link_id in links_map:
                                                                        actual_source_id, actual_source_output = links_map[setnode_link_id]
                                                                        if actual_source_id not in skipped_node_ids:
                                                                            converted_inputs[input_name] = [actual_source_id, actual_source_output]
                                                                            logger.info(f"节点{node_id}.{input_name}: 通过 SetNode {source_node_id} -> 实际源节点 {actual_source_id}")
                                                                            break
                                                                    break
                                                            break
                                                    if input_name not in converted_inputs:
                                                        logger.warning(f"节点{node_id}.{input_name}: 无法解析 SetNode {source_node_id} 的链接，跳过")
                                                # 如果源节点是 GetNode，查找对应的 SetNode 的源
                                                elif source_node_id in getnode_to_setnode_map:
                                                    setnode_id = getnode_to_setnode_map[source_node_id]
                                                    # 查找 SetNode 的输入链接
                                                    for setnode in workflow_data["nodes"]:
                                                        if str(setnode["id"]) == setnode_id and "inputs" in setnode:
                                                            for setnode_input in setnode.get("inputs", []):
                                                                if isinstance(setnode_input, dict) and "link" in setnode_input and setnode_input["link"] is not None:
                                                                    setnode_link_id = setnode_input["link"]
                                                                    if setnode_link_id in links_map:
                                                                        actual_source_id, actual_source_output = links_map[setnode_link_id]
                                                                        if actual_source_id not in skipped_node_ids:
                                                                            converted_inputs[input_name] = [actual_source_id, actual_source_output]
                                                                            logger.info(f"节点{node_id}.{input_name}: 通过 GetNode {source_node_id} -> SetNode {setnode_id} -> 实际源节点 {actual_source_id}")
                                                                            break
                                                                    break
                                                            break
                                                    if input_name not in converted_inputs:
                                                        logger.warning(f"节点{node_id}.{input_name}: 无法解析 GetNode {source_node_id} 的链接，尝试直接查找SetNode")
                                                        # 如果GetNode映射失败，尝试直接查找对应的SetNode
                                                        # 通过GetNode的widgets_values获取名称
                                                        getnode_name = None
                                                        for getnode in workflow_data["nodes"]:
                                                            if str(getnode["id"]) == source_node_id:
                                                                getnode_name = getnode.get("title", "").replace("Get_", "")
                                                                if not getnode_name and getnode.get("widgets_values"):
                                                                    getnode_name = getnode["widgets_values"][0] if isinstance(getnode["widgets_values"], list) else ""
                                                                break
                                                        # 查找对应的SetNode
                                                        if getnode_name:
                                                            for setnode in workflow_data["nodes"]:
                                                                setnode_name = setnode.get("title", "").replace("Set_", "")
                                                                if not setnode_name and setnode.get("widgets_values"):
                                                                    setnode_name = setnode["widgets_values"][0] if isinstance(setnode["widgets_values"], list) else ""
                                                                if setnode_name == getnode_name:
                                                                    # 找到SetNode，查找其输入链接
                                                                    if "inputs" in setnode and isinstance(setnode["inputs"], list):
                                                                        for setnode_input in setnode["inputs"]:
                                                                            if isinstance(setnode_input, dict) and "link" in setnode_input and setnode_input["link"] is not None:
                                                                                setnode_link_id = setnode_input["link"]
                                                                                if setnode_link_id in links_map:
                                                                                    actual_source_id, actual_source_output = links_map[setnode_link_id]
                                                                                    if actual_source_id not in skipped_node_ids:
                                                                                        converted_inputs[input_name] = [actual_source_id, actual_source_output]
                                                                                        logger.info(f"节点{node_id}.{input_name}: 通过直接查找SetNode -> 实际源节点 {actual_source_id}")
                                                                                        break
                                                                    break
                                                else:
                                                    logger.warning(f"节点{node_id}.{input_name}: 源节点 {source_node_id} 被跳过且无法解析，跳过此输入")
                                            # 如果源节点是 logic 节点，直接使用计算的值
                                            elif source_node_id in logic_node_values:
                                                converted_inputs[input_name] = logic_node_values[source_node_id]
                                                logger.info(f"节点{node_id}.{input_name}: 内联 logic 节点{source_node_id}的值 = {logic_node_values[source_node_id]}")
                                            else:
                                                # 检查源节点是否存在（不在prompt中或已被跳过）
                                                if source_node_id not in prompt and source_node_id not in skipped_node_ids:
                                                    logger.warning(f"节点{node_id}.{input_name}: 源节点 {source_node_id} 不存在，跳过此输入")
                                                    # 不设置此输入，让ComfyUI使用默认值或报错
                                                else:
                                                    converted_inputs[input_name] = [source_node_id, source_output_index]
                                        else:
                                            # 如果找不到 link，保持原值或设为 None
                                            logger.warning(f"节点{node_id}.{input_name}: 链接 {link_id} 在 links_map 中不存在")
                                            converted_inputs[input_name] = None
                                        # 如果有 widget，需要跳过 widgets_values 中的对应值（仅当是列表时）
                                        if not widgets_values_is_dict and has_widget and widget_index < len(widgets_values):
                                            widget_index += 1
                                    else:
                                        # 如果没有 link，尝试从 value 字段或 widgets_values 获取值
                                        if "value" in input_item:
                                            converted_inputs[input_name] = input_item["value"]
                                        elif has_widget:
                                            # 从 widgets_values 获取值
                                            widget_value = None
                                            if widgets_values_is_dict:
                                                # 字典模式：按名称匹配
                                                widget_value = widgets_values.get(input_name)
                                            elif widget_index < len(widgets_values):
                                                # 列表模式：按顺序匹配
                                                widget_value = widgets_values[widget_index]
                                                widget_index += 1
                                            
                                            # 跳过 null 值（可能是可选输入）
                                            if widget_value is not None:
                                                converted_inputs[input_name] = widget_value
                                        # 如果没有值，不设置（可能是可选输入）
                        converted_node["inputs"] = converted_inputs
                    else:
                        converted_node[key] = value
            # 将 type 字段转换为 class_type（ComfyUI API 需要）
            if "type" in converted_node:
                node_type = converted_node["type"]
                # 检查节点类型是否包含管道符（命名空间），如 "MathExpression|pysssss"
                if "|" in node_type:
                    # 如果包含管道符，直接使用
                    converted_node["class_type"] = node_type
                else:
                    # 如果不包含管道符，检查是否有properties中的cnr_id
                    properties = converted_node.get("properties", {})
                    cnr_id = properties.get("cnr_id")
                    if cnr_id:
                        # 尝试使用 "节点类型|插件ID" 格式
                        # 但ComfyUI API通常只需要节点类型名称，不需要插件ID
                        converted_node["class_type"] = node_type
                    else:
                        converted_node["class_type"] = node_type
                # 保留 type 字段（某些情况下可能需要）
            # 确保节点有 class_type 字段（ComfyUI API 必需）
            if "class_type" not in converted_node:
                if "type" in converted_node:
                    converted_node["class_type"] = converted_node["type"]
                else:
                    logger.warning(f"节点 {node_id} 缺少 type 和 class_type 字段")
            prompt[node_id] = converted_node
        logger.info("已转换 nodes 数组格式为节点 ID key 格式")
        
        # 后处理：验证关键节点的必需输入是否已设置，并尝试修复
        # 这有助于早期发现链接解析问题
        critical_nodes = {
            "28": {"vae": "WANVAE", "samples": "LATENT"},  # WanVideoDecode
            "77": {"image": "IMAGE", "width": "INT", "height": "INT"},  # ImageResizeKJv2
            "79": {"image_1": "IMAGE"},  # ImageConcatMulti
            "131": {"images": "IMAGE"},  # PreviewImage
        }
        
        # 尝试修复缺失的链接
        for node_id, required_inputs in critical_nodes.items():
            if node_id in prompt:
                if "inputs" not in prompt[node_id]:
                    logger.warning(f"⚠️ 关键节点 {node_id} 缺少 inputs 对象")
                    prompt[node_id]["inputs"] = {}
                
                for input_name, input_type in required_inputs.items():
                    if input_name not in prompt[node_id]["inputs"] or prompt[node_id]["inputs"][input_name] is None:
                        logger.warning(f"⚠️ 关键节点 {node_id} 缺少必需输入 {input_name} ({input_type})，尝试修复")
                        
                        # 从原始workflow中查找此节点的输入链接
                        for orig_node in workflow_data["nodes"]:
                            if str(orig_node["id"]) == node_id:
                                if "inputs" in orig_node and isinstance(orig_node["inputs"], list):
                                    for input_item in orig_node["inputs"]:
                                        if isinstance(input_item, dict) and input_item.get("name") == input_name:
                                            if "link" in input_item and input_item["link"] is not None:
                                                link_id = input_item["link"]
                                                logger.info(f"  节点{node_id}.{input_name} 的链接ID: {link_id}")
                                                
                                                # 查找这个链接的源节点
                                                if "links" in workflow_data:
                                                    for link in workflow_data["links"]:
                                                        if len(link) >= 6 and link[0] == link_id:
                                                            source_node_id = str(link[1])
                                                            source_output_index = link[2]
                                                            logger.info(f"  链接{link_id}: 源节点 {source_node_id}, 输出索引 {source_output_index}")
                                                            
                                                            # 检查源节点类型
                                                            source_node_type = None
                                                            source_node_name = None
                                                            for src_node in workflow_data["nodes"]:
                                                                if str(src_node["id"]) == source_node_id:
                                                                    source_node_type = src_node.get("type")
                                                                    source_node_name = src_node.get("title", "")
                                                                    break
                                                            
                                                            logger.info(f"  源节点类型: {source_node_type}, 名称: {source_node_name}")
                                                            
                                                            # 如果源节点是GetNode，查找对应的SetNode
                                                            if source_node_type == "GetNode":
                                                                getnode_name = source_node_name.replace("Get_", "")
                                                                if not getnode_name:
                                                                    for src_node in workflow_data["nodes"]:
                                                                        if str(src_node["id"]) == source_node_id:
                                                                            if src_node.get("widgets_values"):
                                                                                getnode_name = src_node["widgets_values"][0] if isinstance(src_node["widgets_values"], list) else ""
                                                                            break
                                                                
                                                                logger.info(f"  GetNode名称: {getnode_name}")
                                                                
                                                                # 查找对应的SetNode
                                                                for setnode in workflow_data["nodes"]:
                                                                    if setnode.get("type") == "SetNode":
                                                                        setnode_name = setnode.get("title", "").replace("Set_", "")
                                                                        if not setnode_name and setnode.get("widgets_values"):
                                                                            setnode_name = setnode["widgets_values"][0] if isinstance(setnode["widgets_values"], list) else ""
                                                                        
                                                                        if setnode_name == getnode_name:
                                                                            # 找到SetNode，查找其输入链接
                                                                            logger.info(f"  找到SetNode {setnode['id']}: {setnode_name}")
                                                                            if "inputs" in setnode and isinstance(setnode["inputs"], list):
                                                                                for setnode_input in setnode["inputs"]:
                                                                                    if isinstance(setnode_input, dict) and "link" in setnode_input:
                                                                                        setnode_link_id = setnode_input["link"]
                                                                                        logger.info(f"  SetNode的输入链接ID: {setnode_link_id}")
                                                                                        # 查找SetNode的源节点
                                                                                        for link2 in workflow_data["links"]:
                                                                                            if len(link2) >= 6 and link2[0] == setnode_link_id:
                                                                                                actual_source_id = str(link2[1])
                                                                                                actual_output_index = link2[2]
                                                                                                logger.info(f"  SetNode的源节点: {actual_source_id}, 输出索引: {actual_output_index}")
                                                                                                
                                                                                                # 设置链接
                                                                                                if actual_source_id not in skipped_node_ids:
                                                                                                    prompt[node_id]["inputs"][input_name] = [actual_source_id, actual_output_index]
                                                                                                    logger.info(f"  ✅ 修复成功: 节点{node_id}.{input_name} = [{actual_source_id}, {actual_output_index}]")
                                                                                                break
                                                                                        break
                                                                            break
                                                            else:
                                                                # 源节点不是GetNode，直接使用
                                                                if source_node_id not in skipped_node_ids:
                                                                    prompt[node_id]["inputs"][input_name] = [source_node_id, source_output_index]
                                                                    logger.info(f"  ✅ 修复成功: 节点{node_id}.{input_name} = [{source_node_id}, {source_output_index}]")
                                                            break
                                            break
                                break
    else:
        # new_Wan22_api.json 使用节点 ID key 格式
        prompt = workflow_data
    
    # 更新模型名称（仅对标准 workflow）
    if not is_mega_model and available_models:
        # 更新节点 122 和 549 的模型名称（如果存在）
        update_model_in_prompt(prompt, "122", available_models)
        update_model_in_prompt(prompt, "549", available_models)
    elif is_mega_model and available_models:
        # 对于 RapidAIO Mega (V2.5).json，更新节点 574 (CheckpointLoaderSimple) 的模型
        if "574" in prompt and "widgets_values" in prompt["574"]:
            current_model = prompt["574"]["widgets_values"][0] if prompt["574"]["widgets_values"] else ""
            # 查找 MEGA/AIO 模型
            mega_models = [m for m in available_models if "mega" in m.lower() or "aio" in m.lower() or "all-in-one" in m.lower() or "allinone" in m.lower()]
            if mega_models:
                new_model = mega_models[0]
                if current_model != new_model:
                    prompt["574"]["widgets_values"][0] = new_model
                    logger.info(f"节点 574 模型更新: {current_model} -> {new_model}")
            elif available_models:
                # 如果没有找到 MEGA 模型，使用第一个可用模型
                new_model = available_models[0]
                if current_model != new_model:
                    prompt["574"]["widgets_values"][0] = new_model
                    logger.info(f"节点 574 模型更新: {current_model} -> {new_model}")
    
    # MEGA v12 推荐配置（根据 Hugging Face: https://huggingface.co/Phr00t/WAN2.2-14B-Rapid-AllInOne）
    # - Steps: 4 (推荐值，保持向后兼容允许自定义)
    # - CFG: 1.0 (推荐值)
    # - Sampler: euler_a (推荐，替代之前的 ipndm)
    # - Scheduler: beta (推荐，替代之前的 sgm_uniform)
    steps = job_input.get("steps", 4)
    seed = job_input.get("seed", 42)
    cfg = job_input.get("cfg", 1.0)
    # 允许用户自定义 sampler 和 scheduler（保持向后兼容）
    sampler_name = job_input.get("sampler", "euler_a")
    scheduler = job_input.get("scheduler", "beta")
    
    # 支持多提示词输入（用于生成更长视频）
    # 可以是字符串（用换行符分隔）或数组
    prompt_input = job_input.get("prompt", "running man, grab the gun")
    if isinstance(prompt_input, list):
        # 如果是数组，用换行符连接
        positive_prompt = "\n".join(str(p) for p in prompt_input if p)
    elif isinstance(prompt_input, str):
        # 如果是字符串，直接使用（可能包含换行符）
        positive_prompt = prompt_input
    else:
        positive_prompt = str(prompt_input)
    
    # 计算提示词数量（用于日志和验证）
    prompt_lines = [line.strip() for line in positive_prompt.split("\n") if line.strip()]
    prompt_count = len(prompt_lines)
    if prompt_count > 1:
        # 根据 Hugging Face 讨论：总视频长度 = length * prompt_count
        # length 是每个 batch 的帧数
        total_frames = length * prompt_count
        # 转换为秒数（假设 16fps）
        total_seconds = total_frames / 16.0
        logger.info(f"📹 多提示词模式: {prompt_count} 个提示词，每个 batch {length} 帧，总长度约 {total_seconds:.1f} 秒 ({total_frames} 帧)")
        logger.info(f"提示词列表: {[p[:50] + '...' if len(p) > 50 else p for p in prompt_lines]}")
    
    negative_prompt = job_input.get("negative_prompt", "")
    
    # 提示词长度检查 - 过长的提示词可能导致 OOM
    max_prompt_length = 500  # 建议最大长度（单个提示词）
    if prompt_count > 1:
        # 多提示词模式：检查每个提示词的长度
        for i, prompt_line in enumerate(prompt_lines):
            if len(prompt_line) > max_prompt_length:
                logger.warning(f"⚠️ 提示词 {i+1}/{prompt_count} 长度 ({len(prompt_line)} 字符) 超过建议值 ({max_prompt_length} 字符)")
    else:
        # 单提示词模式：检查总长度
        if len(positive_prompt) > max_prompt_length:
            logger.warning(f"⚠️ 提示词长度 ({len(positive_prompt)} 字符) 超过建议值 ({max_prompt_length} 字符)，可能导致 GPU 内存不足")
            logger.warning(f"提示词前100字符: {positive_prompt[:100]}...")
    
    # 해상도(폭/높이) 16배수 보정
    original_width = job_input.get("width", 480)
    original_height = job_input.get("height", 832)
    adjusted_width = to_nearest_multiple_of_16(original_width)
    adjusted_height = to_nearest_multiple_of_16(original_height)
    if adjusted_width != original_width:
        logger.info(f"Width adjusted to nearest multiple of 16: {original_width} -> {adjusted_width}")
    if adjusted_height != original_height:
        logger.info(f"Height adjusted to nearest multiple of 16: {original_height} -> {adjusted_height}")
    
    if is_mega_model:
        # RapidAIO Mega (V2.5).json workflow 节点配置
        # V2.5 使用不同的节点结构，需要适配新的节点 ID
        
        # 节点597: LoadImage (起始图像)
        if "597" in prompt:
            if "widgets_values" in prompt["597"]:
                prompt["597"]["widgets_values"][0] = image_path
            # 确保 inputs 存在并设置 image
            if "inputs" not in prompt["597"]:
                prompt["597"]["inputs"] = {}
            prompt["597"]["inputs"]["image"] = image_path
            logger.info(f"节点597 (起始图像): {image_path}")
        
        # 节点591: CreaPrompt List - 多提示词输入
        # widgets_values[0] = Multi_prompts, [1] = prefix, [2] = suffix
        if "591" in prompt:
            if "widgets_values" in prompt["591"]:
                widgets = prompt["591"]["widgets_values"]
                # 设置多提示词（用换行符分隔）
                widgets[0] = positive_prompt
                # prefix 和 suffix 保持原值或设为空
                if len(widgets) < 2:
                    widgets.append("")  # prefix
                if len(widgets) < 3:
                    widgets.append("")  # suffix
            if "inputs" not in prompt["591"]:
                prompt["591"]["inputs"] = {}
            prompt["591"]["inputs"]["Multi_prompts"] = positive_prompt
            if prompt_count > 1:
                logger.info(f"节点591 (CreaPrompt List - 多提示词模式): {prompt_count} 个提示词")
            else:
                logger.info(f"节点591 (CreaPrompt List): {positive_prompt}")
        
        # 节点574: CheckpointLoaderSimple - widgets_values[0] 是模型名称
        if "574" in prompt:
            if "widgets_values" in prompt["574"] and prompt["574"]["widgets_values"]:
                model_name = prompt["574"]["widgets_values"][0]
            else:
                # 如果没有 widgets_values，尝试从可用模型列表中获取
                if available_models:
                    model_name = available_models[0]
                else:
                    model_name = "wan2.2-rapid-mega-aio-nsfw-v12.1.safetensors"  # 默认值
            
            if "inputs" not in prompt["574"]:
                prompt["574"]["inputs"] = {}
            
            # 获取 CheckpointLoaderSimple 的实际可用模型列表
            checkpoint_models = []
            try:
                url = f"http://{server_address}:8188/object_info"
                with urllib_request.urlopen(url, timeout=5) as response:
                    object_info = json.loads(response.read())
                    if "CheckpointLoaderSimple" in object_info:
                        loader_info = object_info["CheckpointLoaderSimple"]
                        if "input" in loader_info and "required" in loader_info["input"]:
                            if "ckpt_name" in loader_info["input"]["required"]:
                                checkpoint_models = loader_info["input"]["required"]["ckpt_name"]
                                if isinstance(checkpoint_models, list) and len(checkpoint_models) > 0:
                                    if isinstance(checkpoint_models[0], list):
                                        checkpoint_models = checkpoint_models[0]
                                    checkpoint_models = [m for m in checkpoint_models if isinstance(m, str)]
                        logger.info(f"CheckpointLoaderSimple 可用模型列表: {checkpoint_models}")
            except Exception as e:
                logger.warning(f"获取 CheckpointLoaderSimple 模型列表失败: {e}")
            
            # 决定使用哪个模型名称
            if checkpoint_models:
                if model_name in checkpoint_models:
                    final_model_name = model_name
                    logger.info(f"使用模型: {final_model_name} (在 CheckpointLoaderSimple 列表中)")
                else:
                    final_model_name = checkpoint_models[0]
                    logger.warning(f"模型 '{model_name}' 不在 CheckpointLoaderSimple 列表中，使用列表中的第一个: {final_model_name}")
            else:
                if model_name in available_models:
                    final_model_name = model_name
                    logger.warning(f"CheckpointLoaderSimple 模型列表为空，但模型 '{model_name}' 在 WanVideoModelLoader 中")
                else:
                    final_model_name = model_name
                    logger.warning(f"CheckpointLoaderSimple 和 WanVideoModelLoader 都无法找到模型，使用默认名称: {final_model_name}")
            
            prompt["574"]["inputs"]["ckpt_name"] = final_model_name
            logger.info(f"节点574 (模型): {prompt['574']['inputs']['ckpt_name']}")
        
        # 节点592, 593, 585 (comfyui-logic) 已在转换时跳过并内联，这里不需要处理
        
        # 节点595: PrimitiveString (Filename) - 文件名前缀
        if "595" in prompt:
            filename_prefix = job_input.get("filename_prefix", "rapid-mega-out/vid")
            if "widgets_values" in prompt["595"]:
                prompt["595"]["widgets_values"][0] = filename_prefix
            if "inputs" not in prompt["595"]:
                prompt["595"]["inputs"] = {}
            prompt["595"]["inputs"]["value"] = filename_prefix
            logger.info(f"节点595 (Filename): {filename_prefix}")
        
        # 节点561: easy forLoopStart - 循环开始
        # total 会自动从节点 589 (StringFromList) 的 size 获取（提示词数量）
        # 不需要手动设置，workflow 会自动处理
        
        # 节点566: CLIPTextEncode (正面提示词) - 在循环内，由节点 565 (StringFromList) 提供
        # 不需要手动设置，workflow 会自动从提示词列表中提取
        
        # 节点567: CLIPTextEncode (负面提示词)
        if "567" in prompt:
            if "widgets_values" in prompt["567"]:
                prompt["567"]["widgets_values"][0] = negative_prompt
            if "inputs" not in prompt["567"]:
                prompt["567"]["inputs"] = {}
            prompt["567"]["inputs"]["text"] = negative_prompt
            logger.info(f"节点567 (负面提示词): {negative_prompt}")
        
        # 节点576: WanVideoVACEStartToEndFrame - widgets_values[0]=num_frames, [1]=empty_frame_level
        if "576" in prompt:
            empty_frame_level = 1.0  # 默认值
            if "widgets_values" in prompt["576"]:
                widgets = prompt["576"]["widgets_values"]
                widgets[0] = length  # num_frames
                if len(widgets) < 2:
                    widgets.append(1.0)  # empty_frame_level (默认 1.0)
                empty_frame_level = widgets[1] if len(widgets) > 1 else 1.0
            if "inputs" not in prompt["576"]:
                prompt["576"]["inputs"] = {}
            prompt["576"]["inputs"]["num_frames"] = length
            prompt["576"]["inputs"]["empty_frame_level"] = empty_frame_level
            logger.info(f"节点576 (VACE num_frames): {length}, empty_frame_level: {prompt['576']['inputs']['empty_frame_level']}")
        
        # 节点572: WanVaceToVideo - widgets_values[0]=width, [1]=height, [2]=length, [3]=strength, [4]=batch_size
        if "572" in prompt:
            batch_size = 1  # 默认值
            if "widgets_values" in prompt["572"]:
                widgets = prompt["572"]["widgets_values"]
                # 先确保列表长度足够（至少5个元素），再访问索引
                if len(widgets) < 5:
                    widgets.extend([None] * (5 - len(widgets)))
                widgets[0] = adjusted_width
                widgets[1] = adjusted_height
                widgets[2] = length
                widgets[3] = 1  # strength = 1 for I2V
                if widgets[4] is None:
                    widgets[4] = 1  # batch_size
                batch_size = widgets[4]
            if "inputs" not in prompt["572"]:
                prompt["572"]["inputs"] = {}
            prompt["572"]["inputs"]["width"] = adjusted_width
            prompt["572"]["inputs"]["height"] = adjusted_height
            prompt["572"]["inputs"]["length"] = length
            prompt["572"]["inputs"]["batch_size"] = batch_size
            prompt["572"]["inputs"]["strength"] = 1  # I2V mode
            logger.info(f"节点572 (WanVaceToVideo): width={adjusted_width}, height={adjusted_height}, length={length}, batch_size={prompt['572']['inputs']['batch_size']}, strength=1 (I2V)")
        
        # 节点562: ModelSamplingSD3 - widgets_values[0] 是 shift
        if "562" in prompt:
            shift_value = job_input.get("shift", 7.02)  # V2.5 默认值
            if "widgets_values" in prompt["562"]:
                prompt["562"]["widgets_values"][0] = shift_value
            if "inputs" not in prompt["562"]:
                prompt["562"]["inputs"] = {}
            prompt["562"]["inputs"]["shift"] = shift_value
            logger.info(f"节点562 (ModelSamplingSD3): shift={shift_value}")
        
        # 节点563: KSampler - widgets_values[0]=seed, [1]=control_after_generate, [2]=steps, [3]=cfg, [4]=sampler_name, [5]=scheduler, [6]=denoise
        if "563" in prompt:
            if "widgets_values" in prompt["563"]:
                widgets = prompt["563"]["widgets_values"]
                # 先确保列表长度足够（至少6个元素），再访问索引
                if len(widgets) < 6:
                    widgets.extend([None] * (6 - len(widgets)))
                widgets[0] = seed
                widgets[2] = steps
                widgets[3] = cfg
                # MEGA v12 推荐使用 euler_a/beta（根据 Hugging Face 文档）
                # 如果用户没有指定或值为 "randomize"，使用推荐的默认值
                if not widgets[4] or widgets[4] == "randomize":
                    widgets[4] = sampler_name  # 使用 job_input 中的值或默认 euler_a
                if not widgets[5]:
                    widgets[5] = scheduler  # 使用 job_input 中的值或默认 beta
            if "inputs" not in prompt["563"]:
                prompt["563"]["inputs"] = {}
            widgets = prompt["563"].get("widgets_values", [seed, "randomize", steps, cfg, sampler_name, scheduler, 1])
            prompt["563"]["inputs"]["seed"] = seed
            prompt["563"]["inputs"]["steps"] = steps
            prompt["563"]["inputs"]["cfg"] = cfg
            # 使用 job_input 中的值（已包含默认值 euler_a/beta）
            prompt["563"]["inputs"]["sampler_name"] = widgets[4] if len(widgets) > 4 and widgets[4] else sampler_name
            prompt["563"]["inputs"]["scheduler"] = widgets[5] if len(widgets) > 5 and widgets[5] else scheduler
            prompt["563"]["inputs"]["denoise"] = widgets[6] if len(widgets) > 6 else 1.0
            logger.info(f"节点563 (KSampler): seed={seed}, steps={steps}, cfg={cfg}, sampler={prompt['563']['inputs']['sampler_name']}, scheduler={prompt['563']['inputs']['scheduler']}, denoise={prompt['563']['inputs']['denoise']}")
        
        # 节点584: VHS_VideoCombine - 视频合并节点
        if "584" in prompt:
            # 确保 inputs 存在
            if "inputs" not in prompt["584"]:
                prompt["584"]["inputs"] = {}
            
            # 如果存在 widgets_values，将其转换为 inputs
            if "widgets_values" in prompt["584"]:
                widgets = prompt["584"]["widgets_values"]
                # VHS_VideoCombine 需要的参数
                if isinstance(widgets, dict):
                    # 将 widgets_values 字典中的参数复制到 inputs
                    for key, value in widgets.items():
                        if key not in ["videopreview"]:  # 排除不需要的参数
                            prompt["584"]["inputs"][key] = value
                    logger.info(f"节点584 (VHS_VideoCombine): 已从 widgets_values 转换参数到 inputs")
                else:
                    # 如果 widgets_values 是数组，使用默认值
                    prompt["584"]["inputs"]["frame_rate"] = 16
                    prompt["584"]["inputs"]["loop_count"] = 0
                    prompt["584"]["inputs"]["filename_prefix"] = job_input.get("filename_prefix", "rapid-mega-out/vid")
                    prompt["584"]["inputs"]["format"] = "video/h264-mp4"
                    prompt["584"]["inputs"]["save_output"] = True
                    prompt["584"]["inputs"]["pingpong"] = False
                    logger.info(f"节点584 (VHS_VideoCombine): 使用默认参数")
            else:
                # 如果没有 widgets_values，使用默认值
                prompt["584"]["inputs"]["frame_rate"] = 16
                prompt["584"]["inputs"]["loop_count"] = 0
                prompt["584"]["inputs"]["filename_prefix"] = job_input.get("filename_prefix", "rapid-mega-out/vid")
                prompt["584"]["inputs"]["format"] = "video/h264-mp4"
                prompt["584"]["inputs"]["save_output"] = True
                prompt["584"]["inputs"]["pingpong"] = False
                logger.info(f"节点584 (VHS_VideoCombine): 使用默认参数")
    elif use_steadydancer:
        # SteadyDancer workflow 节点配置
        # 获取 shift 参数（SteadyDancer 使用）
        shift = job_input.get("shift", 5.0)  # SteadyDancer 默认值
        
        # 节点 76: LoadImage (参考图像)
        if "76" in prompt:
            if "widgets_values" in prompt["76"]:
                prompt["76"]["widgets_values"][0] = image_path
            if "inputs" not in prompt["76"]:
                prompt["76"]["inputs"] = {}
            prompt["76"]["inputs"]["image"] = image_path
            logger.info(f"节点76 (LoadImage): {image_path}")
        
        # 节点 75: VHS_LoadVideo (输入视频)
        video_path = job_input.get("video_path") or job_input.get("video_url") or job_input.get("video_base64")
        if video_path:
            video_path_local = process_input(video_path, task_id, "input_video.mp4", 
                                            "path" if "video_path" in job_input else ("url" if "video_url" in job_input else "base64"))
            if "75" in prompt:
                if "widgets_values" in prompt["75"]:
                    widgets = prompt["75"]["widgets_values"]
                    if isinstance(widgets, dict):
                        widgets["video"] = video_path_local
                    elif isinstance(widgets, list) and len(widgets) > 0:
                        widgets[0] = video_path_local
                if "inputs" not in prompt["75"]:
                    prompt["75"]["inputs"] = {}
                prompt["75"]["inputs"]["video"] = video_path_local
                logger.info(f"节点75 (VHS_LoadVideo): {video_path_local}")
        else:
            logger.warning("⚠️ 未提供输入视频，SteadyDancer workflow 需要输入视频用于姿态检测")
        
        # 节点 22: WanVideoModelLoader (模型)
        if "22" in prompt:
            # 查找 SteadyDancer 模型（支持 GGUF）
            model_name = None
            if available_models:
                # 优先查找包含 "steadydancer" 的模型
                steadydancer_models = [m for m in available_models if "steadydancer" in m.lower()]
                if steadydancer_models:
                    model_name = steadydancer_models[0]
                else:
                    # 如果没有找到，查找包含 "gguf" 的模型
                    gguf_models = [m for m in available_models if "gguf" in m.lower()]
                    if gguf_models:
                        model_name = gguf_models[0]
                    elif available_models:
                        # 如果都没有，使用第一个可用模型
                        model_name = available_models[0]
                        logger.warning(f"⚠️ 未找到 SteadyDancer 模型，使用第一个可用模型: {model_name}")
            
            if model_name:
                if "widgets_values" in prompt["22"]:
                    widgets = prompt["22"]["widgets_values"]
                    if len(widgets) > 0:
                        widgets[0] = model_name
                if "inputs" not in prompt["22"]:
                    prompt["22"]["inputs"] = {}
                prompt["22"]["inputs"]["model"] = model_name
                logger.info(f"节点22 (WanVideoModelLoader): {model_name}")
            else:
                logger.warning(f"⚠️ 未找到可用模型，可用模型列表: {available_models}")
        
        # 节点 38: WanVideoVAELoader (VAE 模型)
        # workflow 中使用 "wanvideo/Wan2_1_VAE_bf16.safetensors"
        # Dockerfile 中已创建符号链接支持此路径格式
        if "38" in prompt:
            # 使用 workflow 中的路径格式（wanvideo/ 前缀）
            vae_model_name = "wanvideo/Wan2_1_VAE_bf16.safetensors"
            if "widgets_values" in prompt["38"]:
                widgets = prompt["38"]["widgets_values"]
                if len(widgets) > 0:
                    widgets[0] = vae_model_name
            if "inputs" not in prompt["38"]:
                prompt["38"]["inputs"] = {}
            prompt["38"]["inputs"]["model_name"] = vae_model_name
            logger.info(f"节点38 (WanVideoVAELoader): {vae_model_name}")
        
        # 节点 59: CLIPVisionLoader (CLIP Vision 模型)
        # workflow 中使用 "clip_vision_h.safetensors"，路径正确
        if "59" in prompt:
            clip_vision_name = "clip_vision_h.safetensors"
            if "widgets_values" in prompt["59"]:
                widgets = prompt["59"]["widgets_values"]
                if len(widgets) > 0:
                    widgets[0] = clip_vision_name
            if "inputs" not in prompt["59"]:
                prompt["59"]["inputs"] = {}
            prompt["59"]["inputs"]["clip_name"] = clip_vision_name
            logger.info(f"节点59 (CLIPVisionLoader): {clip_vision_name}")
        
        # 节点 69: WanVideoLoraSelect (LoRA 选择器)
        # workflow 中使用 "WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
        # Dockerfile 中已下载到 /ComfyUI/models/loras/WanVideo/Lightx2v/
        if "69" in prompt:
            # 尝试不同的路径格式
            lora_candidates = [
                "WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",  # 完整路径
                "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",  # 子目录格式
                "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",  # 直接文件名
            ]
            
            lora_model = None
            for candidate in lora_candidates:
                # 检查文件是否存在
                if candidate.startswith("WanVideo/"):
                    full_path = f"/ComfyUI/models/loras/{candidate}"
                elif "/" in candidate:
                    full_path = f"/ComfyUI/models/loras/{candidate}"
                else:
                    full_path = f"/ComfyUI/models/loras/WanVideo/Lightx2v/{candidate}"
                
                if os.path.exists(full_path):
                    lora_model = candidate
                    logger.info(f"找到 LoRA 模型: {full_path}")
                    break
            
            # 如果找不到，使用workflow中的默认路径
            if not lora_model:
                lora_model = "WanVideo/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
                logger.warning(f"LoRA 模型文件不存在，使用默认路径: {lora_model}")
            
            if "widgets_values" in prompt["69"]:
                widgets = prompt["69"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = lora_model
            if "inputs" not in prompt["69"]:
                prompt["69"]["inputs"] = {}
            prompt["69"]["inputs"]["lora"] = lora_model
            logger.info(f"节点69 (WanVideoLoraSelect): {lora_model}")
        
        # 节点 92: WanVideoTextEncodeCached (文本编码器)
        # workflow 中使用 "umt5-xxl-enc-bf16.safetensors"，路径正确
        if "92" in prompt:
            if "widgets_values" in prompt["92"]:
                widgets = prompt["92"]["widgets_values"]
                # widgets_values[0] = model_name (umt5-xxl-enc-bf16.safetensors)
                # widgets_values[1] = precision (bf16)
                # widgets_values[2] = positive_prompt
                # widgets_values[3] = negative_prompt
                if len(widgets) >= 1:
                    # 保持 model_name 不变（workflow 中已有正确值）
                    pass
                if len(widgets) >= 3:
                    widgets[2] = positive_prompt  # positive_prompt
                if len(widgets) >= 4:
                    widgets[3] = negative_prompt  # negative_prompt
            if "inputs" not in prompt["92"]:
                prompt["92"]["inputs"] = {}
            prompt["92"]["inputs"]["positive_prompt"] = positive_prompt
            prompt["92"]["inputs"]["negative_prompt"] = negative_prompt
            logger.info(f"节点92 (WanVideoTextEncodeCached): positive='{positive_prompt[:50]}...', negative='{negative_prompt[:50] if negative_prompt else ''}...'")
        
        # 节点 129: OnnxDetectionModelLoader (姿态检测模型)
        if "129" in prompt:
            # 获取可用模型列表
            try:
                url = f"http://{server_address}:8188/object_info"
                with urllib_request.urlopen(url, timeout=5) as response:
                    object_info = json.loads(response.read())
                    if "OnnxDetectionModelLoader" in object_info:
                        loader_info = object_info["OnnxDetectionModelLoader"]
                        available_vitpose = []
                        available_yolo = []
                        
                        if "input" in loader_info and "required" in loader_info["input"]:
                            if "vitpose_model" in loader_info["input"]["required"]:
                                available_vitpose = loader_info["input"]["required"]["vitpose_model"]
                                if isinstance(available_vitpose, list) and len(available_vitpose) > 0:
                                    if isinstance(available_vitpose[0], list):
                                        available_vitpose = available_vitpose[0]
                                    available_vitpose = [m for m in available_vitpose if isinstance(m, str)]
                            if "yolo_model" in loader_info["input"]["required"]:
                                available_yolo = loader_info["input"]["required"]["yolo_model"]
                                if isinstance(available_yolo, list) and len(available_yolo) > 0:
                                    if isinstance(available_yolo[0], list):
                                        available_yolo = available_yolo[0]
                                    available_yolo = [m for m in available_yolo if isinstance(m, str)]
                        
                        logger.info(f"OnnxDetectionModelLoader 可用模型: vitpose={available_vitpose}, yolo={available_yolo}")
                        
                        # 如果列表为空，尝试从文件系统扫描
                        if not available_vitpose or not available_yolo:
                            detection_dirs = [
                                ("/ComfyUI/models/detection", "detection"),
                                ("/ComfyUI/models/onnx", "onnx")
                            ]
                            for detection_dir, prefix in detection_dirs:
                                if os.path.exists(detection_dir):
                                    for file in os.listdir(detection_dir):
                                        if file.endswith('.onnx'):
                                            file_path = os.path.join(detection_dir, file)
                                            if os.path.isfile(file_path):
                                                # 尝试多种路径格式
                                                path_formats = [
                                                    f"{prefix}/{file}",  # 带前缀的路径
                                                    file,  # 仅文件名
                                                ]
                                                for relative_path in path_formats:
                                                    if 'vitpose' in file.lower() and relative_path not in available_vitpose:
                                                        available_vitpose.append(relative_path)
                                                    if 'yolo' in file.lower() and relative_path not in available_yolo:
                                                        available_yolo.append(relative_path)
                            if available_vitpose or available_yolo:
                                logger.info(f"从文件系统扫描到的模型: vitpose={available_vitpose}, yolo={available_yolo}")
            except Exception as e:
                logger.warning(f"获取 OnnxDetectionModelLoader 模型列表失败: {e}")
                available_vitpose = []
                available_yolo = []
                # 尝试从文件系统扫描作为后备
                try:
                    detection_dirs = [
                        ("/ComfyUI/models/detection", "detection"),
                        ("/ComfyUI/models/onnx", "onnx")
                    ]
                    for detection_dir, prefix in detection_dirs:
                        if os.path.exists(detection_dir):
                            for file in os.listdir(detection_dir):
                                if file.endswith('.onnx'):
                                    file_path = os.path.join(detection_dir, file)
                                    if os.path.isfile(file_path):
                                        # 尝试多种路径格式
                                        path_formats = [
                                            f"{prefix}/{file}",  # 带前缀的路径
                                            file,  # 仅文件名
                                        ]
                                        for relative_path in path_formats:
                                            if 'vitpose' in file.lower() and relative_path not in available_vitpose:
                                                available_vitpose.append(relative_path)
                                            if 'yolo' in file.lower() and relative_path not in available_yolo:
                                                available_yolo.append(relative_path)
                    if available_vitpose or available_yolo:
                        logger.info(f"从文件系统扫描到的模型（后备）: vitpose={available_vitpose}, yolo={available_yolo}")
                except Exception as scan_error:
                    logger.warning(f"文件系统扫描失败: {scan_error}")
            
            # 尝试不同的路径格式（按优先级排序）
            vitpose_candidates = [
                "detection/vitpose_h_wholebody_model.onnx",  # detection 目录格式（ComfyUI 期望的格式）
                "onnx/vitpose_h_wholebody_model.onnx",  # workflow 中的格式
                "vitpose_h_wholebody_model.onnx",  # 直接文件名
            ]
            yolo_candidates = [
                "detection/yolov10m.onnx",  # detection 目录格式（ComfyUI 期望的格式）
                "onnx/yolov10m.onnx",  # workflow 中的格式
                "yolov10m.onnx",  # 直接文件名
            ]
            
            # 检查模型文件是否存在，并匹配可用模型列表
            vitpose_model = None
            yolo_model = None
            
            # 优先从可用模型列表中选择
            if available_vitpose:
                for candidate in vitpose_candidates:
                    # 检查完整路径或文件名匹配
                    for available in available_vitpose:
                        if candidate == available or candidate.endswith(available) or available.endswith(candidate):
                            vitpose_model = available
                            logger.info(f"从可用列表中选择 ViTPose 模型: {vitpose_model}")
                            break
                    if vitpose_model:
                        break
            
            # 如果列表中没有，尝试文件系统
            if not vitpose_model:
                for candidate in vitpose_candidates:
                    # 提取文件名（移除所有路径前缀）
                    file_name = candidate.split('/')[-1]
                    # 检查所有可能的路径
                    detection_path = f"/ComfyUI/models/detection/{file_name}"
                    onnx_path = f"/ComfyUI/models/onnx/{file_name}"
                    model_path = None
                    used_format = None
                    
                    # 优先检查 detection 目录（ComfyUI 期望的格式）
                    if os.path.exists(detection_path):
                        model_path = detection_path
                        used_format = f"detection/{file_name}"
                    elif os.path.exists(onnx_path):
                        model_path = onnx_path
                        used_format = candidate if 'detection' in candidate or 'onnx' in candidate else file_name
                    
                    if model_path:
                        # 如果可用列表为空，优先使用 detection/ 格式
                        if not available_vitpose:
                            vitpose_model = used_format if used_format else file_name
                            logger.info(f"可用列表为空，找到 ViTPose 模型文件: {model_path}, 使用格式: {vitpose_model}")
                        elif used_format in available_vitpose:
                            vitpose_model = used_format
                        elif file_name in available_vitpose:
                            vitpose_model = file_name
                        elif any(file_name in m or m in file_name for m in available_vitpose):
                            vitpose_model = next((m for m in available_vitpose if file_name in m or m in file_name), used_format)
                        else:
                            # 如果不在列表中，优先使用 detection/ 格式
                            vitpose_model = used_format if 'detection' in used_format else file_name
                            logger.warning(f"模型不在可用列表中，尝试使用格式: {vitpose_model}")
                        break
            
            if available_yolo:
                for candidate in yolo_candidates:
                    for available in available_yolo:
                        if candidate == available or candidate.endswith(available) or available.endswith(candidate):
                            yolo_model = available
                            logger.info(f"从可用列表中选择 YOLO 模型: {yolo_model}")
                            break
                    if yolo_model:
                        break
            
            if not yolo_model:
                for candidate in yolo_candidates:
                    # 提取文件名（移除所有路径前缀）
                    file_name = candidate.split('/')[-1]
                    # 检查所有可能的路径
                    detection_path = f"/ComfyUI/models/detection/{file_name}"
                    onnx_path = f"/ComfyUI/models/onnx/{file_name}"
                    model_path = None
                    used_format = None
                    
                    # 优先检查 detection 目录（ComfyUI 期望的格式）
                    if os.path.exists(detection_path):
                        model_path = detection_path
                        used_format = f"detection/{file_name}"
                    elif os.path.exists(onnx_path):
                        model_path = onnx_path
                        used_format = candidate if 'detection' in candidate or 'onnx' in candidate else file_name
                    
                    if model_path:
                        # 如果可用列表为空，优先使用 detection/ 格式
                        if not available_yolo:
                            yolo_model = used_format if used_format else file_name
                            logger.info(f"可用列表为空，找到 YOLO 模型文件: {model_path}, 使用格式: {yolo_model}")
                        elif used_format in available_yolo:
                            yolo_model = used_format
                        elif file_name in available_yolo:
                            yolo_model = file_name
                        elif any(file_name in m or m in file_name for m in available_yolo):
                            yolo_model = next((m for m in available_yolo if file_name in m or m in file_name), used_format)
                        else:
                            # 如果不在列表中，优先使用 detection/ 格式
                            yolo_model = used_format if 'detection' in used_format else file_name
                            logger.warning(f"模型不在可用列表中，尝试使用格式: {yolo_model}")
                        break
            
            # 如果找不到，使用可用列表中的第一个或默认路径格式
            if not vitpose_model:
                if available_vitpose:
                    vitpose_model = available_vitpose[0]
                    logger.info(f"使用可用列表中的第一个 ViTPose 模型: {vitpose_model}")
                else:
                    # 检查文件是否存在，优先使用 detection/ 格式
                    default_file = "vitpose_h_wholebody_model.onnx"
                    if os.path.exists(f"/ComfyUI/models/detection/{default_file}"):
                        vitpose_model = f"detection/{default_file}"
                        logger.info(f"使用默认 ViTPose 模型（detection格式）: {vitpose_model}")
                    elif os.path.exists(f"/ComfyUI/models/onnx/{default_file}"):
                        vitpose_model = f"detection/{default_file}"  # 即使文件在 onnx，也使用 detection/ 格式
                        logger.info(f"使用默认 ViTPose 模型（detection格式）: {vitpose_model}")
                    else:
                        vitpose_model = f"detection/{default_file}"  # 默认使用 detection/ 格式
                        logger.warning(f"ViTPose 模型文件不存在，使用默认格式: {vitpose_model}")
            
            if not yolo_model:
                if available_yolo:
                    yolo_model = available_yolo[0]
                    logger.info(f"使用可用列表中的第一个 YOLO 模型: {yolo_model}")
                else:
                    # 检查文件是否存在，优先使用 detection/ 格式
                    default_file = "yolov10m.onnx"
                    if os.path.exists(f"/ComfyUI/models/detection/{default_file}"):
                        yolo_model = f"detection/{default_file}"
                        logger.info(f"使用默认 YOLO 模型（detection格式）: {yolo_model}")
                    elif os.path.exists(f"/ComfyUI/models/onnx/{default_file}"):
                        yolo_model = f"detection/{default_file}"  # 即使文件在 onnx，也使用 detection/ 格式
                        logger.info(f"使用默认 YOLO 模型（detection格式）: {yolo_model}")
                    else:
                        yolo_model = f"detection/{default_file}"  # 默认使用 detection/ 格式
                        logger.warning(f"YOLO 模型文件不存在，使用默认格式: {yolo_model}")
            
            if "widgets_values" in prompt["129"]:
                widgets = prompt["129"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = vitpose_model
                if len(widgets) >= 2:
                    widgets[1] = yolo_model
            if "inputs" not in prompt["129"]:
                prompt["129"]["inputs"] = {}
            prompt["129"]["inputs"]["vitpose_model"] = vitpose_model
            prompt["129"]["inputs"]["yolo_model"] = yolo_model
            logger.info(f"节点129 (OnnxDetectionModelLoader): vitpose={vitpose_model}, yolo={yolo_model}")
        
        # 节点 65: WanVideoClipVisionEncode (CLIP Vision 编码 - 用于节点63)
        # 确保必需的输入连接存在
        if "65" in prompt:
            if "inputs" not in prompt["65"]:
                prompt["65"]["inputs"] = {}
            
            # clip_vision 来自节点128 (GetNode "clip_vision") -> 节点106 (SetNode "clip_vision") -> 节点59 (CLIPVisionLoader)
            if "clip_vision" not in prompt["65"]["inputs"] or prompt["65"]["inputs"]["clip_vision"] is None:
                if "59" in prompt:
                    prompt["65"]["inputs"]["clip_vision"] = ["59", 0]
                    logger.info(f"节点65: 修复 clip_vision 输入 = ['59', 0]")
                else:
                    logger.error(f"节点65: 缺少节点59 (CLIPVisionLoader)，无法设置 clip_vision 输入")
            
            # image_1 来自节点96 (SetNode "start_frame") -> 节点68 (ImageResizeKJv2) -> 节点76 (LoadImage)
            if "image_1" not in prompt["65"]["inputs"] or prompt["65"]["inputs"]["image_1"] is None:
                if "68" in prompt:
                    prompt["65"]["inputs"]["image_1"] = ["68", 0]
                    logger.info(f"节点65: 修复 image_1 输入 = ['68', 0]")
                elif "76" in prompt:
                    prompt["65"]["inputs"]["image_1"] = ["76", 0]
                    logger.info(f"节点65: 修复 image_1 输入 = ['76', 0]")
                else:
                    logger.error(f"节点65: 缺少节点68或76，无法设置 image_1 输入")
            
            logger.info(f"节点65 (WanVideoClipVisionEncode): clip_vision={prompt['65']['inputs'].get('clip_vision')}, image_1={prompt['65']['inputs'].get('image_1')}")
        
        # 节点 82: WanVideoClipVisionEncode (CLIP Vision 编码 - 用于节点71)
        # 确保必需的输入连接存在
        if "82" in prompt:
            if "inputs" not in prompt["82"]:
                prompt["82"]["inputs"] = {}
            
            # clip_vision 来自节点107 (GetNode "clip_vision") -> 节点106 (SetNode "clip_vision") -> 节点59 (CLIPVisionLoader)
            if "clip_vision" not in prompt["82"]["inputs"] or prompt["82"]["inputs"]["clip_vision"] is None:
                if "59" in prompt:
                    prompt["82"]["inputs"]["clip_vision"] = ["59", 0]
                    logger.info(f"节点82: 修复 clip_vision 输入 = ['59', 0]")
                else:
                    logger.error(f"节点82: 缺少节点59 (CLIPVisionLoader)，无法设置 clip_vision 输入")
            
            # image_1 来自节点81 (GetImageRangeFromBatch) -> 节点113 (SetNode "poses") -> 节点77 (ImageResizeKJv2)
            if "image_1" not in prompt["82"]["inputs"] or prompt["82"]["inputs"]["image_1"] is None:
                if "81" in prompt:
                    prompt["82"]["inputs"]["image_1"] = ["81", 0]
                    logger.info(f"节点82: 修复 image_1 输入 = ['81', 0]")
                elif "77" in prompt:
                    prompt["82"]["inputs"]["image_1"] = ["77", 0]
                    logger.info(f"节点82: 修复 image_1 输入 = ['77', 0]")
                else:
                    logger.error(f"节点82: 缺少节点81或77，无法设置 image_1 输入")
            
            logger.info(f"节点82 (WanVideoClipVisionEncode): clip_vision={prompt['82']['inputs'].get('clip_vision')}, image_1={prompt['82']['inputs'].get('image_1')}")
        
        # 节点 81: GetImageRangeFromBatch (从批次中获取图像范围)
        # 确保必需的输入连接存在
        if "81" in prompt:
            if "inputs" not in prompt["81"]:
                prompt["81"]["inputs"] = {}
            
            # images 来自节点113 (SetNode "poses") -> 节点77 (ImageResizeKJv2) -> 节点130 (PoseDetectionOneToAllAnimation)
            if "images" not in prompt["81"]["inputs"] or prompt["81"]["inputs"]["images"] is None:
                if "77" in prompt:
                    prompt["81"]["inputs"]["images"] = ["77", 0]
                    logger.info(f"节点81: 修复 images 输入 = ['77', 0]")
                elif "130" in prompt:
                    prompt["81"]["inputs"]["images"] = ["130", 0]
                    logger.info(f"节点81: 修复 images 输入 = ['130', 0]")
                else:
                    logger.error(f"节点81: 缺少节点77或130，无法设置 images 输入")
            
            logger.info(f"节点81 (GetImageRangeFromBatch): images={prompt['81']['inputs'].get('images')}")
        
        # 节点 72: WanVideoEncode (VAE 编码)
        # 确保必需的输入连接存在
        if "72" in prompt:
            if "inputs" not in prompt["72"]:
                prompt["72"]["inputs"] = {}
            
            # image 来自节点113 (SetNode "poses") -> 节点77 (ImageResizeKJv2) -> 节点130 (PoseDetectionOneToAllAnimation)
            if "image" not in prompt["72"]["inputs"] or prompt["72"]["inputs"]["image"] is None:
                if "77" in prompt:
                    prompt["72"]["inputs"]["image"] = ["77", 0]
                    logger.info(f"节点72: 修复 image 输入 = ['77', 0]")
                elif "130" in prompt:
                    prompt["72"]["inputs"]["image"] = ["130", 0]
                    logger.info(f"节点72: 修复 image 输入 = ['130', 0]")
                else:
                    logger.error(f"节点72: 缺少节点77或130，无法设置 image 输入")
            
            # vae 来自节点112 (GetNode "VAE") -> 节点116 (GetNode "VAE") -> 节点38 (WanVideoVAELoader)
            if "vae" not in prompt["72"]["inputs"] or prompt["72"]["inputs"]["vae"] is None:
                if "38" in prompt:
                    prompt["72"]["inputs"]["vae"] = ["38", 0]
                    logger.info(f"节点72: 修复 vae 输入 = ['38', 0]")
                else:
                    logger.error(f"节点72: 缺少节点38 (WanVideoVAELoader)，无法设置 vae 输入")
            
            logger.info(f"节点72 (WanVideoEncode): image={prompt['72']['inputs'].get('image')}, vae={prompt['72']['inputs'].get('vae')}")
        
        # 节点 71: WanVideoAddSteadyDancerEmbeds (添加 SteadyDancer 嵌入)
        # 确保必需的输入连接存在
        if "71" in prompt:
            if "inputs" not in prompt["71"]:
                prompt["71"]["inputs"] = {}
            
            # embeds 来自节点63 (WanVideoImageToVideoEncode) 的输出
            if "embeds" not in prompt["71"]["inputs"] or prompt["71"]["inputs"]["embeds"] is None:
                if "63" in prompt:
                    prompt["71"]["inputs"]["embeds"] = ["63", 0]
                    logger.info(f"节点71: 修复 embeds 输入 = ['63', 0]")
                else:
                    logger.error(f"节点71: 缺少节点63 (WanVideoImageToVideoEncode)，无法设置 embeds 输入")
            
            # pose_latents_positive 来自节点72 (WanVideoEncode) 的输出
            if "pose_latents_positive" not in prompt["71"]["inputs"] or prompt["71"]["inputs"]["pose_latents_positive"] is None:
                if "72" in prompt:
                    prompt["71"]["inputs"]["pose_latents_positive"] = ["72", 0]
                    logger.info(f"节点71: 修复 pose_latents_positive 输入 = ['72', 0]")
                else:
                    logger.error(f"节点71: 缺少节点72 (WanVideoEncode)，无法设置 pose_latents_positive 输入")
            
            # clip_vision_embeds 来自节点82 (WanVideoClipVisionEncode) 的输出
            if "clip_vision_embeds" not in prompt["71"]["inputs"] or prompt["71"]["inputs"]["clip_vision_embeds"] is None:
                if "82" in prompt:
                    prompt["71"]["inputs"]["clip_vision_embeds"] = ["82", 0]
                    logger.info(f"节点71: 修复 clip_vision_embeds 输入 = ['82', 0]")
                else:
                    logger.error(f"节点71: 缺少节点82 (WanVideoClipVisionEncode)，无法设置 clip_vision_embeds 输入")
            
            logger.info(f"节点71 (WanVideoAddSteadyDancerEmbeds): embeds={prompt['71']['inputs'].get('embeds')}, pose_latents_positive={prompt['71']['inputs'].get('pose_latents_positive')}, clip_vision_embeds={prompt['71']['inputs'].get('clip_vision_embeds')}")
        
        # 节点 130: PoseDetectionOneToAllAnimation (姿态检测) - 必须在节点129之后
        # 确保必需的输入连接存在
        if "130" in prompt:
            if "inputs" not in prompt["130"]:
                prompt["130"]["inputs"] = {}
            
            # 确保 model 输入存在 (来自节点129)
            if "model" not in prompt["130"]["inputs"] or prompt["130"]["inputs"]["model"] is None:
                if "129" in prompt:
                    prompt["130"]["inputs"]["model"] = ["129", 0]
                    logger.info(f"节点130: 修复 model 输入 = ['129', 0]")
                else:
                    logger.error(f"节点130: 缺少节点129 (OnnxDetectionModelLoader)，无法设置 model 输入")
            
            # 确保 images 输入存在 (来自节点91)
            if "images" not in prompt["130"]["inputs"] or prompt["130"]["inputs"]["images"] is None:
                if "91" in prompt:
                    prompt["130"]["inputs"]["images"] = ["91", 0]
                    logger.info(f"节点130: 修复 images 输入 = ['91', 0]")
                else:
                    logger.error(f"节点130: 缺少节点91 (GetImageSizeAndCount)，无法设置 images 输入")
            
            # 设置 width 和 height
            if "width" not in prompt["130"]["inputs"] or prompt["130"]["inputs"]["width"] is None:
                prompt["130"]["inputs"]["width"] = adjusted_width
            if "height" not in prompt["130"]["inputs"] or prompt["130"]["inputs"]["height"] is None:
                prompt["130"]["inputs"]["height"] = adjusted_height
            
            logger.info(f"节点130 (PoseDetectionOneToAllAnimation): model={prompt['130']['inputs'].get('model')}, images={prompt['130']['inputs'].get('images')}, width={adjusted_width}, height={adjusted_height}")
        
        # 节点 70: WanVideoSetBlockSwap - 确保model输入存在
        if "70" in prompt:
            if "inputs" not in prompt["70"]:
                prompt["70"]["inputs"] = {}
            
            # 确保 model 输入存在 (来自节点22)
            if "model" not in prompt["70"]["inputs"] or prompt["70"]["inputs"]["model"] is None:
                if "22" in prompt:
                    prompt["70"]["inputs"]["model"] = ["22", 0]
                    logger.info(f"节点70: 修复 model 输入 = ['22', 0]")
                else:
                    logger.error(f"节点70: 缺少节点22 (WanVideoModelLoader)，无法设置 model 输入")
            
            # 确保 block_swap_args 输入存在 (来自节点39)
            if "block_swap_args" not in prompt["70"]["inputs"] or prompt["70"]["inputs"]["block_swap_args"] is None:
                if "39" in prompt:
                    prompt["70"]["inputs"]["block_swap_args"] = ["39", 0]
                    logger.info(f"节点70: 修复 block_swap_args 输入 = ['39', 0]")
                else:
                    logger.error(f"节点70: 缺少节点39 (WanVideoBlockSwap)，无法设置 block_swap_args 输入")
            
            logger.info(f"节点70 (WanVideoSetBlockSwap): model={prompt['70']['inputs'].get('model')}, block_swap_args={prompt['70']['inputs'].get('block_swap_args')}")
        
        # 节点 63: WanVideoImageToVideoEncode (图像编码)
        # widgets_values 格式: [width, height, num_frames, noise_aug_strength, start_latent_strength, end_latent_strength, force_offload, fun_or_fl2v_model, tiled_vae, augment_empty_frames]
        if "63" in prompt:
            if "widgets_values" in prompt["63"]:
                widgets = prompt["63"]["widgets_values"]
                # 确保列表长度足够，索引从0开始，所以需要 len >= index + 1
                if len(widgets) >= 1:
                    widgets[0] = adjusted_width  # width
                if len(widgets) >= 2:
                    widgets[1] = adjusted_height  # height
                if len(widgets) >= 3:
                    widgets[2] = length  # num_frames
            if "inputs" not in prompt["63"]:
                prompt["63"]["inputs"] = {}
            
            # clip_embeds 来自节点65 (WanVideoClipVisionEncode) 的输出
            if "clip_embeds" not in prompt["63"]["inputs"] or prompt["63"]["inputs"]["clip_embeds"] is None:
                if "65" in prompt:
                    prompt["63"]["inputs"]["clip_embeds"] = ["65", 0]
                    logger.info(f"节点63: 修复 clip_embeds 输入 = ['65', 0]")
                else:
                    logger.error(f"节点63: 缺少节点65 (WanVideoClipVisionEncode)，无法设置 clip_embeds 输入")
            
            # start_image 来自节点96 (SetNode "start_frame") -> 节点68 (ImageResizeKJv2)
            if "start_image" not in prompt["63"]["inputs"] or prompt["63"]["inputs"]["start_image"] is None:
                if "68" in prompt:
                    prompt["63"]["inputs"]["start_image"] = ["68", 0]
                    logger.info(f"节点63: 修复 start_image 输入 = ['68', 0]")
                elif "76" in prompt:
                    prompt["63"]["inputs"]["start_image"] = ["76", 0]
                    logger.info(f"节点63: 修复 start_image 输入 = ['76', 0]")
                else:
                    logger.error(f"节点63: 缺少节点68或76，无法设置 start_image 输入")
            
            # vae 来自节点116 (GetNode "VAE") -> 节点38 (WanVideoVAELoader)
            if "vae" not in prompt["63"]["inputs"] or prompt["63"]["inputs"]["vae"] is None:
                if "38" in prompt:
                    prompt["63"]["inputs"]["vae"] = ["38", 0]
                    logger.info(f"节点63: 修复 vae 输入 = ['38', 0]")
                else:
                    logger.error(f"节点63: 缺少节点38 (WanVideoVAELoader)，无法设置 vae 输入")
            
            prompt["63"]["inputs"]["width"] = adjusted_width
            prompt["63"]["inputs"]["height"] = adjusted_height
            prompt["63"]["inputs"]["num_frames"] = length
            logger.info(f"节点63 (WanVideoImageToVideoEncode): width={adjusted_width}, height={adjusted_height}, num_frames={length}, clip_embeds={prompt['63']['inputs'].get('clip_embeds')}, start_image={prompt['63']['inputs'].get('start_image')}, vae={prompt['63']['inputs'].get('vae')}")
        
        # 节点 68: ImageResizeKJv2 (图像尺寸调整)
        if "68" in prompt:
            if "widgets_values" in prompt["68"]:
                widgets = prompt["68"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = adjusted_width  # width
                if len(widgets) >= 2:
                    widgets[1] = adjusted_height  # height
            if "inputs" not in prompt["68"]:
                prompt["68"]["inputs"] = {}
            prompt["68"]["inputs"]["width"] = adjusted_width
            prompt["68"]["inputs"]["height"] = adjusted_height
            logger.info(f"节点68 (ImageResizeKJv2): width={adjusted_width}, height={adjusted_height}")
        
        # 节点 77: ImageResizeKJv2 (姿态图像尺寸调整)
        # 注意：节点77的image输入来自节点130的输出，width和height来自GetNode
        # 如果链接解析失败，这里设置默认值作为后备
        if "77" in prompt:
            if "widgets_values" in prompt["77"]:
                widgets = prompt["77"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = adjusted_width  # width
                if len(widgets) >= 2:
                    widgets[1] = adjusted_height  # height
            if "inputs" not in prompt["77"]:
                prompt["77"]["inputs"] = {}
            # 如果width和height没有通过链接设置，使用调整后的值
            if "width" not in prompt["77"]["inputs"] or prompt["77"]["inputs"]["width"] is None:
                prompt["77"]["inputs"]["width"] = adjusted_width
            if "height" not in prompt["77"]["inputs"] or prompt["77"]["inputs"]["height"] is None:
                prompt["77"]["inputs"]["height"] = adjusted_height
            logger.info(f"节点77 (ImageResizeKJv2): width={prompt['77']['inputs'].get('width')}, height={prompt['77']['inputs'].get('height')}")
        
        # 节点 87: WanVideoContextOptions (上下文选项)
        if "87" in prompt:
            context_frames = job_input.get("context_frames", 81)
            context_stride = job_input.get("context_stride", 4)
            context_overlap = job_input.get("context_overlap", 16)
            if "widgets_values" in prompt["87"]:
                widgets = prompt["87"]["widgets_values"]
                if len(widgets) >= 2:
                    widgets[1] = context_frames
                if len(widgets) >= 3:
                    widgets[2] = context_stride
                if len(widgets) >= 4:
                    widgets[3] = context_overlap
            if "inputs" not in prompt["87"]:
                prompt["87"]["inputs"] = {}
            prompt["87"]["inputs"]["context_frames"] = context_frames
            prompt["87"]["inputs"]["context_stride"] = context_stride
            prompt["87"]["inputs"]["context_overlap"] = context_overlap
            logger.info(f"节点87 (WanVideoContextOptions): context_frames={context_frames}, context_stride={context_stride}, context_overlap={context_overlap}")
        
        # 节点 119: WanVideoSamplerSettings (采样器设置)
        # 注意：cfg 和 seed 是通过链接传递的（来自 PrimitiveNode 123 和 124），不应该在 widgets_values 中
        # widgets_values 只包含有 widget 的输入，顺序为：steps, shift, force_offload, batched_cfg, scheduler, riflex_freq_index, denoise_strength, add_noise_to_samples, rope_function, start_step, end_step, ...
        if "119" in prompt:
            if "widgets_values" in prompt["119"]:
                widgets = prompt["119"]["widgets_values"]
                # 确保列表长度足够
                if len(widgets) < 14:
                    widgets.extend([None] * (14 - len(widgets)))
                # 只更新有 widget 的输入（cfg 和 seed 通过链接传递，不在 widgets_values 中）
                if len(widgets) >= 1:
                    widgets[0] = steps  # steps (widget)
                if len(widgets) >= 2:
                    widgets[1] = shift  # shift (widget)，不是 cfg
                # widgets[2] = force_offload (保持原值或使用默认值)
                # widgets[3] = batched_cfg (保持原值或使用默认值)
                if len(widgets) >= 5:
                    # scheduler 通过链接传递，但如果有 widget 也更新
                    pass
                # 确保 rope_function 是字符串，不是布尔值或错误的值
                if len(widgets) >= 9:
                    if widgets[8] is None or widgets[8] == False or widgets[8] == "False":
                        widgets[8] = "comfy"  # rope_function 默认值
                # 确保 start_step 是整数
                if len(widgets) >= 10:
                    if widgets[9] is None or not isinstance(widgets[9], int):
                        try:
                            widgets[9] = int(widgets[9]) if widgets[9] is not None else 0
                        except (ValueError, TypeError):
                            widgets[9] = 0  # start_step 默认值
                # 确保 riflex_freq_index 是整数
                if len(widgets) >= 6:
                    if widgets[5] is None or not isinstance(widgets[5], int):
                        try:
                            widgets[5] = int(widgets[5]) if widgets[5] is not None else 0
                        except (ValueError, TypeError):
                            widgets[5] = 0  # riflex_freq_index 默认值
            if "inputs" not in prompt["119"]:
                prompt["119"]["inputs"] = {}
            prompt["119"]["inputs"]["steps"] = steps
            prompt["119"]["inputs"]["cfg"] = cfg  # 通过链接传递
            prompt["119"]["inputs"]["shift"] = shift
            prompt["119"]["inputs"]["seed"] = seed  # 通过链接传递
            
            # 确保 scheduler 输入存在 (来自节点122)
            if "scheduler" not in prompt["119"]["inputs"] or prompt["119"]["inputs"]["scheduler"] is None:
                if "122" in prompt:
                    prompt["119"]["inputs"]["scheduler"] = ["122", 3]  # scheduler是节点122的第4个输出(索引3)
                    logger.info(f"节点119: 修复 scheduler 输入 = ['122', 3]")
                else:
                    # 如果节点122不存在，直接使用scheduler值
                    prompt["119"]["inputs"]["scheduler"] = scheduler
                    logger.info(f"节点119: 使用直接值 scheduler = {scheduler}")
            
            # 确保 image_embeds 输入存在 (来自节点71)
            if "image_embeds" not in prompt["119"]["inputs"] or prompt["119"]["inputs"]["image_embeds"] is None:
                if "71" in prompt:
                    prompt["119"]["inputs"]["image_embeds"] = ["71", 0]
                    logger.info(f"节点119: 修复 image_embeds 输入 = ['71', 0]")
                else:
                    logger.error(f"节点119: 缺少节点71 (WanVideoAddSteadyDancerEmbeds)，无法设置 image_embeds 输入")
            
            # 确保 rope_function 是字符串，不是布尔值
            if "rope_function" not in prompt["119"]["inputs"] or prompt["119"]["inputs"]["rope_function"] == False or prompt["119"]["inputs"]["rope_function"] == "False":
                prompt["119"]["inputs"]["rope_function"] = "comfy"  # 默认值
            # 确保 start_step 是整数
            if "start_step" in prompt["119"]["inputs"]:
                try:
                    prompt["119"]["inputs"]["start_step"] = int(prompt["119"]["inputs"]["start_step"])
                except (ValueError, TypeError):
                    prompt["119"]["inputs"]["start_step"] = 0
            # 确保 riflex_freq_index 是整数
            if "riflex_freq_index" in prompt["119"]["inputs"]:
                try:
                    prompt["119"]["inputs"]["riflex_freq_index"] = int(prompt["119"]["inputs"]["riflex_freq_index"])
                except (ValueError, TypeError):
                    prompt["119"]["inputs"]["riflex_freq_index"] = 0
            logger.info(f"节点119 (WanVideoSamplerSettings): steps={steps}, cfg={cfg}, shift={shift}, seed={seed}, scheduler={prompt['119']['inputs'].get('scheduler')}, image_embeds={prompt['119']['inputs'].get('image_embeds')}, rope_function={prompt['119']['inputs'].get('rope_function', 'comfy')}")
        
        # 节点 122: WanVideoScheduler (调度器)
        if "122" in prompt:
            if "widgets_values" in prompt["122"]:
                widgets = prompt["122"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = scheduler
                if len(widgets) >= 2:
                    widgets[1] = steps
                if len(widgets) >= 3:
                    widgets[2] = shift
            if "inputs" not in prompt["122"]:
                prompt["122"]["inputs"] = {}
            prompt["122"]["inputs"]["scheduler"] = scheduler
            prompt["122"]["inputs"]["steps"] = steps
            prompt["122"]["inputs"]["shift"] = shift
            logger.info(f"节点122 (WanVideoScheduler): scheduler={scheduler}, steps={steps}, shift={shift}")
        
        # 节点 123: PrimitiveNode (cfg)
        # 注意：PrimitiveNode 节点会在节点转换时被跳过，但值会通过链接直接传递到目标节点
        # 这里保留配置代码是为了确保值在转换前已设置（用于链接解析）
        if "123" in prompt:
            if "widgets_values" in prompt["123"]:
                prompt["123"]["widgets_values"][0] = cfg
            if "inputs" not in prompt["123"]:
                prompt["123"]["inputs"] = {}
            prompt["123"]["inputs"]["cfg"] = cfg
        
        # 节点 124: PrimitiveNode (seed)
        # 注意：PrimitiveNode 节点会在节点转换时被跳过，但值会通过链接直接传递到目标节点
        # 这里保留配置代码是为了确保值在转换前已设置（用于链接解析）
        if "124" in prompt:
            if "widgets_values" in prompt["124"]:
                prompt["124"]["widgets_values"][0] = seed
            if "inputs" not in prompt["124"]:
                prompt["124"]["inputs"] = {}
            prompt["124"]["inputs"]["seed"] = seed
        
        # 节点 83: VHS_VideoCombine (输出视频)
        if "83" in prompt:
            if "widgets_values" in prompt["83"]:
                widgets = prompt["83"]["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["frame_rate"] = job_input.get("frame_rate", 24)
                    widgets["filename_prefix"] = job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer")
                    widgets["format"] = job_input.get("format", "video/h264-mp4")
                    widgets["save_output"] = True
            if "inputs" not in prompt["83"]:
                prompt["83"]["inputs"] = {}
            prompt["83"]["inputs"]["frame_rate"] = job_input.get("frame_rate", 24)
            prompt["83"]["inputs"]["filename_prefix"] = job_input.get("filename_prefix", "WanVideoWrapper_SteadyDancer")
            prompt["83"]["inputs"]["format"] = job_input.get("format", "video/h264-mp4")
            prompt["83"]["inputs"]["save_output"] = True
            logger.info(f"节点83 (VHS_VideoCombine): frame_rate={job_input.get('frame_rate', 24)}, filename_prefix={job_input.get('filename_prefix', 'WanVideoWrapper_SteadyDancer')}")
        
        # 节点 117: VHS_VideoCombine (姿态检测视频 - 仅用于预览，不输出)
        # 确保节点 117 不输出视频文件，只使用节点 83 的输出
        if "117" in prompt:
            if "widgets_values" in prompt["117"]:
                widgets = prompt["117"]["widgets_values"]
                if isinstance(widgets, dict):
                    widgets["save_output"] = False
            if "inputs" not in prompt["117"]:
                prompt["117"]["inputs"] = {}
            prompt["117"]["inputs"]["save_output"] = False
            logger.info(f"节点117 (VHS_VideoCombine - 姿态视频): save_output=False (不输出文件，仅用于预览)")
        
        # 节点 130: PoseDetectionOneToAllAnimation (姿态检测)
        if "130" in prompt:
            # 使用调整后的尺寸，确保与视频生成尺寸一致
            pose_width = adjusted_width
            pose_height = adjusted_height
            align_to = job_input.get("align_to", "ref")
            draw_face_points = job_input.get("draw_face_points", "weak")
            draw_head = job_input.get("draw_head", "full")
            if "widgets_values" in prompt["130"]:
                widgets = prompt["130"]["widgets_values"]
                if len(widgets) >= 1:
                    widgets[0] = pose_width
                if len(widgets) >= 2:
                    widgets[1] = pose_height
                if len(widgets) >= 3:
                    widgets[2] = align_to
                if len(widgets) >= 4:
                    widgets[3] = draw_face_points
                if len(widgets) >= 5:
                    widgets[4] = draw_head
            if "inputs" not in prompt["130"]:
                prompt["130"]["inputs"] = {}
            prompt["130"]["inputs"]["width"] = pose_width
            prompt["130"]["inputs"]["height"] = pose_height
            prompt["130"]["inputs"]["align_to"] = align_to
            prompt["130"]["inputs"]["draw_face_points"] = draw_face_points
            prompt["130"]["inputs"]["draw_head"] = draw_head
            logger.info(f"节点130 (PoseDetectionOneToAllAnimation): width={pose_width}, height={pose_height}, align_to={align_to}, draw_face_points={draw_face_points}, draw_head={draw_head}")
    else:
        # 标准 workflow (new_Wan22_api.json) 节点配置
        prompt["244"]["inputs"]["image"] = image_path
        prompt["541"]["inputs"]["num_frames"] = length
        # 当有输入图像时，必须设置 fun_or_fl2v_model 为 true 以支持 I2V 模式
        if image_path and "541" in prompt and "inputs" in prompt["541"]:
            # 强制设置为布尔值 True，确保JSON序列化正确
            prompt["541"]["inputs"]["fun_or_fl2v_model"] = True
            # 验证设置是否成功
            actual_value = prompt["541"]["inputs"].get("fun_or_fl2v_model")
            logger.info(f"已设置 fun_or_fl2v_model = {actual_value} (类型: {type(actual_value).__name__}) 以支持 I2V 模式")
        prompt["135"]["inputs"]["positive_prompt"] = positive_prompt
        prompt["220"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["seed"] = seed
        prompt["540"]["inputs"]["cfg"] = cfg
        prompt["235"]["inputs"]["value"] = adjusted_width
        prompt["236"]["inputs"]["value"] = adjusted_height
    
    if not is_mega_model and not use_steadydancer:
        # 标准 workflow 的 context_overlap 和 steps 设置
        # context_overlap 动态调整：确保不超过总帧数，且对短视频使用更保守的值
        user_overlap = job_input.get("context_overlap")
        if user_overlap is not None:
            # 用户指定了值，但需要确保不超过总帧数
            context_overlap = min(user_overlap, length - 1) if length > 1 else 0
            if user_overlap != context_overlap:
                logger.warning(f"context_overlap {user_overlap} exceeds length {length}, adjusted to {context_overlap}")
        else:
            # 自动计算：对于短视频使用更小的值
            if length < 50:
                # 短视频：最多 30% 或 0，取较小值
                context_overlap = min(0, max(1, int(length * 0.3)))
            else:
                # 长视频：最多 60% 或 48，取较小值
                context_overlap = min(48, max(0, int(length * 0.6)))
            logger.info(f"Auto-calculated context_overlap: {context_overlap} for length: {length}")
        
        if "498" in prompt:
            prompt["498"]["inputs"]["context_overlap"] = context_overlap
        
        # step 설정 적용
        # 节点 569: steps (INTConstant) - 默认值是 4
        if "569" in prompt:
            prompt["569"]["inputs"]["value"] = steps
            logger.info(f"节点569 (Steps): {steps}")
        # 节点 575: start_step (INTConstant) - 默认值是 4
        if "575" in prompt:
            # start_step 应该是 steps 的一部分，默认保持为 4
            start_step = 4 if steps >= 4 else steps
            prompt["575"]["inputs"]["value"] = start_step
            logger.info(f"节点575 (StartStep): {start_step}")

        # 엔드 이미지가 있는 경우 617번 노드에 경로 적용 (FLF2V 전용)
        if end_image_path_local and "617" in prompt:
            prompt["617"]["inputs"]["image"] = end_image_path_local
    
    # LoRA 설정 적용
    if lora_count > 0:
        if is_mega_model:
            # RapidAIO Mega (V2.5).json 可能不支持 LoRA，记录警告
            logger.warning(f"Rapid-AIO-Mega workflow 不支持 LoRA 设置，已忽略 {lora_count} 个 LoRA pairs")
        else:
            # 标准 workflow 的 LoRA 设置 - HIGH LoRA는 노드 279, LOW LoRA는 노드 553
            high_lora_node_id = "279"
            low_lora_node_id = "553"
            
            # 입력받은 LoRA pairs 적용 (lora_1부터 시작)
            for i, lora_pair in enumerate(lora_pairs):
                if i < 4:  # 최대 4개까지만
                    lora_high = lora_pair.get("high")
                    lora_low = lora_pair.get("low")
                    lora_high_weight = lora_pair.get("high_weight", 1.0)
                    lora_low_weight = lora_pair.get("low_weight", 1.0)
                    
                    # HIGH LoRA 설정 (노드 279번, lora_0부터 시작)
                    if lora_high and high_lora_node_id in prompt:
                        prompt[high_lora_node_id]["inputs"][f"lora_{i}"] = lora_high
                        prompt[high_lora_node_id]["inputs"][f"strength_{i}"] = lora_high_weight
                        logger.info(f"LoRA {i+1} HIGH applied to node 279: {lora_high} with weight {lora_high_weight}")
                    
                    # LOW LoRA 설정 (노드 553번, lora_0부터 시작)
                    if lora_low and low_lora_node_id in prompt:
                        prompt[low_lora_node_id]["inputs"][f"lora_{i}"] = lora_low
                        prompt[low_lora_node_id]["inputs"][f"strength_{i}"] = lora_low_weight
                        logger.info(f"LoRA {i+1} LOW applied to node 553: {lora_low} with weight {lora_low_weight}")

    # 验证关键参数设置 - 无条件输出验证信息
    logger.info("=" * 60)
    logger.info("验证关键节点配置:")
    
    if use_steadydancer:
        # SteadyDancer workflow 验证
        if "76" in prompt:
            if "inputs" in prompt["76"]:
                image_in_76 = prompt["76"]["inputs"].get("image")
                logger.info(f"✓ 节点76 (LoadImage): {image_in_76}")
            else:
                logger.warning("✗ 节点76 缺少 inputs")
        if "75" in prompt:
            if "inputs" in prompt["75"]:
                video_in_75 = prompt["75"]["inputs"].get("video")
                logger.info(f"✓ 节点75 (VHS_LoadVideo): {video_in_75}")
            else:
                logger.warning("✗ 节点75 缺少 inputs")
        if "92" in prompt:
            if "inputs" in prompt["92"]:
                pos_prompt = prompt["92"]["inputs"].get("positive_prompt", "")
                logger.info(f"✓ 节点92 (WanVideoTextEncodeCached): positive='{pos_prompt[:50] if pos_prompt else ''}...'")
            else:
                logger.warning("✗ 节点92 缺少 inputs")
        if "22" in prompt:
            if "inputs" in prompt["22"]:
                model_in_22 = prompt["22"]["inputs"].get("model")
                logger.info(f"✓ 节点22 (WanVideoModelLoader): {model_in_22}")
            else:
                logger.warning("✗ 节点22 缺少 inputs")
        if "63" in prompt:
            if "inputs" in prompt["63"]:
                width_63 = prompt["63"]["inputs"].get("width")
                height_63 = prompt["63"]["inputs"].get("height")
                num_frames_63 = prompt["63"]["inputs"].get("num_frames")
                clip_embeds_63 = prompt["63"]["inputs"].get("clip_embeds")
                start_image_63 = prompt["63"]["inputs"].get("start_image")
                vae_63 = prompt["63"]["inputs"].get("vae")
                logger.info(f"✓ 节点63 (WanVideoImageToVideoEncode): width={width_63}, height={height_63}, num_frames={num_frames_63}, clip_embeds={'已设置' if clip_embeds_63 else '未设置'}, start_image={'已设置' if start_image_63 else '未设置'}, vae={'已设置' if vae_63 else '未设置'}")
            else:
                logger.warning("✗ 节点63 缺少 inputs")
        if "68" in prompt:
            if "inputs" in prompt["68"]:
                width_68 = prompt["68"]["inputs"].get("width")
                height_68 = prompt["68"]["inputs"].get("height")
                logger.info(f"✓ 节点68 (ImageResizeKJv2): width={width_68}, height={height_68}")
            else:
                logger.warning("✗ 节点68 缺少 inputs")
        if "77" in prompt:
            if "inputs" in prompt["77"]:
                width_77 = prompt["77"]["inputs"].get("width")
                height_77 = prompt["77"]["inputs"].get("height")
                image_77 = prompt["77"]["inputs"].get("image")
                logger.info(f"✓ 节点77 (ImageResizeKJv2): width={width_77}, height={height_77}, image={'已设置' if image_77 else '未设置'}")
            else:
                logger.warning("✗ 节点77 缺少 inputs")
        if "28" in prompt:
            if "inputs" in prompt["28"]:
                vae_28 = prompt["28"]["inputs"].get("vae")
                samples_28 = prompt["28"]["inputs"].get("samples")
                logger.info(f"✓ 节点28 (WanVideoDecode): vae={'已设置' if vae_28 else '未设置'}, samples={'已设置' if samples_28 else '未设置'}")
            else:
                logger.warning("✗ 节点28 缺少 inputs")
        if "79" in prompt:
            if "inputs" in prompt["79"]:
                image_1_79 = prompt["79"]["inputs"].get("image_1")
                image_2_79 = prompt["79"]["inputs"].get("image_2")
                logger.info(f"✓ 节点79 (ImageConcatMulti): image_1={'已设置' if image_1_79 else '未设置'}, image_2={'已设置' if image_2_79 else '未设置'}")
            else:
                logger.warning("✗ 节点79 缺少 inputs")
        if "131" in prompt:
            if "inputs" in prompt["131"]:
                images_131 = prompt["131"]["inputs"].get("images")
                logger.info(f"✓ 节点131 (PreviewImage): images={'已设置' if images_131 else '未设置'}")
            else:
                logger.warning("✗ 节点131 缺少 inputs")
        if "83" in prompt:
            if "inputs" in prompt["83"]:
                frame_rate_83 = prompt["83"]["inputs"].get("frame_rate")
                filename_prefix_83 = prompt["83"]["inputs"].get("filename_prefix")
                logger.info(f"✓ 节点83 (VHS_VideoCombine): frame_rate={frame_rate_83}, filename_prefix={filename_prefix_83}")
            else:
                logger.warning("✗ 节点83 缺少 inputs")
        if "129" in prompt:
            if "inputs" in prompt["129"]:
                vitpose_129 = prompt["129"]["inputs"].get("vitpose_model")
                yolo_129 = prompt["129"]["inputs"].get("yolo_model")
                logger.info(f"✓ 节点129 (OnnxDetectionModelLoader): vitpose={vitpose_129}, yolo={yolo_129}")
            else:
                logger.warning("✗ 节点129 缺少 inputs")
        if "38" in prompt:
            if "inputs" in prompt["38"]:
                vae_38 = prompt["38"]["inputs"].get("model_name")
                logger.info(f"✓ 节点38 (WanVideoVAELoader): {vae_38}")
            else:
                logger.warning("✗ 节点38 缺少 inputs")
        if "59" in prompt:
            if "inputs" in prompt["59"]:
                clip_59 = prompt["59"]["inputs"].get("clip_name")
                logger.info(f"✓ 节点59 (CLIPVisionLoader): {clip_59}")
            else:
                logger.warning("✗ 节点59 缺少 inputs")
        if "130" in prompt:
            if "inputs" in prompt["130"]:
                width_130 = prompt["130"]["inputs"].get("width")
                height_130 = prompt["130"]["inputs"].get("height")
                logger.info(f"✓ 节点130 (PoseDetectionOneToAllAnimation): width={width_130}, height={height_130}")
            else:
                logger.warning("✗ 节点130 缺少 inputs")
        if "65" in prompt:
            if "inputs" in prompt["65"]:
                clip_vision_65 = prompt["65"]["inputs"].get("clip_vision")
                image_1_65 = prompt["65"]["inputs"].get("image_1")
                logger.info(f"✓ 节点65 (WanVideoClipVisionEncode): clip_vision={'已设置' if clip_vision_65 else '未设置'}, image_1={'已设置' if image_1_65 else '未设置'}")
            else:
                logger.warning("✗ 节点65 缺少 inputs")
        if "82" in prompt:
            if "inputs" in prompt["82"]:
                clip_vision_82 = prompt["82"]["inputs"].get("clip_vision")
                image_1_82 = prompt["82"]["inputs"].get("image_1")
                logger.info(f"✓ 节点82 (WanVideoClipVisionEncode): clip_vision={'已设置' if clip_vision_82 else '未设置'}, image_1={'已设置' if image_1_82 else '未设置'}")
            else:
                logger.warning("✗ 节点82 缺少 inputs")
        if "72" in prompt:
            if "inputs" in prompt["72"]:
                image_72 = prompt["72"]["inputs"].get("image")
                vae_72 = prompt["72"]["inputs"].get("vae")
                logger.info(f"✓ 节点72 (WanVideoEncode): image={'已设置' if image_72 else '未设置'}, vae={'已设置' if vae_72 else '未设置'}")
            else:
                logger.warning("✗ 节点72 缺少 inputs")
        if "71" in prompt:
            if "inputs" in prompt["71"]:
                embeds_71 = prompt["71"]["inputs"].get("embeds")
                pose_latents_71 = prompt["71"]["inputs"].get("pose_latents_positive")
                clip_vision_embeds_71 = prompt["71"]["inputs"].get("clip_vision_embeds")
                logger.info(f"✓ 节点71 (WanVideoAddSteadyDancerEmbeds): embeds={'已设置' if embeds_71 else '未设置'}, pose_latents_positive={'已设置' if pose_latents_71 else '未设置'}, clip_vision_embeds={'已设置' if clip_vision_embeds_71 else '未设置'}")
            else:
                logger.warning("✗ 节点71 缺少 inputs")
    elif is_mega_model:
        # RapidAIO Mega (V2.5).json 验证
        if "597" in prompt and "widgets_values" in prompt["597"]:
            image_in_597 = prompt["597"]["widgets_values"][0] if prompt["597"]["widgets_values"] else None
            logger.info(f"✓ 节点597 (起始图像): {image_in_597}")
        if "591" in prompt and "widgets_values" in prompt["591"]:
            prompts_in_591 = prompt["591"]["widgets_values"][0] if prompt["591"]["widgets_values"] else None
            logger.info(f"✓ 节点591 (CreaPrompt List): {prompts_in_591[:100] if prompts_in_591 and len(prompts_in_591) > 100 else prompts_in_591}...")
        if "574" in prompt and "inputs" in prompt["574"]:
            model_in_574 = prompt["574"]["inputs"].get("ckpt_name")
            logger.info(f"✓ 节点574 (模型): {model_in_574}")
        if "572" in prompt and "widgets_values" in prompt["572"]:
            widgets = prompt["572"]["widgets_values"]
            logger.info(f"✓ 节点572 (WanVaceToVideo): width={widgets[0]}, height={widgets[1]}, length={widgets[2]}, strength={widgets[3]} (I2V)")
        if "576" in prompt and "widgets_values" in prompt["576"]:
            num_frames_576 = prompt["576"]["widgets_values"][0] if prompt["576"]["widgets_values"] else None
            logger.info(f"✓ 节点576 (VACE num_frames): {num_frames_576}")
        if "563" in prompt and "widgets_values" in prompt["563"]:
            widgets = prompt["563"]["widgets_values"]
            logger.info(f"✓ 节点563 (KSampler): seed={widgets[0]}, steps={widgets[2]}, cfg={widgets[3]}, sampler={widgets[4] if len(widgets) > 4 else 'N/A'}")
        if "584" in prompt:
            if "inputs" in prompt["584"]:
                inputs_584 = prompt["584"]["inputs"]
                images_input = inputs_584.get("images")
                logger.info(f"✓ 节点584 (VHS_VideoCombine): images={images_input}, frame_rate={inputs_584.get('frame_rate')}, format={inputs_584.get('format')}")
            else:
                logger.warning("✗ 节点584 缺少 inputs")
    else:
        # 标准 workflow 验证
        if "244" in prompt:
            if "inputs" in prompt["244"]:
                image_in_244 = prompt["244"]["inputs"].get("image")
                logger.info(f"✓ 节点244 (LoadImage): image = {image_in_244}")
            else:
                logger.warning("✗ 节点244 缺少 inputs")
        else:
            logger.warning("✗ 节点244 不存在")
        
        if "541" in prompt:
            if "inputs" in prompt["541"]:
                fun_or_fl2v_value = prompt["541"]["inputs"].get("fun_or_fl2v_model")
                logger.info(f"✓ 节点541 (WanVideoImageToVideoEncode): fun_or_fl2v_model = {fun_or_fl2v_value} (类型: {type(fun_or_fl2v_value).__name__})")
                if fun_or_fl2v_value != True:
                    logger.warning(f"⚠ 警告: fun_or_fl2v_model 不是 True，实际值: {fun_or_fl2v_value}")
                
                num_frames = prompt["541"]["inputs"].get("num_frames")
                logger.info(f"  - num_frames = {num_frames}")
            else:
                logger.warning("✗ 节点541 缺少 inputs")
        else:
            logger.warning("✗ 节点541 不存在")
    
    logger.info("=" * 60)
    
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    # 먼저 HTTP 연결이 가능한지 확인
    http_url = f"http://{server_address}:8188/"
    logger.info(f"Checking HTTP connection to: {http_url}")
    
    # HTTP 연결 확인 (최대 1분)
    max_http_attempts = 180
    for http_attempt in range(max_http_attempts):
        try:
            response = urllib_request.urlopen(http_url, timeout=5)
            logger.info(f"HTTP 연결 성공 (시도 {http_attempt+1})")
            break
        except Exception as e:
            logger.warning(f"HTTP 연결 실패 (시도 {http_attempt+1}/{max_http_attempts}): {e}")
            if http_attempt == max_http_attempts - 1:
                raise Exception("ComfyUI 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
            time.sleep(1)
    
    ws = websocket.WebSocket()
    # 웹소켓 연결 시도 (최대 3분)
    max_attempts = int(180/5)  # 3분 (1초에 한 번씩 시도)
    for attempt in range(max_attempts):
        try:
            ws.connect(ws_url)
            logger.info(f"웹소켓 연결 성공 (시도 {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"웹소켓 연결 실패 (시도 {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("웹소켓 연결 시간 초과 (3분)")
            time.sleep(5)
    try:
        videos = get_videos(ws, prompt, is_mega_model or use_steadydancer)
        ws.close()

        # SteadyDancer workflow: 优先返回节点 83 的最终视频（而不是节点 117 的姿态视频）
        if use_steadydancer:
            # 优先返回节点 83 的视频（最终生成的跳舞视频）
            if "83" in videos and videos["83"]:
                logger.info("✅ 返回节点 83 的最终生成视频（跳舞视频）")
                return {"video": videos["83"][0]}
            # 如果节点 83 没有视频，记录警告并尝试其他节点
            logger.warning("⚠️ 节点 83 没有视频输出，尝试其他节点")
        
        # 对于其他 workflow 或 SteadyDancer 的备用方案，返回第一个找到的视频
        for node_id in videos:
            if videos[node_id]:
                logger.info(f"返回节点 {node_id} 的视频")
                return {"video": videos[node_id][0]}
        
        return {"error": "비디오를를 찾을 수 없습니다."}
    except Exception as e:
        ws.close()
        error_message = str(e)
        logger.error(f"Video generation failed: {error_message}")
        return {"error": error_message}

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
