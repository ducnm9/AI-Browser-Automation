# AI Browser Automation

AI-powered browser automation tool with natural language control.

## Cài đặt và chạy

### 1. Cài dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

playwright install chromium

cp .env.example .env
```

### 2. Khởi động LM Studio

Ứng dụng mặc định dùng LM Studio (local LLM) tại `http://localhost:1234/v1`. Mở LM Studio, load một model, và bật server.

### 3. Chạy CLI

```bash
ai-browser
```

Hoặc:

```bash
python -m ai_browser_automation.main
```

Bạn sẽ thấy prompt `>>>` — nhập lệnh tiếng Việt hoặc tiếng Anh:

```
>>> Mở trang google.com và tìm kiếm "thời tiết Hà Nội"
>>> Đăng nhập Gmail và đọc email mới nhất
>>> Vào shopee.vn, tìm "laptop" và lấy giá 5 sản phẩm đầu tiên
```

Gõ `exit` hoặc `Ctrl+C` để thoát.

### 4. Dùng cloud LLM (tùy chọn)

Nếu muốn dùng OpenAI thay vì local:

```bash
export OPENAI_API_KEY="sk-your-key-here"
export AI_BROWSER_DEFAULT_LLM="openai"
ai-browser
```

Tương tự cho Gemini (`GEMINI_API_KEY`) hoặc Bedrock (`AWS_DEFAULT_REGION`).

### 5. Dùng như library trong code Python

```python
import asyncio
from ai_browser_automation import AIBrowserAutomation
from ai_browser_automation.models.config import AppConfig, LLMProvider

async def main():
    config = AppConfig(
        default_llm=LLMProvider.LM_STUDIO,
        lm_studio_url="http://localhost:1234/v1",
    )
    app = AIBrowserAutomation(config)
    await app.initialize()

    result = await app.chat("Mở google.com và tìm 'AI browser automation'")
    print(result)

    await app.shutdown()

asyncio.run(main())
```

> **Lưu ý quan trọng:** khi input chứa dữ liệu nhạy cảm (mật khẩu, số thẻ, CMND...), hệ thống tự động chuyển sang LM Studio local — không gửi ra cloud.
