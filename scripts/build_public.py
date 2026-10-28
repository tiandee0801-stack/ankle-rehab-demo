"""Build GitHub Pages files from the shared frontend, using a browser-local adapter."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs'
if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT / 'dist', OUT)
shutil.copy2(ROOT / 'public/runtime.js', OUT / 'public-runtime.js')
shutil.copy2(ROOT / 'public/seed.json', OUT / 'public-seed.json')
p = OUT / 'index.html'
s = p.read_text().replace('href="/', 'href="./').replace('src="/', 'src="./')
s = s.replace('<script src="./landing.js', '<script src="./public-runtime.js" defer></script><script src="./landing.js')
s = s.replace('本机运行 · 数据保存在本机', '在线演示 · 记录仅保存在此浏览器')
s = s.replace('正在加载本地记录', '正在加载演示记录')
s = s.replace('</header>\n<div class="app-shell">', '</header>\n<div class="public-site-note">在线交互演示 · 记录保存在当前浏览器 · 新的视频识别需使用本机版</div>\n<div class="app-shell">', 1)
p.write_text(s)
p = OUT / 'landing.js'
s = p.read_text().replace('本机分析</span>', '已保存的模型结果</span>')
s = s.replace('在下面展开完整记录，或切到填写表单。保存内容会进入本机档案。', '在下面展开记录或填写表单。保存内容会留在当前浏览器。')
s = s.replace('接入本机 MMPose / RTMPose。可选择自己的视频，历史结果保留来源。', '观看已保存的模型结果，或预览自己的视频；新的视频识别需运行本机版。')
s = s.replace('下方就是已接通本机数据的功能区，可以直接展开、填写和切换。', '下方功能区可以直接操作，数据保存在当前浏览器。')
s = s.replace('本版在这台 Mac 上运行，记录与上传视频保存在本机。无需申请云端账号；服务关闭后，已保存的数据仍保留。', '在线版的记录保存在当前浏览器，访客之间互不共享。所选视频只在浏览器预览。完整姿态识别服务需要运行仓库中的本机版。')
s = s.replace('可以建立和查看档案、填写四时点训练记录、在产品2上传提踵观察视频、记录人工复核意见，以及查看和导出阶段报告。', '可以建立档案、填写四时点记录、预览视频、记录人工复核意见、查看和导出报告。新的模型识别需运行本机版。')
p.write_text(s)
p = OUT / 'app.js'
s = p.read_text().replace('本机产品原型', '在线交互演示').replace('本机档案', '浏览器档案')
s = s.replace('视频已提交，开始本机分析。', '请在本机版执行视频模型识别。')
p.write_text(s)
with (OUT / 'physitrack.css').open('a') as f:
    f.write('\n.public-site-note{padding:10px 24px;text-align:center;font-size:12px;color:#536e70;background:#f0f4f6;border-bottom:1px solid #e0e7e8}@media print{.public-site-note{display:none}}\n')
(OUT / '.nojekyll').touch()
print('GitHub Pages build complete:', OUT)
