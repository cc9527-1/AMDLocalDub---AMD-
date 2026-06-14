"""VideoDub ASR 语音识别引擎。

只使用 whisper.cpp Vulkan/ROCm GPU 加速，不支持任何 CPU 回退。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.data_models import ASRError


class ASREngine:
    """ASR 语音识别引擎。

    只支持 whisper.cpp Vulkan/ROCm GPU 加速。
    如果 whisper.cpp 不可用，直接报错，不降级到 CPU。

    Attributes:
        _model_path: 模型路径
        _backend: 推理后端 (vulkan / rocm)
        _gpu_device: GPU 设备编号
        _whisper_executable: whisper.cpp 可执行文件路径
        _initialized: 是否已初始化
        _backend_choice: 实际选择的后端名称
    """

    def __init__(
        self,
        model_path: str,
        backend: str = "vulkan",
        gpu_device: int = 0,
    ) -> None:
        self._model_path: str = model_path
        self._backend: str = backend
        self._gpu_device: int = gpu_device
        self._whisper_executable: Optional[str] = None
        self._initialized: bool = False
        self._backend_choice: str = "unknown"

    def initialize(
        self, progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """初始化 ASR 引擎。

        只尝试 whisper.cpp Vulkan/ROCm GPU 加速。
        如果不可用直接报错，不降级到 CPU。

        Returns:
            初始化成功返回 True

        Raises:
            ASRError: whisper.cpp 不可用
        """
        cpp_ok, cpp_msg = self._try_init_whisper_cpp()
        if cpp_ok:
            self._backend_choice = f"whisper.cpp ({self._backend})"
            self._initialized = True
            return True

        raise ASRError(
            f"语音识别引擎不可用: {cpp_msg}\n\n"
            f"请确保 whisper.cpp 已编译并配置好:\n"
            f"  1. 确认 whisper_jerry_bin/whisper-cli.exe 存在\n"
            f"  2. 确认 models/ 下有模型文件\n"
            f"  3. 确认 AMD 显卡驱动已安装\n"
            f"  4. 启动 bat 文件会自动配置 GPU 路径"
        )

    def _try_init_whisper_cpp(self) -> Tuple[bool, str]:
        """尝试初始化 whisper.cpp GPU 后端。

        Returns:
            (成功否, 状态消息)
        """
        model_exists = os.path.isfile(self._model_path)
        exe_path = self._find_executable("whisper-cli")
        if not exe_path:
            return False, f"未找到 whisper-cli.exe（请检查 whisper_jerry_bin/ 目录）"

        try:
            result = subprocess.run(
                [exe_path, "--help"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False, f"whisper-cli 启动失败 (exit={result.returncode})"
        except Exception as e:
            return False, f"whisper-cli 验证失败: {e}"

        self._whisper_executable = exe_path
        if not model_exists:
            return False, f"模型文件不存在: {self._model_path}"
        return True, "就绪"

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """执行语音识别（仅 GPU，无 CPU 回退）。

        Args:
            audio_path: 音频文件路径
            progress_callback: 进度回调
            language: 音频语言代码

        Returns:
            识别结果列表 [{text, start, end}, ...]

        Raises:
            ASRError: whisper.cpp GPU 识别失败
        """
        if not self._initialized:
            raise ASRError("ASR 引擎未初始化，请先调用 initialize()")
        if not os.path.isfile(audio_path):
            raise ASRError(f"音频文件不存在: {audio_path}")
        if not self._whisper_executable:
            raise ASRError("whisper.cpp 未初始化，请检查 whisper_jerry_bin/ 目录")

        return self._transcribe_cpp(audio_path, progress_callback, language)

    def _transcribe_cpp(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """使用 whisper.cpp (GPU) 执行语音识别。"""
        if progress_callback:
            progress_callback(10.0, f"正在使用 {self._backend_choice} 识别...")

        tmp_dir = tempfile.mkdtemp(prefix="whisper_")
        output_path = os.path.join(tmp_dir, "output")

        try:
            cmd = [
                self._whisper_executable,
                "-m", self._model_path,
                "-f", audio_path,
                "--output-json",
                "--output-file", output_path,
                "--language", language,
            ]
            # GPU 加速：指定设备
            cmd.extend(["--device", str(self._gpu_device)])

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors="replace",
            )
            stdout, stderr = process.communicate(timeout=600)

            if process.returncode != 0:
                err_text = (stderr or "").strip()[:300] or (stdout or "").strip()[:100] or "未知错误"
                raise ASRError(
                    f"whisper.cpp GPU 识别失败(exit={process.returncode}): {err_text}"
                )

            result_json = output_path + ".json"
            if not os.path.isfile(result_json):
                raise ASRError("whisper.cpp 未生成输出 JSON 文件")

            segments = self._parse_output(result_json)
            if progress_callback:
                progress_callback(100.0, f"GPU 识别完成，共 {len(segments)} 个片段")
            return segments

        except subprocess.TimeoutExpired:
            process.kill()
            raise ASRError("whisper.cpp GPU 处理超时 (600s)")
        except ASRError:
            raise
        except Exception as e:
            raise ASRError(f"whisper.cpp GPU 识别出错: {e}")
        finally:
            try:
                for f in os.listdir(tmp_dir):
                    os.remove(os.path.join(tmp_dir, f))
                os.rmdir(tmp_dir)
            except OSError:
                pass

    def shutdown(self) -> None:
        """释放 ASR 引擎资源。"""
        self._initialized = False
        self._whisper_executable = None

    def _parse_output(self, json_path: str) -> List[Dict[str, Any]]:
        """解析 whisper.cpp 的 JSON 输出文件。"""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ASRError(f"解析 whisper.cpp JSON 输出失败: {e}")

        segments: List[Dict[str, Any]] = []

        # 格式1: transcription = [{timestamps: {from, to}, text}] (jerryshell 版)
        raw = data.get("transcription")
        if isinstance(raw, list):
            for seg in raw:
                text = seg.get("text", "").strip()
                if not text:
                    continue
                ts = seg.get("timestamps", {})
                start_str = ts.get("from", "00:00:00,000")
                end_str = ts.get("to", "00:00:00,000")
                segments.append({
                    "text": text,
                    "start": self._parse_srt_timestamp(start_str),
                    "end": self._parse_srt_timestamp(end_str),
                })
            if segments:
                return segments

        # 格式2: segments = [{start, end, text}] (标准 whisper.cpp)
        for seg in data.get("segments", []):
            text = seg.get("text", "").strip()
            if text:
                segments.append({
                    "text": text,
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                })

        if not segments:
            text = data.get("text", "").strip()
            if text:
                segments.append({
                    "text": text, "start": 0.0,
                    "end": data.get("duration", 0.0),
                })
        return segments

    @staticmethod
    def _parse_srt_timestamp(ts: str) -> float:
        ts = ts.replace(",", ".").replace("，", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        else:
            try:
                return float(parts[0])
            except ValueError:
                return 0.0

    @staticmethod
    def _find_executable(name: str) -> Optional[str]:
        """在 PATH 和常见路径中查找 whisper-cli。"""
        import pathlib
        project_root = pathlib.Path(__file__).resolve().parent.parent.parent
        for bin_subdir in ["whisper_jerry_bin", "whisper_vulkan_bin"]:
            bin_dir = project_root / bin_subdir
            if bin_dir.is_dir():
                for ext in ["", ".exe", ".bat", ".cmd"]:
                    full_path = bin_dir / (name + ext)
                    if full_path.is_file():
                        return str(full_path.resolve())
        if os.path.isfile(name) and os.access(name, os.X_OK):
            return os.path.abspath(name)
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for dir_path in path_dirs:
            full_path = os.path.join(dir_path, name)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                return full_path
            for ext in [".exe", ".bat", ".cmd"]:
                full_path_ext = full_path + ext
                if os.path.isfile(full_path_ext) and os.access(full_path_ext, os.X_OK):
                    return full_path_ext
        return None
