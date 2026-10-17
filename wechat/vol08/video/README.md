# 第 8 期 15 秒短片

`out/vol08-15s-1080p.mp4`：1920×1080，30fps，H.264 + AAC，15 秒，约 19.6MB。上传公众号用这个。
`out/vol08-15s-720p.mp4`：1280×720，约 3.3MB，方便在微信里转发预览。
`out/poster.jpg`：封面帧。`out/music.wav`：配乐原文件。

## 结构（120 BPM，一小节 2 秒）
| 时间 | 画面 | 声音 |
|---|---|---|
| 0–2s | 午夜蓝底，「08」黄色描边画出，字形里透出课堂画面，镜头推进穿过「8」 | 低频轰鸣 + 噪声上扬 + 军鼓滚奏 |
| 2–12s | 五段现场各 2 秒：LEARN / PRACTICE / ONE ON ONE / CREATE / THINK，顶部 logo，底部 5 格进度条 | 四拍节奏，二四拍画面轻微冲击缩放 |
| 切换点 | 4s 缩放模糊，6s 横向甩镜，8s 斜向光扫，10s 纵向甩镜 | 每次切换前一声「唰」 |
| 12–15s | 画面放慢、虚化、压暗，「五天，把路走通。」→「第 9 期 · 招生中」→ logo | 重拍收束 + 长音铺底 + 亮音 |

## 制作流程（全部为代码，可复现）
1. 素材：iPhone HLG HDR 原片，用 ffmpeg zscale + hable 色调映射转为 BT.709 SDR。
2. `music.py`：用 numpy/scipy 合成配乐，没有用任何采样或版权素材。
3. `overlay.html` + `render.js`：用 Chromium 逐帧渲染文字、进度条和片头遮罩（透明 PNG）。字体为 Inter 与思源黑体，都是开源可商用字体。
4. `compose.py`：用 OpenCV 逐帧做推镜、节拍缩放、转场、调色、暗角、颗粒，叠加图形层，最后由 ffmpeg 编码。

```bash
python3 music.py music.wav
node render.js frames/ fonts.css all
python3 -I compose.py sdr/ frames/ music.wav out/vol08-15s-1080p.mp4
```
