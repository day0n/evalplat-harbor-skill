FROM python:3.12-slim

RUN useradd -m -u 1000 agent

# 文档处理：LibreOffice（doc/docx/xlsx 转换、公式重算）、PDF 文本抽取、OCR、中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates bash jq ripgrep unzip poppler-utils \
        libreoffice-writer libreoffice-calc \
        fonts-noto-cjk fonts-arphic-ukai fonts-arphic-uming \
        tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# 作答与判分共用的解析库（判分在同一镜像内运行，判分时不联网装依赖）
RUN pip install --no-cache-dir \
        markitdown openpyxl pandas python-docx python-pptx pypdf pdfplumber pymupdf PyYAML chardet pytesseract pillow

# 题包材料放在 /app 下（只读）；交付放 /app/output。不要把 Gold、rubric 放进 environment/
COPY input_files/ /app/
RUN chown -R root:root /app && chmod -R a-w /app \
    && mkdir -p /app/output && chown agent:agent /app/output && chmod 755 /app/output
WORKDIR /app
