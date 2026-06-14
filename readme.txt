AMDLocalDub  --  AMD离线配音  --  纯本地 / AMD显卡加速 的视频翻译配音工具

它能干什么？
把外文视频自动转成中文配音版（或其他语言），全部在你自己的电脑上完成，不需要上传任何文件到云端。

AMD 显卡加速在哪？
- 语音识别用 whisper.cpp Vulkan 后端，跑在 AMD GPU 上
- 视频编码用 ffmpeg AMF (h264_amf)，跑在 AMD GPU 上
- 全程不需要 NVIDIA CUDA，AMD Radeon RX 9070 XT 实测可用

完全本地体现在哪？
- 语音识别：纯本地，模型文件在本地加载
- 配音：Edge-TTS 本地合成
- 视频合成：ffmpeg 本地编码
- 翻译：支持 LM Studio 本地模型，搭配使用可完全断网运行
- 整个流程视频不上传任何服务器

支持的语言
- 源语言：英语、中文、印地语、西班牙语、法语、阿拉伯语、葡萄牙语、俄语 等 20 种
- 目标语言：中文、英语、日语、韩语、法语、德语、西班牙语、俄语 等 23 种
- 配音音色：50 多种，每种语言 2-8 种可选

使用方法
1. 双击 start_amdlocaldub.bat 启动
2. 浏览器打开 http://127.0.0.1:7860
3. 在文本框中输入视频路径（推荐），或拖拽文件到上传区
4. 选择翻译引擎（SiliconFlow / DeepSeek / LM Studio 本地）
5. 点击一键启动

输出文件
- xxx_dubbed.mp4  成品视频
- xxx_dubbed.srt  字幕文件
- 如果没有指定输出目录，默认输出到项目根目录的 outputs/ 文件夹
- 中间缓存文件在 outputs/.cache_xxx/ 目录下，可删除
