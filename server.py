#!/usr/bin/env python3
"""
image_tools_mcp — 图像处理 MCP 服务
提供满铺斜向水印、图片裁切、调色等工具，供 Claude Code 调用。

启动方式（stdio，供 Claude Code 使用）：
  python3 server.py
"""

import json
import math
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from pydantic import BaseModel, Field, ConfigDict, field_validator

# ── 初始化 ──────────────────────────────────────────────────────────────────────
mcp = FastMCP("image_tools_mcp")

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

FALLBACK_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",           # macOS
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/msyh.ttc",                    # Windows
    "C:/Windows/Fonts/simhei.ttf",
]


# ── 共用工具函数 ────────────────────────────────────────────────────────────────
def _get_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    for path in FALLBACK_FONTS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _collect_images(input_path: str) -> list[Path]:
    """收集单张图片或文件夹内所有支持格式图片"""
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() not in SUPPORTED_EXT:
            raise ValueError(f"不支持的文件格式：{p.suffix}，支持：{SUPPORTED_EXT}")
        return [p]
    elif p.is_dir():
        files = [f for f in p.iterdir() if f.suffix.lower() in SUPPORTED_EXT]
        if not files:
            raise ValueError(f"文件夹 {p} 中没有找到支持的图片")
        return sorted(files)
    else:
        raise FileNotFoundError(f"路径不存在：{p}")


def _save_image(img: Image.Image, src: Path, suffix: str) -> Path:
    """保存为新文件，自动处理 JPEG 的 RGBA 问题"""
    out = src.parent / f"{src.stem}{suffix}{src.suffix}"
    if src.suffix.lower() in (".jpg", ".jpeg"):
        img = img.convert("RGB")
        img.save(out, "JPEG", quality=95)
    else:
        img.save(out)
    return out


def _make_watermark_layer(
    width: int,
    height: int,
    text: str,
    angle: float,
    opacity: float,
    font: ImageFont.FreeTypeFont,
    gap: int,
    color: tuple,
) -> Image.Image:
    """生成满铺斜向水印图层（与原图等大的 RGBA 透明图层）"""
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    diag = int(math.ceil(math.sqrt(width**2 + height**2)))
    canvas_size = diag + max(tw, th) * 2 + gap * 4

    big = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    alpha = int(255 * opacity)
    fill = (*color, alpha)

    step_x, step_y = tw + gap, th + gap
    for y in range(-step_y, canvas_size + step_y, step_y):
        for x in range(-step_x, canvas_size + step_x, step_x):
            draw.text((x, y), text, font=font, fill=fill)

    rotated = big.rotate(angle, expand=False, resample=Image.BICUBIC)
    left = (canvas_size - width) // 2
    top = (canvas_size - height) // 2
    return rotated.crop((left, top, left + width, top + height))


# ── Pydantic 输入模型 ───────────────────────────────────────────────────────────
class WatermarkInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description="图片文件路径或文件夹路径")
    text: str = Field(..., description="水印文字内容，如 '内部资料 Simon'", min_length=1, max_length=100)
    angle: float = Field(default=30.0, description="倾斜角度，正数=逆时针，默认 30", ge=-180, le=180)
    opacity: float = Field(default=0.12, description="透明度 0.0（全透明）~1.0（不透明），默认 0.12", ge=0.0, le=1.0)
    font_size: int = Field(default=32, description="字号，默认 32", ge=8, le=200)
    gap: int = Field(default=100, description="水印重复间距（像素），越大越稀疏，默认 100", ge=10, le=500)
    color: str = Field(default="128,128,128", description="文字颜色 R,G,B，默认灰色 '128,128,128'")
    suffix: str = Field(default="_wm", description="输出文件名后缀，默认 '_wm'")
    font_path: Optional[str] = Field(default=None, description="字体文件路径（可选，不填自动检测中文字体）")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        parts = v.split(",")
        if len(parts) != 3:
            raise ValueError("color 格式应为 R,G,B，例如 128,128,128")
        for p in parts:
            val = int(p.strip())
            if not 0 <= val <= 255:
                raise ValueError("颜色值应在 0~255 之间")
        return v


class CropInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description="图片文件路径或文件夹路径")
    mode: str = Field(..., description="裁切模式：'box'=指定坐标框, 'center'=从中心裁切到目标尺寸")
    width: Optional[int] = Field(default=None, description="目标宽度（center 模式必填）", ge=1)
    height: Optional[int] = Field(default=None, description="目标高度（center 模式必填）", ge=1)
    left: Optional[int] = Field(default=None, description="左边界像素（box 模式）", ge=0)
    top: Optional[int] = Field(default=None, description="上边界像素（box 模式）", ge=0)
    right: Optional[int] = Field(default=None, description="右边界像素（box 模式）", ge=0)
    bottom: Optional[int] = Field(default=None, description="下边界像素（box 模式）", ge=0)
    suffix: str = Field(default="_crop", description="输出文件名后缀，默认 '_crop'")


class ColorAdjustInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description="图片文件路径或文件夹路径")
    brightness: float = Field(default=1.0, description="亮度，1.0=原始，>1 更亮，<1 更暗", ge=0.1, le=5.0)
    contrast: float = Field(default=1.0, description="对比度，1.0=原始，>1 更强", ge=0.1, le=5.0)
    saturation: float = Field(default=1.0, description="饱和度，1.0=原始，0=灰度，>1 更鲜艳", ge=0.0, le=5.0)
    sharpness: float = Field(default=1.0, description="锐度，1.0=原始，>1 更锐利", ge=0.0, le=5.0)
    suffix: str = Field(default="_adj", description="输出文件名后缀，默认 '_adj'")


class ImageInfoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description="图片文件路径或文件夹路径")


# ── 工具：满铺斜向水印 ──────────────────────────────────────────────────────────
@mcp.tool(
    name="image_add_watermark",
    annotations={
        "title": "添加满铺斜向水印",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def image_add_watermark(params: WatermarkInput) -> str:
    """为图片添加满铺斜向平铺水印，支持单张或批量处理整个文件夹。

    水印以指定角度均匀铺满整张图片，可调节透明度、字号、间距和颜色。
    输出为新文件（原文件名+后缀），不覆盖原文件。

    Args:
        params (WatermarkInput): 水印参数，包含：
            - input_path: 图片或文件夹路径
            - text: 水印文字
            - angle: 倾斜角度（默认30度）
            - opacity: 透明度（默认0.12）
            - font_size: 字号（默认32）
            - gap: 水印间距像素（默认100）
            - color: R,G,B 颜色字符串（默认灰色）
            - suffix: 输出文件后缀（默认_wm）
            - font_path: 可选字体路径

    Returns:
        str: JSON，包含处理结果列表，每项含 input/output/status/error
    """
    try:
        targets = _collect_images(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    color = tuple(int(x.strip()) for x in params.color.split(","))
    font = _get_font(params.font_path, params.font_size)
    results = []

    for src in targets:
        try:
            img = Image.open(src).convert("RGBA")
            w, h = img.size
            wm_layer = _make_watermark_layer(w, h, params.text, params.angle,
                                             params.opacity, font, params.gap, color)
            composited = Image.alpha_composite(img, wm_layer)
            out = _save_image(composited, src, params.suffix)
            results.append({"input": str(src), "output": str(out), "status": "ok"})
        except Exception as e:
            results.append({"input": str(src), "status": "error", "error": str(e)})

    summary = f"处理完成：{sum(1 for r in results if r['status']=='ok')}/{len(results)} 张成功"
    return json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)


# ── 工具：图片裁切 ──────────────────────────────────────────────────────────────
@mcp.tool(
    name="image_crop",
    annotations={
        "title": "图片裁切",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def image_crop(params: CropInput) -> str:
    """裁切图片，支持两种模式：指定坐标框 或 从中心裁切到目标尺寸。

    Args:
        params (CropInput): 裁切参数，包含：
            - input_path: 图片或文件夹路径
            - mode: 'box'（指定left/top/right/bottom）或 'center'（指定width/height）
            - width/height: center 模式的目标尺寸
            - left/top/right/bottom: box 模式的裁切坐标
            - suffix: 输出文件后缀（默认_crop）

    Returns:
        str: JSON，处理结果列表
    """
    try:
        targets = _collect_images(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    results = []
    for src in targets:
        try:
            img = Image.open(src)
            w, h = img.size

            if params.mode == "center":
                if not params.width or not params.height:
                    raise ValueError("center 模式需要同时指定 width 和 height")
                tw, th = min(params.width, w), min(params.height, h)
                left = (w - tw) // 2
                top = (h - th) // 2
                box = (left, top, left + tw, top + th)
            elif params.mode == "box":
                if any(v is None for v in [params.left, params.top, params.right, params.bottom]):
                    raise ValueError("box 模式需要同时指定 left/top/right/bottom")
                box = (params.left, params.top, params.right, params.bottom)
            else:
                raise ValueError(f"未知裁切模式：{params.mode}，应为 'box' 或 'center'")

            cropped = img.crop(box)
            out = _save_image(cropped, src, params.suffix)
            results.append({
                "input": str(src),
                "original_size": f"{w}x{h}",
                "cropped_size": f"{cropped.width}x{cropped.height}",
                "output": str(out),
                "status": "ok",
            })
        except Exception as e:
            results.append({"input": str(src), "status": "error", "error": str(e)})

    summary = f"裁切完成：{sum(1 for r in results if r['status']=='ok')}/{len(results)} 张成功"
    return json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)


# ── 工具：调色 ──────────────────────────────────────────────────────────────────
@mcp.tool(
    name="image_adjust_color",
    annotations={
        "title": "图片调色（亮度/对比度/饱和度/锐度）",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def image_adjust_color(params: ColorAdjustInput) -> str:
    """调整图片的亮度、对比度、饱和度和锐度，支持单张或批量。

    所有参数以 1.0 为基准（原始值），大于1增强，小于1减弱。
    例如：饱和度=0 得到灰度图，亮度=1.5 提亮50%。

    Args:
        params (ColorAdjustInput): 调色参数，包含：
            - input_path: 图片或文件夹路径
            - brightness: 亮度（默认1.0）
            - contrast: 对比度（默认1.0）
            - saturation: 饱和度（默认1.0，0为灰度）
            - sharpness: 锐度（默认1.0）
            - suffix: 输出文件后缀（默认_adj）

    Returns:
        str: JSON，处理结果列表
    """
    try:
        targets = _collect_images(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    results = []
    for src in targets:
        try:
            img = Image.open(src).convert("RGB")
            img = ImageEnhance.Brightness(img).enhance(params.brightness)
            img = ImageEnhance.Contrast(img).enhance(params.contrast)
            img = ImageEnhance.Color(img).enhance(params.saturation)
            img = ImageEnhance.Sharpness(img).enhance(params.sharpness)
            out = _save_image(img, src, params.suffix)
            results.append({"input": str(src), "output": str(out), "status": "ok"})
        except Exception as e:
            results.append({"input": str(src), "status": "error", "error": str(e)})

    summary = f"调色完成：{sum(1 for r in results if r['status']=='ok')}/{len(results)} 张成功"
    return json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)


# ── 工具：查看图片信息 ──────────────────────────────────────────────────────────
@mcp.tool(
    name="image_info",
    annotations={
        "title": "查看图片信息",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def image_info(params: ImageInfoInput) -> str:
    """查看图片的基本信息（尺寸、格式、文件大小、色彩模式），支持单张或文件夹。

    Args:
        params (ImageInfoInput): 包含 input_path（图片或文件夹路径）

    Returns:
        str: JSON，包含每张图片的详细信息
    """
    try:
        targets = _collect_images(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    results = []
    for src in targets:
        try:
            img = Image.open(src)
            size_kb = round(src.stat().st_size / 1024, 1)
            results.append({
                "file": src.name,
                "path": str(src),
                "size": f"{img.width}x{img.height}",
                "format": img.format or src.suffix.upper().lstrip("."),
                "mode": img.mode,
                "file_size_kb": size_kb,
            })
        except Exception as e:
            results.append({"file": str(src.name), "error": str(e)})

    return json.dumps({"count": len(results), "images": results}, ensure_ascii=False, indent=2)


# ── PDF 水印工具 ────────────────────────────────────────────────────────────────

def _has_cjk(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF or 0x3000 <= ord(c) <= 0x303F for c in text)


def _pick_pdf_font(font_path: Optional[str], text: str):
    """
    返回 fitz.Font 对象（TextWriter 直接接受，会以 CID 字体方式嵌入 PDF）。

    跨机器通用策略，不依赖系统字体：
      1. 用户显式提供 font_path → 验证字形后使用
      2. 文本含 CJK            → PyMuPDF 内置 CJK（DroidSansFallback）
      3. 纯 Latin              → 内置 Helvetica
    """
    import fitz

    if font_path and os.path.exists(font_path):
        try:
            f = fitz.Font(fontfile=font_path)
            if all(f.has_glyph(ord(c)) for c in text if not c.isspace()):
                return f
        except Exception:
            pass

    if _has_cjk(text):
        return fitz.Font(ordering=1)   # 内置简体中文，覆盖简/繁/日/韩+Latin

    return fitz.Font("helv")


def _collect_pdfs(input_path: str) -> list[Path]:
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() != ".pdf":
            raise ValueError(f"不是 PDF 文件：{p.suffix}，请传入 .pdf 文件或文件夹")
        return [p]
    elif p.is_dir():
        files = [f for f in p.iterdir() if f.suffix.lower() == ".pdf"]
        if not files:
            raise ValueError(f"文件夹 {p} 中没有找到 PDF 文件")
        return sorted(files)
    else:
        raise FileNotFoundError(f"路径不存在：{p}")


class PDFWatermarkInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description="PDF 文件路径或包含 PDF 的文件夹路径")
    text: str = Field(..., description="水印文字内容", min_length=1, max_length=100)
    angle: float = Field(default=30.0, description="倾斜角度，正数=逆时针，默认 30", ge=-180, le=180)
    opacity: float = Field(default=0.12, description="透明度 0~1，默认 0.12", ge=0.0, le=1.0)
    font_size: int = Field(default=36, description="字号（点），默认 36", ge=8, le=200)
    gap: int = Field(default=80, description="水印重复间距（点），默认 80（越大越稀疏）", ge=10, le=500)
    color: str = Field(default="128,128,128", description="文字颜色 R,G,B，默认灰色 '128,128,128'")
    suffix: str = Field(default="_wm", description="输出文件名后缀，默认 '_wm'")
    font_path: Optional[str] = Field(default=None, description="字体文件路径（可选，不填自动检测中文字体）")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        parts = v.split(",")
        if len(parts) != 3:
            raise ValueError("color 格式应为 R,G,B，例如 128,128,128")
        for p in parts:
            val = int(p.strip())
            if not 0 <= val <= 255:
                raise ValueError("颜色值应在 0~255 之间")
        return v


@mcp.tool(
    name="pdf_add_watermark",
    annotations={
        "title": "PDF 批量添加满铺斜向水印",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def pdf_add_watermark(params: PDFWatermarkInput) -> str:
    """为 PDF 文件添加满铺斜向平铺水印，支持单个文件或批量处理整个文件夹。

    使用 PyMuPDF 直接写入页面内容流，正确处理旋转页、扫描件等所有 PDF 结构。
    输出为新文件（原文件名+后缀），不覆盖原文件。

    Args:
        params (PDFWatermarkInput): 水印参数，包含：
            - input_path: PDF 文件或文件夹路径
            - text: 水印文字
            - angle: 倾斜角度（默认30度）
            - opacity: 透明度（默认0.12）
            - font_size: 字号点数（默认36）
            - gap: 水印间距点数（默认80）
            - color: R,G,B 颜色字符串（默认灰色）
            - suffix: 输出文件后缀（默认_wm）
            - font_path: 可选字体路径

    Returns:
        str: JSON，包含处理结果列表，每项含 input/output/pages/status/error
    """
    import fitz  # pymupdf

    try:
        targets = _collect_pdfs(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    color_rgb = tuple(int(x.strip()) for x in params.color.split(","))
    r, g, b = [x / 255.0 for x in color_rgb]

    # 字体（跨机器通用，CJK 直接用 PyMuPDF 内置）
    fitz_font = _pick_pdf_font(params.font_path, params.text)
    text_w = fitz_font.text_length(params.text, fontsize=params.font_size)
    step_x = text_w + params.gap
    step_y = params.font_size + params.gap

    results = []
    for src in targets:
        try:
            doc = fitz.open(str(src))
            page_count = len(doc)

            for page in doc:
                # page.rect 已自动处理 /Rotate，始终是显示坐标系
                pw, ph = page.rect.width, page.rect.height
                cx, cy = pw / 2, ph / 2
                diag = math.ceil(math.sqrt(pw ** 2 + ph ** 2))
                n_x = int(diag / step_x) + 2
                n_y = int(diag / step_y) + 2

                # 横排铺满网格（围绕页面中心），通过 morph 旋转整张网格
                writer = fitz.TextWriter(page.rect)
                for i in range(-n_x, n_x + 1):
                    for j in range(-n_y, n_y + 1):
                        x = cx + i * step_x
                        y = cy + j * step_y
                        writer.append(
                            fitz.Point(x, y),
                            params.text,
                            font=fitz_font,
                            fontsize=params.font_size,
                        )
                # 围绕页面中心整体旋转
                morph = (fitz.Point(cx, cy), fitz.Matrix(params.angle))
                writer.write_text(
                    page,
                    color=(r, g, b),
                    opacity=params.opacity,
                    morph=morph,
                )

            out = src.parent / f"{src.stem}{params.suffix}{src.suffix}"
            doc.save(str(out), garbage=4, deflate=True)
            doc.close()

            results.append({
                "input": str(src),
                "output": str(out),
                "pages": page_count,
                "status": "ok",
            })
        except Exception as e:
            results.append({"input": str(src), "status": "error", "error": str(e)})

    summary = f"处理完成：{sum(1 for r in results if r['status'] == 'ok')}/{len(results)} 个文件成功"
    return json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)


# ── DOCX 水印工具 ───────────────────────────────────────────────────────────────

def _collect_docx(input_path: str) -> list[Path]:
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() != ".docx":
            raise ValueError(f"不是 .docx 文件：{p.suffix}（不支持旧版 .doc）")
        return [p]
    elif p.is_dir():
        files = [f for f in p.iterdir() if f.suffix.lower() == ".docx"]
        if not files:
            raise ValueError(f"文件夹 {p} 中没有找到 .docx 文件")
        return sorted(files)
    else:
        raise FileNotFoundError(f"路径不存在：{p}")


# Word 水印模板：mc:AlternateContent 同时提供 DrawingML（现代）和 VML（旧版）
# DrawingML 给 LibreOffice / Word 2010+；VML 兜底给老版本 Word
_DOCX_WATERMARK_TEMPLATE = """\
<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:v="urn:schemas-microsoft-com:vml"
     xmlns:o="urn:schemas-microsoft-com:office:office"
     xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
     xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
     xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:r>
    <w:rPr><w:noProof/></w:rPr>
    <mc:AlternateContent>
      <mc:Choice Requires="wps">
        <w:drawing>
          <wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"
                     relativeHeight="{z_index}" behindDoc="1" locked="0"
                     layoutInCell="1" allowOverlap="1">
            <wp:simplePos x="0" y="0"/>
            <wp:positionH relativeFrom="margin"><wp:align>center</wp:align></wp:positionH>
            <wp:positionV relativeFrom="margin"><wp:align>center</wp:align></wp:positionV>
            <wp:extent cx="{cx}" cy="{cy}"/>
            <wp:effectExtent l="0" t="0" r="0" b="0"/>
            <wp:wrapNone/>
            <wp:docPr id="{shape_id}" name="WatermarkShape{shape_id}"/>
            <wp:cNvGraphicFramePr/>
            <a:graphic>
              <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
                <wps:wsp>
                  <wps:cNvSpPr/>
                  <wps:spPr>
                    <a:xfrm rot="{rot_60k}">
                      <a:off x="0" y="0"/>
                      <a:ext cx="{cx}" cy="{cy}"/>
                    </a:xfrm>
                    <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                    <a:noFill/>
                  </wps:spPr>
                  <wps:txbx>
                    <w:txbxContent>
                      <w:p>
                        <w:pPr><w:jc w:val="center"/></w:pPr>
                        <w:r>
                          <w:rPr>
                            <w:rFonts w:ascii="{font_family}" w:hAnsi="{font_family}" w:eastAsia="{font_family}"/>
                            <w:color w:val="{color_hex}"/>
                            <w:sz w:val="{half_pt}"/>
                            <w:szCs w:val="{half_pt}"/>
                          </w:rPr>
                          <w:t>{text}</w:t>
                        </w:r>
                      </w:p>
                    </w:txbxContent>
                  </wps:txbx>
                  <wps:bodyPr rot="0" wrap="square" anchor="ctr" anchorCtr="1"/>
                </wps:wsp>
              </a:graphicData>
            </a:graphic>
          </wp:anchor>
        </w:drawing>
      </mc:Choice>
      <mc:Fallback>
        <w:pict>
          <v:shape id="WatermarkShape{shape_id}" o:spid="_x0000_s10{shape_id:02d}"
                   type="#_x0000_t136"
                   style="position:absolute;margin-left:0;margin-top:0;width:{width}pt;height:{height}pt;rotation:{angle};z-index:-251655168;mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin"
                   o:allowincell="f" fillcolor="#{color_hex}" stroked="f">
            <v:fill opacity="{opacity}"/>
            <v:textpath style="font-family:'{font_family}';font-size:1pt" string="{text}"/>
          </v:shape>
        </w:pict>
      </mc:Fallback>
    </mc:AlternateContent>
  </w:r>
</w:p>"""


class DocxWatermarkInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input_path: str = Field(..., description=".docx 文件路径或包含 .docx 的文件夹")
    text: str = Field(..., description="水印文字内容", min_length=1, max_length=100)
    angle: float = Field(default=315.0, description="旋转角度（VML 顺时针为正），默认 315=左上→右下", ge=0, le=360)
    opacity: float = Field(default=0.3, description="透明度 0~1，默认 0.3", ge=0.0, le=1.0)
    font_size: int = Field(default=72, description="字号（点），默认 72，影响水印形状大小", ge=12, le=200)
    color: str = Field(default="128,128,128", description="文字颜色 R,G,B，默认灰色")
    suffix: str = Field(default="_wm", description="输出文件名后缀，默认 _wm")
    font_family: Optional[str] = Field(default=None, description="字体名（如 'Microsoft YaHei'），默认按文本自动选择")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        parts = v.split(",")
        if len(parts) != 3:
            raise ValueError("color 格式应为 R,G,B")
        for p in parts:
            val = int(p.strip())
            if not 0 <= val <= 255:
                raise ValueError("颜色值应在 0~255 之间")
        return v


@mcp.tool(
    name="docx_add_watermark",
    annotations={
        "title": "Word 文档批量添加水印",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def docx_add_watermark(params: DocxWatermarkInput) -> str:
    """为 Word 文档（.docx）添加旋转水印，支持单文件或批量处理整个文件夹。

    水印通过 Word 原生页眉机制实现：在每个 section 的页眉里注入 VML 形状，
    Word 自动在每页背景上重复显示。仅支持 .docx，不支持旧版 .doc 或 .docm。

    Args:
        params (DocxWatermarkInput): 水印参数

    Returns:
        str: JSON，包含每个文件的处理结果（input/output/sections/status）
    """
    from docx import Document
    from lxml import etree
    from xml.sax.saxutils import escape as xml_escape

    try:
        targets = _collect_docx(params.input_path)
    except (ValueError, FileNotFoundError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    # 颜色 RGB → HEX
    rgb = tuple(int(x.strip()) for x in params.color.split(","))
    color_hex = "%02X%02X%02X" % rgb

    # 自动选字体：CJK 文本默认用微软雅黑（Mac/Win 均广泛可用），其他用 Arial
    has_cjk = _has_cjk(params.text)
    font_family = params.font_family or ("Microsoft YaHei" if has_cjk else "Arial")

    # 形状尺寸
    char_factor = 1.2 if has_cjk else 0.7
    width_pt = max(120.0, params.font_size * len(params.text) * char_factor)
    height_pt = max(60.0, params.font_size * 1.5)

    # 单位换算：1 pt = 12700 EMU；DrawingML 旋转单位 = 1/60000 度
    EMU_PER_PT = 12700
    cx = int(width_pt * EMU_PER_PT)
    cy = int(height_pt * EMU_PER_PT)
    # VML rotation 顺时针为正；DrawingML rot 也是顺时针为正，单位 1/60000 度
    rot_60k = int(params.angle * 60000) % (360 * 60000)
    half_pt = params.font_size * 2  # w:sz 单位是半点

    results = []
    for src in targets:
        try:
            doc = Document(str(src))
            section_count = len(doc.sections)

            for idx, section in enumerate(doc.sections, start=1):
                wm_xml = _DOCX_WATERMARK_TEMPLATE.format(
                    shape_id=idx,
                    z_index=251655168 + idx,
                    width=round(width_pt, 1),
                    height=round(height_pt, 1),
                    cx=cx,
                    cy=cy,
                    angle=int(params.angle),
                    rot_60k=rot_60k,
                    color_hex=color_hex,
                    opacity=params.opacity,
                    font_family=xml_escape(font_family),
                    half_pt=half_pt,
                    text=xml_escape(params.text),
                )
                wm_elem = etree.fromstring(wm_xml)
                section.header._element.append(wm_elem)

            out = src.parent / f"{src.stem}{params.suffix}{src.suffix}"
            doc.save(str(out))

            results.append({
                "input": str(src),
                "output": str(out),
                "sections": section_count,
                "status": "ok",
            })
        except Exception as e:
            results.append({"input": str(src), "status": "error", "error": str(e)})

    summary = f"处理完成：{sum(1 for r in results if r['status'] == 'ok')}/{len(results)} 个文件成功"
    return json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2)


# ── 启动 ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
