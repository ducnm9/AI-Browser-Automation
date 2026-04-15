# Tài Liệu Yêu Cầu: AI Browser Automation

## Giới Thiệu

Tài liệu này mô tả các yêu cầu chức năng và phi chức năng cho công cụ AI Browser Automation — một ứng dụng chạy hoàn toàn trên máy tính cá nhân (local), cho phép người dùng điều khiển trình duyệt web thông qua ngôn ngữ tự nhiên (tiếng Việt và tiếng Anh). Hệ thống tích hợp nhiều LLM provider (OpenAI, Gemini, Bedrock, LM Studio) với ưu tiên bảo mật dữ liệu tuyệt đối, sử dụng Playwright làm browser engine chính với fallback sang Selenium. Kiến trúc module hóa tuân thủ Strategy Pattern, Dependency Injection và Factory Pattern để dễ mở rộng và kiểm thử.

## Thuật Ngữ

- **Hệ_Thống**: Ứng dụng AI Browser Automation tổng thể, bao gồm facade AIBrowserAutomation
- **NL_Processor**: Thành phần xử lý ngôn ngữ tự nhiên, phân tích câu lệnh người dùng thành intent và parameters
- **LLM_Router**: Thành phần điều phối request đến các LLM provider, quản lý fallback chain và chính sách bảo mật
- **Task_Planner**: Thành phần chuyển đổi intent thành kế hoạch thực thi (execution plan) gồm các bước cụ thể
- **Action_Executor**: Thành phần thực thi các bước hành động trên trình duyệt, xử lý lỗi và retry thông minh
- **Browser_Engine**: Lớp trừu tượng (ABC) cho Playwright/Selenium, cung cấp API thống nhất thao tác trình duyệt
- **Security_Layer**: Thành phần bảo vệ dữ liệu nhạy cảm, phát hiện và ẩn danh hóa trước khi gửi cloud
- **LLM_Provider**: Một dịch vụ AI cung cấp khả năng xử lý ngôn ngữ, implement BaseLLMProvider ABC (OpenAI, Gemini, Bedrock, LM Studio)
- **Intent**: Ý định hành động được trích xuất từ câu lệnh ngôn ngữ tự nhiên của người dùng
- **Execution_Plan**: Kế hoạch thực thi gồm danh sách các ActionStep cụ thể trên trình duyệt
- **Action_Step**: Một bước hành động đơn lẻ trong execution plan (click, type, navigate, wait, extract, scroll, screenshot)
- **Dữ_Liệu_Nhạy_Cảm**: Thông tin cá nhân như mật khẩu, số thẻ tín dụng, CMND/CCCD, email cá nhân, số điện thoại
- **Local_LLM**: LLM chạy trên máy cá nhân (LM Studio), không gửi dữ liệu ra internet
- **Cloud_LLM**: LLM chạy trên cloud (OpenAI, Gemini, Bedrock), yêu cầu kết nối internet
- **Sanitize**: Quá trình thay thế dữ liệu nhạy cảm bằng placeholder trước khi gửi đến cloud
- **Page_Context**: Ngữ cảnh trang web hiện tại bao gồm URL, title, DOM summary và danh sách phần tử tương tác được

## Yêu Cầu

### Yêu Cầu 1: Xử Lý Ngôn Ngữ Tự Nhiên

**User Story:** Là người dùng, tôi muốn nhập lệnh bằng ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh) để điều khiển trình duyệt, để tôi không cần biết kỹ thuật lập trình hay selector CSS/XPath.

#### Tiêu Chí Chấp Nhận

1. WHEN người dùng nhập một câu lệnh bằng tiếng Việt hoặc tiếng Anh, THE NL_Processor SHALL phân tích câu lệnh và trả về danh sách ParsedIntent không rỗng, mỗi intent có intent_type thuộc tập IntentType và confidence trong khoảng [0.0, 1.0]
2. WHEN câu lệnh người dùng chứa nhiều hành động kết hợp (ví dụ: "Đăng nhập Gmail và đọc email mới nhất"), THE NL_Processor SHALL trả về một ParsedIntent có intent_type là COMPOSITE với danh sách sub_intents không rỗng
3. WHEN một intent có confidence thấp hơn 0.7, THE Hệ_Thống SHALL tạo câu hỏi làm rõ và gửi lại cho người dùng thay vì thực thi
4. WHEN câu lệnh người dùng là chuỗi rỗng hoặc chỉ chứa khoảng trắng, THE NL_Processor SHALL từ chối xử lý và trả về thông báo lỗi phù hợp

### Yêu Cầu 2: Lập Kế Hoạch Thực Thi

**User Story:** Là người dùng, tôi muốn hệ thống tự động lập kế hoạch các bước thực thi cụ thể từ lệnh ngôn ngữ tự nhiên, để các thao tác trên trình duyệt được thực hiện chính xác và có trình tự.

#### Tiêu Chí Chấp Nhận

1. WHEN nhận được danh sách ParsedIntent và Page_Context hiện tại, THE Task_Planner SHALL tạo một Execution_Plan chứa danh sách Action_Step không rỗng, mỗi step có action_type, selector_strategy, selector_value và timeout_ms hợp lệ
2. WHEN một bước trong Execution_Plan thất bại, THE Task_Planner SHALL tạo kế hoạch thay thế (replan) dựa trên thông tin lỗi và screenshot trang hiện tại
3. THE Task_Planner SHALL xác định selector strategy phù hợp (css, xpath, text, ai_vision) cho từng phần tử mục tiêu dựa trên ngữ cảnh trang

### Yêu Cầu 3: Thực Thi Hành Động Trên Trình Duyệt

**User Story:** Là người dùng, tôi muốn hệ thống tự động thực thi các thao tác trên trình duyệt (click, nhập liệu, điều hướng, trích xuất dữ liệu) một cách chính xác, để tôi không cần thao tác thủ công.

#### Tiêu Chí Chấp Nhận

1. WHEN nhận được một Execution_Plan, THE Action_Executor SHALL thực thi tuần tự từng Action_Step và trả về danh sách ActionResult có số lượng bằng số step đã thực thi, với thứ tự tương ứng
2. WHEN một Action_Step thất bại, THE Action_Executor SHALL thực hiện smart retry bằng cách dùng AI phân tích lỗi và đề xuất selector hoặc cách tiếp cận thay thế, tối đa số lần retry bằng giá trị retry_count của step đó
3. WHEN smart retry vẫn thất bại, THE Action_Executor SHALL yêu cầu Task_Planner replan và thử thực thi kế hoạch thay thế
4. IF tất cả các cách retry và replan đều thất bại cho một step, THEN THE Action_Executor SHALL dừng thực thi các step còn lại và trả về kết quả với thông báo lỗi chi tiết
5. WHEN action_type là "extract", THE Action_Executor SHALL trả về ActionResult có extracted_data chứa dữ liệu trích xuất từ trang web
6. THE Action_Executor SHALL ghi nhận duration_ms thực tế cho mỗi ActionResult, giá trị này phải >= 0

### Yêu Cầu 4: Điều Phối LLM Provider

**User Story:** Là người dùng, tôi muốn hệ thống tự động chọn LLM provider phù hợp (local hoặc cloud) dựa trên nội dung lệnh và chính sách bảo mật, để dữ liệu nhạy cảm luôn được bảo vệ mà vẫn tận dụng được hiệu năng cloud khi an toàn.

#### Tiêu Chí Chấp Nhận

1. WHILE request chứa dữ liệu nhạy cảm (is_sensitive = True), THE LLM_Router SHALL chỉ gửi request đến Local_LLM (LM Studio), không gửi đến bất kỳ Cloud_LLM nào
2. WHEN LLM_Provider mặc định không khả dụng, THE LLM_Router SHALL tự động chuyển sang provider tiếp theo trong fallback chain cho đến khi tìm được provider khả dụng
3. IF tất cả LLM_Provider đã đăng ký đều không khả dụng, THEN THE LLM_Router SHALL thông báo lỗi LLMUnavailableError bao gồm danh sách provider đã thử
4. THE LLM_Router SHALL đảm bảo mỗi provider chỉ được thử tối đa một lần trong một vòng fallback
5. WHEN đăng ký một LLM_Provider mới, THE LLM_Router SHALL cho phép thêm provider thông qua register_provider() mà không cần sửa đổi code hiện tại

### Yêu Cầu 5: Bảo Mật Dữ Liệu

**User Story:** Là người dùng, tôi muốn dữ liệu cá nhân (mật khẩu, số thẻ, CMND) được bảo vệ tuyệt đối, không bị gửi ra ngoài internet khi không cần thiết, để tôi yên tâm sử dụng công cụ với các tài khoản quan trọng.

#### Tiêu Chí Chấp Nhận

1. WHEN văn bản chứa dữ liệu nhạy cảm (email, số điện thoại VN, số thẻ tín dụng, CMND/CCCD, mật khẩu), THE Security_Layer SHALL phát hiện và trả về danh sách tất cả các mục Dữ_Liệu_Nhạy_Cảm tìm thấy
2. WHEN dữ liệu cần gửi đến Cloud_LLM, THE Security_Layer SHALL thay thế tất cả Dữ_Liệu_Nhạy_Cảm bằng placeholder và tạo mapping để khôi phục
3. WHEN nhận kết quả từ Cloud_LLM chứa placeholder, THE Security_Layer SHALL khôi phục Dữ_Liệu_Nhạy_Cảm từ mapping, đảm bảo restore(sanitize(text)) trả về text gốc
4. THE Security_Layer SHALL hỗ trợ custom sensitive patterns từ SecurityPolicy ngoài các pattern mặc định (builtin)
5. WHEN văn bản rỗng được kiểm tra, THE Security_Layer SHALL trả về danh sách rỗng mà không gây lỗi
6. THE Hệ_Thống SHALL không ghi log nội dung chứa Dữ_Liệu_Nhạy_Cảm — tất cả phải được mask trước khi log
7. THE Hệ_Thống SHALL mã hóa API keys và credentials khi lưu trữ trên disk bằng thư viện cryptography
8. THE Hệ_Thống SHALL không gửi bất kỳ dữ liệu telemetry nào ra bên ngoài

### Yêu Cầu 6: Quản Lý Trình Duyệt

**User Story:** Là người dùng, tôi muốn hệ thống quản lý trình duyệt một cách ổn định và linh hoạt, hỗ trợ nhiều loại trình duyệt, để tôi có thể tự động hóa trên bất kỳ trang web nào.

#### Tiêu Chí Chấp Nhận

1. THE Browser_Engine SHALL cung cấp API thống nhất cho các thao tác: launch, navigate, click, type_text, extract_text, screenshot, get_page_context và close
2. WHEN Playwright không khả dụng, THE Hệ_Thống SHALL tự động chuyển sang Selenium làm browser engine dự phòng
3. WHEN trích xuất Page_Context, THE Browser_Engine SHALL trả về danh sách tối đa 50 phần tử tương tác được (a, button, input, select, textarea, role="button", onclick) đang hiển thị trên trang
4. WHEN trình duyệt được đóng (shutdown), THE Browser_Engine SHALL xóa toàn bộ cookies, session data và temporary profile directory
5. THE Browser_Engine SHALL hỗ trợ cả chế độ headless và có giao diện (headed) theo cấu hình người dùng

### Yêu Cầu 7: Quản Lý Hội Thoại

**User Story:** Là người dùng, tôi muốn hệ thống nhớ ngữ cảnh hội thoại trước đó, để tôi có thể ra lệnh tiếp nối mà không cần lặp lại thông tin.

#### Tiêu Chí Chấp Nhận

1. WHEN người dùng gửi lệnh mới, THE Hệ_Thống SHALL lưu lượt hội thoại (user và assistant) vào ConversationHistory kèm timestamp và danh sách actions_taken
2. WHILE số lượt hội thoại vượt quá max_context_turns, THE Hệ_Thống SHALL tự động cắt bớt các lượt cũ nhất để giữ trong giới hạn context window
3. THE Hệ_Thống SHALL chỉ chấp nhận role là "user" hoặc "assistant" cho mỗi ConversationTurn
4. THE Hệ_Thống SHALL từ chối ConversationTurn có content rỗng

### Yêu Cầu 8: Cấu Hình Hệ Thống

**User Story:** Là người dùng, tôi muốn cấu hình linh hoạt các thông số hệ thống (LLM provider, browser type, timeout), để tôi có thể tùy chỉnh theo nhu cầu và môi trường của mình.

#### Tiêu Chí Chấp Nhận

1. THE Hệ_Thống SHALL validate rằng openai_api_key bắt đầu bằng "sk-" nếu được cung cấp
2. THE Hệ_Thống SHALL validate rằng lm_studio_url là URL hợp lệ
3. THE Hệ_Thống SHALL validate rằng action_timeout_ms nằm trong khoảng (0, 60000]
4. THE Hệ_Thống SHALL validate rằng max_retries nằm trong khoảng [0, 10]
5. THE Hệ_Thống SHALL mặc định sử dụng Local_LLM (LM Studio) làm provider mặc định để đảm bảo bảo mật

### Yêu Cầu 9: Pipeline Xử Lý Chính

**User Story:** Là người dùng, tôi muốn chỉ cần nhập một câu lệnh duy nhất và hệ thống tự động hoàn thành toàn bộ quy trình từ phân tích đến thực thi, để trải nghiệm sử dụng đơn giản và liền mạch.

#### Tiêu Chí Chấp Nhận

1. WHEN người dùng nhập lệnh hợp lệ, THE Hệ_Thống SHALL thực thi pipeline hoàn chỉnh: kiểm tra bảo mật → phân tích NL → lập kế hoạch → thực thi → trả kết quả
2. WHEN pipeline hoàn thành thành công, THE Hệ_Thống SHALL trả về chuỗi mô tả kết quả và cập nhật ConversationHistory
3. IF pipeline thất bại ở bất kỳ bước nào, THEN THE Hệ_Thống SHALL trả về thông báo lỗi chi tiết và đảm bảo trình duyệt ở trạng thái ổn định
4. WHEN lệnh chứa Dữ_Liệu_Nhạy_Cảm, THE Hệ_Thống SHALL tự động chuyển sang xử lý bằng Local_LLM trước khi thực thi pipeline
