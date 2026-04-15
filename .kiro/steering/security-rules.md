---
inclusion: auto
---

# Security Rules — AI Browser Automation

## Nguyên Tắc Bảo Mật Cốt Lõi

1. **Local-First**: Mặc định mọi xử lý diễn ra local. Cloud chỉ dùng khi user chủ động chọn.
2. **Zero Trust Cloud**: Mọi dữ liệu gửi cloud PHẢI được sanitize trước.
3. **No Telemetry**: Không gửi bất kỳ dữ liệu sử dụng nào ra bên ngoài.

## Quy Tắc Code Bảo Mật

### API Keys & Credentials
- KHÔNG hardcode API keys, passwords, hoặc secrets trong source code
- Sử dụng environment variables hoặc encrypted config file
- API keys trong config PHẢI được mã hóa khi lưu disk
- KHÔNG log API keys — mask trong tất cả log output

```python
# Good
api_key = os.environ.get("OPENAI_API_KEY") or config.get_encrypted("openai_api_key")

# Bad
api_key = "sk-abc123..."
```

### Sensitive Data Handling
- Mọi user input PHẢI đi qua `SecurityLayer.detect_sensitive_data()` trước khi gửi cloud
- Dữ liệu nhạy cảm (passwords, credit cards, CMND) PHẢI được sanitize hoặc route sang local LLM
- Mapping để restore sensitive data KHÔNG được persist — chỉ giữ trong memory
- Khi process kết thúc, sensitive data mapping PHẢI được clear

### Logging
- KHÔNG log nội dung user input chứa sensitive data
- Sử dụng `SecurityLayer` để mask trước khi log
- Log files KHÔNG chứa: passwords, API keys, credit card numbers, CMND/CCCD

```python
# Good
logger.info("Processing command: %s", security.mask_for_log(user_input))

# Bad
logger.info("Processing command: %s", user_input)
```

### Browser Data
- Cookies và session data KHÔNG được persist giữa các phiên
- Browser profile dùng temporary directory, xóa khi shutdown
- Screenshot chỉ giữ trong memory, không lưu disk trừ khi user yêu cầu

### Dependencies
- Chỉ sử dụng dependencies từ trusted sources (PyPI official)
- Pin exact versions trong `pyproject.toml` cho production
- Audit dependencies định kỳ với `pip-audit`
