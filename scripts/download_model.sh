#!/bin/bash
# VideoDub - whisper.cpp 模型下载脚本
# 用法: bash scripts/download_model.sh [模型名称]
# 默认下载 large-v3，可选: tiny / base / small / medium / large-v1 / large-v3

set -euo pipefail

MODELS_DIR="models"
MODEL="${1:-large-v3}"

# Hugging Face 模型映射
declare -A MODEL_URLS
MODEL_URLS["tiny"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"
MODEL_URLS["base"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"
MODEL_URLS["small"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"
MODEL_URLS["medium"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
MODEL_URLS["large-v1"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v1.bin"
MODEL_URLS["large-v3"]="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"

MODEL_URL="${MODEL_URLS[$MODEL]:-}"
if [ -z "$MODEL_URL" ]; then
    echo "错误: 不支持的模型 '$MODEL'"
    echo "支持的模型: tiny, base, small, medium, large-v1, large-v3"
    exit 1
fi

# 创建模型目录
mkdir -p "$MODELS_DIR"

OUTPUT_FILE="${MODELS_DIR}/ggml-${MODEL}.bin"

# 检查是否已下载
if [ -f "$OUTPUT_FILE" ]; then
    echo "模型已存在: $OUTPUT_FILE"
    echo "如需重新下载，请先删除该文件。"
    exit 0
fi

echo "开始下载 whisper.cpp ${MODEL} 模型..."
echo "来源: $MODEL_URL"
echo "目标: $OUTPUT_FILE"
echo ""

# 使用 wget 或 curl 下载
if command -v wget &> /dev/null; then
    wget -O "$OUTPUT_FILE" "$MODEL_URL" --progress=bar:force
elif command -v curl &> /dev/null; then
    curl -L -o "$OUTPUT_FILE" "$MODEL_URL" --progress-bar
else
    echo "错误: 未找到 wget 或 curl，请先安装其中之一。"
    exit 1
fi

echo ""
echo "模型下载完成: $OUTPUT_FILE"

# 验证文件大小
FILE_SIZE=$(stat -c%s "$OUTPUT_FILE" 2>/dev/null || stat -f%z "$OUTPUT_FILE" 2>/dev/null)
if [ "$FILE_SIZE" -lt 1000000 ]; then
    echo "警告: 文件大小异常 (${FILE_SIZE} bytes)，下载可能不完整。"
    exit 1
fi

echo "文件大小: $(numfmt --to=iec $FILE_SIZE 2>/dev/null || echo "${FILE_SIZE} bytes")"
echo "模型已就绪，可以开始使用 VideoDub。"
