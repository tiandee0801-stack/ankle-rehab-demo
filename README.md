# Dee · 脚踝恢复实验室

脚踝恢复服务的交互原型：筛查建档 → 四时点训练反馈 → 视频观察 → 人工复核 → 阶段报告。

**在线体验：** https://tiandee0801-stack.github.io/ankle-rehab-demo/

本项目是个人产品 Demo，尚未进行真实用户交付或康复效果验证。P1 / P2 / P3 是同一脚踝项目的三个服务层级；首版展开 P2「小腿提踵能力」。

## 在线版与本机版

| 功能 | GitHub Pages 在线版 | Python 本机版 |
| --- | --- | --- |
| 档案、四时点记录、人工复核 | 可操作，保存于当前浏览器 | 可操作，保存于本机 SQLite |
| 阶段报告、JSON 导出、打印 | 可用 | 可用 |
| 公开动作视频及骨架叠加回放 | 可观看此前已计算的结果 | 可观看 |
| 选择自己的视频 | 仅浏览器预览，不上传、不识别 | 可提交本机姿态模型分析 |
| 新视频 MMPose / RTMPose 推理 | 不运行 | 需另行配置模型环境 |

在线版仅包含手工构造的虚构示例档案、训练记录和人工意见。没有上传原始 SQLite 数据库、个人录像、教材、简历或 API 密钥。访客数据互不共享，保存在各自浏览器的 localStorage 中。

## 本机运行

基础记录服务仅需 Python 3.10+ 的标准库：

```sh
python3 server.py
```

打开终端输出的本机地址，默认 `http://127.0.0.1:8843/`。服务只绑定本机，数据写入被 Git 忽略的 `data/`。可通过 `ANKLE_DATA_DIR` 指定独立的数据目录。

真实视频分析还需要 MMPose / MMDetection、RTMPose-M COCO-WholeBody 133、RTMDet-nano person 权重，以及 FFmpeg / FFprobe。模型与依赖不包含在仓库中，需按 [MMPose 官方项目](https://github.com/open-mmlab/mmpose) 的许可和安装说明单独配置。

```sh
export ANKLE_MODEL_PYTHON=/path/to/mmpose/.venv/bin/python
export ANKLE_MMPOSE_ROOT=/path/to/mmpose
export ANKLE_FFMPEG=/path/to/ffmpeg
export ANKLE_FFPROBE=/path/to/ffprobe
python3 server.py
```

仅分析离线短视频：最多 30 秒、80 MiB。二维图像关键点、候选轨迹和质量提示不等于医学关节测量、力量评估或自动康复进阶。

## 开发与部署

```sh
python3 scripts/build_public.py
python3 -m http.server 8844 --bind 127.0.0.1
```

浏览 `http://127.0.0.1:8844/docs/` 检查公开版。`docs/` 是 GitHub Pages 的发布目录，发布源为 `main` 分支的 `/docs`。修改 `dist/` 或 `public/` 后重新构建并提交 `docs/`。

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_public_runtime.cjs
```

## 主要文件

- `dist/`：与本机版共享的前端。
- `public/runtime.js`：浏览器存储、表单校验及在线能力提示。
- `public/seed.json`：虚构示例资料与公开视频的已计算结果。
- `server.py`：本机 HTTP / SQLite 服务。
- `engine/`：本机关键点推理和提踵候选后处理。
- `API-CONTRACT.md`：本机接口及状态规则。
- `docs/`：构建后的 GitHub Pages 页面。

## 参考与素材

MMPose 用于真实姿态关键点推理；Good-GYM 提供训练交互和计数状态的思路参考，没有把其代码或演示视频冒充本项目实现。OpenPose、EasyMocap、QuickPose 为选型参考，本版没有集成其全部功能。界面布局参考 [Physitrack 公开首页](https://www.physitrack.com/)，使用本项目品牌、文字与功能重新实现。

公开小腿运动视频来自 [DVIDS · Explosive Calf Raise](https://www.dvidshub.net/video/636502/explosive-calf-raise)，作者 Capt. Matthew Holfinger / U.S. Marine Corps Training and Education Command。原视频标记为 public domain，使用限制及处理记录见 [素材说明](dist/assets/calf/SOURCE-LICENSE.txt)。本项目保留原视频裁切、真实模型叠加及质量不足的结果：有效观察帧约 22.1%，不提供候选次数。没有真人标准提踵计数准确率或康复效果结论。

The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement.

第三方软件、模型、数据与素材各按原许可处理；公开本仓库不额外授予对第三方内容的权利。
