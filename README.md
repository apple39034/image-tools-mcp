# image-tools-mcp

基于 [FastMCP](https://github.com/jlowin/fastmcp) 的图像处理 MCP 服务，供 Claude Code 调用。

## 工具列表

| 工具名 | 功能 |
|--------|------|
| `image_info` | 查看图片尺寸、格式、文件大小、色彩模式 |
| `image_add_watermark` | 图片满铺斜向平铺水印（支持批量处理整个文件夹） |
| `image_crop` | 图片裁切（坐标框 / 居中裁切两种模式） |
| `image_adjust_color` | 调色（亮度 / 对比度 / 饱和度 / 锐度） |
| `pdf_add_watermark` | PDF 满铺斜向平铺水印（支持批量处理整个文件夹） |
| `docx_add_watermark` | Word 文档（.docx）添加旋转水印（每页背景显示） |

## 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

## 一键安装

```bash
# 1. 克隆到任意目录，推荐 ~/tools/
git clone https://github.com/apple39034/image-tools-mcp ~/tools/image-tools-mcp

# 2. 运行安装脚本（自动安装依赖 + 注册到 Claude Code）
cd ~/tools/image-tools-mcp
bash install.sh
```

安装完成后重启 Claude Code，`/mcp` 即可看到 `image-tools ✓ Connected`。

## 手动安装

### 步骤 1：安装依赖

```bash
cd ~/tools/image-tools-mcp
uv sync          # 推荐：uv 自动创建 .venv 并安装
# 或
pip install "mcp[cli]>=1.26" Pillow
```

### 步骤 2：注册到 Claude Code

> **注意**：必须使用 `--project` 参数，否则 `uv run` 找不到虚拟环境会报 `No module named 'mcp'`。

**全局注册（所有项目都可用，推荐）：**

```bash
INSTALL_DIR="$HOME/tools/image-tools-mcp"
claude mcp add -s user image-tools -- \
  uv run --project "$INSTALL_DIR" "$INSTALL_DIR/server.py"
```

**项目级注册（仅当前项目）：**

```bash
INSTALL_DIR="$HOME/tools/image-tools-mcp"
claude mcp add image-tools -- \
  uv run --project "$INSTALL_DIR" "$INSTALL_DIR/server.py"
```

### 步骤 3：验证

```bash
claude mcp list
# 应看到：image-tools: ✓ Connected
```

## 使用示例

在 Claude Code 对话中直接描述需求：

```
给 ~/Desktop/photos 里所有图片加水印，文字"内部资料 2025"，角度 45 度，透明度 0.15

把 report.png 从中心裁切到 1080x1080

把 photo.jpg 的饱和度降到 0.3，亮度提到 1.2

查看 ~/Downloads/screenshots 文件夹里所有图片的尺寸和格式
```

## 参数速查

### `image_add_watermark`
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_path` | 必填 | 图片路径或文件夹路径 |
| `text` | 必填 | 水印文字 |
| `angle` | `30` | 倾斜角度（正数=逆时针，-180~180） |
| `opacity` | `0.12` | 透明度（0~1） |
| `font_size` | `32` | 字号（8~200） |
| `gap` | `100` | 水印间距像素，越大越稀疏 |
| `color` | `"128,128,128"` | 颜色 "R,G,B" |
| `suffix` | `"_wm"` | 输出文件名后缀 |
| `font_path` | 自动检测 | 字体路径，Mac 可填 `/System/Library/Fonts/PingFang.ttc` |

### `image_crop`
| 参数 | 说明 |
|------|------|
| `mode` | `"center"`（居中裁切）或 `"box"`（坐标框） |
| `width` / `height` | center 模式必填 |
| `left` / `top` / `right` / `bottom` | box 模式必填 |
| `suffix` | 输出后缀，默认 `"_crop"` |

### `image_adjust_color`
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `brightness` | `1.0` | 亮度，>1 更亮 |
| `contrast` | `1.0` | 对比度，>1 更强 |
| `saturation` | `1.0` | 饱和度，0 = 灰度 |
| `sharpness` | `1.0` | 锐度，>1 更锐利 |
| `suffix` | `"_adj"` | 输出后缀 |

### `docx_add_watermark`
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_path` | 必填 | .docx 文件路径或包含 .docx 的文件夹（不支持 .doc / .docm） |
| `text` | 必填 | 水印文字 |
| `angle` | `315` | 旋转角度（VML/DrawingML 顺时针为正，315=左上→右下） |
| `opacity` | `0.3` | 透明度（0~1）|
| `font_size` | `72` | 字号（点） |
| `color` | `"128,128,128"` | 颜色 "R,G,B" |
| `suffix` | `"_wm"` | 输出文件名后缀 |
| `font_family` | 自动选择 | CJK 默认 `Microsoft YaHei`，其他默认 `Arial` |

> 实现方式：通过 Word 原生的页眉水印机制注入 `mc:AlternateContent`（同时提供
> DrawingML 和 VML 两套），Word 自动在每页背景重复显示。Word 2010+、LibreOffice
> 均能正确渲染。

### `pdf_add_watermark`
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_path` | 必填 | PDF 文件路径或包含 PDF 的文件夹路径 |
| `text` | 必填 | 水印文字 |
| `angle` | `30` | 倾斜角度（正数=逆时针） |
| `opacity` | `0.12` | 透明度（0~1） |
| `font_size` | `36` | 字号（点，1点=1/72英寸） |
| `gap` | `80` | 水印间距（点），越大越稀疏 |
| `color` | `"128,128,128"` | 颜色 "R,G,B" |
| `suffix` | `"_wm"` | 输出文件名后缀 |
| `font_path` | 自动检测 | 字体路径，中文建议指定 |

## 支持的图片格式

`.jpg` / `.jpeg` / `.png` / `.bmp` / `.tiff` / `.webp`

## 常见问题

**Q: 注册后 `/mcp` 显示 `Failed to connect`？**

A: 确认使用了 `--project` 参数。直接运行 `uv run /path/server.py`（无 `--project`）时 uv 找不到虚拟环境，会报 `No module named 'mcp'`。正确命令：
```bash
uv run --project /path/to/image-tools-mcp /path/to/image-tools-mcp/server.py
```

**Q: 中文水印显示为方块？**

A: 指定中文字体路径：
- macOS：`font_path="/System/Library/Fonts/PingFang.ttc"`
- Linux：`font_path="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"`
