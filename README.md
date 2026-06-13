# 📄 Mac 文档翻译器

将 **Word (.docx)** 和 **PDF** 文件逐页翻译为**简体中文**，调用 **DeepSeek API**。
保留原文格式、图片、表格，翻译完毕后自动生成术语表。

## 功能特性

- ✅ 支持 Word (.docx) 和 PDF 两种输入格式
- ✅ **逐页翻译**：大文档不会被截断，确保每一页都被翻译
- ✅ 保留原始格式：字体、加粗、斜体、颜色、对齐方式
- ✅ 保留图片和表格
- ✅ 自动 OCR：扫描件 PDF 自动使用 Tesseract 识别文字
- ✅ **术语表生成**：翻译完成后自动提取专有名词和领域术语
- ✅ 双格式输出：可选 Word (.docx) 或 Markdown (.md)
- ✅ 断点续传：长时间翻译任务中断后可恢复
- ✅ 并发翻译：多页并行翻译，提升速度
- ✅ **Web 界面 + 命令行**两种使用方式
- ✅ 配置灵活：API Key / 模型 / 分页大小 / 并发数均可自定义

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/lepHySicS/doc-translator.git
cd doc-translator
```

### 2. 创建虚拟环境并安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "."
```

### 3. 安装系统依赖（仅扫描件 PDF OCR 需要）

```bash
brew install tesseract tesseract-lang poppler
```

> 如果你不需要 OCR 功能（普通文字型 PDF 不需要），可以跳过这一步。

### 4. 设置 API Key

```bash
# 方式一：设置环境变量（推荐）
export DEEPSEEK_API_KEY="sk-your-api-key"

# 方式二：创建 .env 文件
echo 'DEEPSEEK_API_KEY=sk-your-api-key' > .env

# 方式三：通过命令行参数传入
doc-translator -i doc.docx --api-key sk-your-api-key
```

DeepSeek API Key 获取地址：[platform.deepseek.com](https://platform.deepseek.com)

## 使用方式

### 🌐 Web 界面（推荐）

```bash
source .venv/bin/activate
python -m doc_translator.webui
```

浏览器会自动打开 `http://127.0.0.1:7860`，在界面中：

1. 上传文档
2. 填写 API Key
3. 选择输出格式
4. 点击「开始翻译」
5. 下载翻译结果

### 💻 命令行

#### 基础用法

```bash
# 翻译单个 Word 文档
doc-translator -i document.docx

# 翻译 PDF
doc-translator -i paper.pdf

# 翻译多个文件
doc-translator -i report.docx thesis.pdf

# 输出为 Markdown
doc-translator -i document.docx --format md

# 指定输出目录
doc-translator -i document.docx -o ./my_translations
```

#### 完整参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `-i, --input` | 输入文件路径（必填） | - |
| `-o, --output-dir` | 输出目录 | `./translated/` |
| `-f, --format` | 输出格式：`docx` 或 `md` | `docx` |
| `--model` | DeepSeek 模型 | `deepseek-chat` |
| `--api-base-url` | API 地址 | `https://api.deepseek.com` |
| `--api-key` | API Key | `$DEEPSEEK_API_KEY` |
| `--chars-per-page` | 每页近似字符数（Word） | `3000` |
| `-w, --workers` | 并发翻译数 | `3` |
| `--temperature` | 翻译温度 (0.0-1.0) | `0.1` |
| `--ocr-force` | 强制 OCR | `false` |
| `--ocr-engine` | OCR 引擎：`tesseract` / `paddle` | `tesseract` |
| `--no-vocabulary` | 跳过术语表 | `false` |
| `--dry-run` | 仅解析预览，不调用 API | - |
| `-v, --verbose` | 详细日志 | - |
| `-q, --quiet` | 静默模式 | - |

#### 高级示例

```bash
# 预览文档有多少页会被翻译（不消耗 API token）
doc-translator -i large_doc.docx --dry-run -v

# 使用自定义模型 + 低温度保证一致性
doc-translator -i legal_contract.docx \
    --model deepseek-chat \
    --temperature 0.0 \
    --chars-per-page 2000

# 扫描件 PDF 强制 OCR
doc-translator -i scanned_book.pdf --ocr-force --ocr-engine tesseract

# 批量翻译并输出 Markdown
doc-translator -i *.docx -f md -o ./translated_md
```

## 翻译效果示例

### 输入 (DOCX)

```
Machine learning is a subset of artificial intelligence (AI)
that enables systems to learn and improve from experience
without being explicitly programmed.
```

### 输出 (DOCX)

```
机器学习是人工智能（AI）的一个子集，
它使系统能够从经验中学习和改进，
而无需显式编程。
```

### 术语表 (自动生成)

| English Term | 中文翻译 | 备注 |
|---|---|---|
| Artificial Intelligence | 人工智能 | 标准术语 |
| Machine Learning | 机器学习 | 标准术语 |

## 架构

```
doc-translator/
├── pyproject.toml
└── src/doc_translator/
    ├── cli.py               # 命令行入口
    ├── webui.py             # Gradio Web 界面
    ├── config.py            # 配置管理（env + CLI）
    ├── document.py          # 统一数据模型
    ├── translator.py        # DeepSeek API + 分段翻译 + 重试
    ├── vocabulary.py        # 术语表提取
    ├── ocr.py               # OCR 模块
    ├── token_counter.py     # Token 计数
    ├── reader/
    │   ├── docx_reader.py   # Word 解析 + 字符分页桶
    │   └── pdf_reader.py    # PDF 解析 + OCR 回退
    └── writer/
        ├── docx_writer.py   # 格式保真 DOCX 输出
        └── markdown_writer.py  # Markdown 输出
```

### 核心设计

- **DOCX 逐页翻译**：Word 无固定分页，采用字符数分页桶策略（默认 3000 字符/页），在段落边界切分，翻译后按原序重建
- **分段对齐**：每页用 `---SEGMENT---` 分隔符拼接多个段落，API 返回同样分隔的翻译，保证 1:1 对齐
- **格式保留**：解析时提取每个 Run 的字体/大小/颜色/加粗/斜体，输出时逐 Run 重建
- **断点续传**：每页翻译结果写入 `.progress/` JSON，重启自动跳过已完成页

## 常见问题

### Q: API 调用报 401 错误？

检查 API Key 是否正确设置：
```bash
echo $DEEPSEEK_API_KEY
```

### Q: PDF 翻译后文本丢失？

可能是扫描件 PDF，请使用 `--ocr-force` 参数：
```bash
doc-translator -i scanned.pdf --ocr-force
```

### Q: Word 文档页数不准确？

Word 本身没有固定分页。`--chars-per-page` 控制近似分页，调整该值可控制每页文本量：
```bash
doc-translator -i doc.docx --chars-per-page 5000
```

### Q: 如何估算翻译费用？

使用 `--dry-run` 预览页数和字符数，不调用 API：
```bash
doc-translator -i doc.docx --dry-run -v
```

### Q: OCR 失败怎么办？

确保已安装系统依赖：
```bash
brew install tesseract tesseract-lang poppler
tesseract --list-langs | grep chi_sim  # 确认中文语言包已安装
```

可选安装 PaddleOCR 获得更好的中文识别：
```bash
pip install paddleocr paddlepaddle
doc-translator -i scanned.pdf --ocr-force --ocr-engine paddle
```

## 依赖

- Python >= 3.11
- 系统：macOS（支持 Apple Silicon 和 Intel）
- DeepSeek API Key

## License

MIT
