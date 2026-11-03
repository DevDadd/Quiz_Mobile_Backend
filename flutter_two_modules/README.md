# QUIZ MOBILE — CHỈ MODULE 2 VÀ MODULE 3

**Tài liệu thiết kế không bị chỉnh sửa.** Đây là mã nguồn thực hiện theo bản PDF đã chốt `02-Lưu Đức Anh - Game thi trắc nghiệm nhanh.pdf`.

## Module 2 — Xem bảng xếp hạng online

- Flutter `lib/module2/leaderboard_page.dart`, `player_statistics_page.dart`, `match_history_page.dart`, `leaderboard_api.dart`.
- Kết nối các Django View có sẵn trong `../leaderboard/views.py` bằng HTTP/JSON.
- API: `GET /leaderboard/leaderboard/?limit=50&offset=0`, `GET /leaderboard/users/{id}/stats/`, `GET /leaderboard/users/{id}/matches/?limit=20&offset=0`.
- Chạy được luồng xem bảng xếp hạng → chọn người chơi → thống kê → xem lịch sử → quay lại; có lỗi kết nối/không có dữ liệu, phân trang.
- Xếp hạng: tổng điểm giảm → trung bình điểm đối thủ giảm → trung bình thời gian thắng tăng. Thống kê và lịch sử tính trên trận `finished`.

## Module 3 — Người chơi thi đấu với máy trên thiết bị

- Flutter `lib/module3/bot_setup_page.dart`, `bot_quiz_page.dart`, `bot_result_page.dart`, `bot_game_controller.dart`.
- Các lớp DAO đúng sơ đồ: `QuestionDAO` chọn câu hỏi từ ngân hàng có sẵn trên thiết bị; `MatchDAO` lưu trận/đáp án/người tham gia bằng **SQLite cục bộ**.
- 10 câu, 60 giây; bot `easy` / `medium` / `hard`; xử lý `break` (thiếu câu hỏi), `loop` chọn đáp án, `alt` nộp bài/hết giờ, rồi `finishMatch(reason)` → `evaluateOutcome(match)` → `saveResult(match)` → màn hình kết quả.
- Luật theo đề: nếu chỉ một bên đúng **10/10** thì bên đó thắng; nếu cả hai đúng hết, bên nhanh hơn thắng; nếu cả hai đều sai ít nhất một câu thì **hòa** (ví dụ 8/10 và 6/10). Thắng 1, hòa 0.5, thua 0.
- Không gọi Django, **không cập nhật `users.total_score` hoặc BXH online**.
- `assets/questions_seed.json`: **36 câu hỏi mẫu** dùng để demo, chưa phải ngân hàng câu hỏi hoàn chỉnh của nhóm. Thay nguồn câu hỏi đúng khi có tài sản nhóm; cần cài lại app/xóa dữ liệu cũ khi thay seed đã khởi tạo.

## Chạy demo Flutter trên máy của bạn

Gói ZIP gốc chỉ có backend Python; **không có source Flutter cũ**. Vì vậy `flutter_two_modules` là project Flutter hai module bổ sung, không phải bản sửa vào frontend không được gửi. Nó có `pubspec.yaml`, `lib/`, `assets/`, `test/` nhưng chưa có thư mục nền tảng Android do môi trường tạo file hiện tại không có Flutter SDK.

Trên máy đã cài Flutter SDK:

```bash
cd flutter_two_modules
flutter create --platforms=android --project-name quiz_mobile_two_modules .
python scripts/enable_dev_http.py
flutter pub get
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` chỉ dành cho Android Emulator để kết nối Django đang chạy trên PC. Trên điện thoại thật hãy đổi sang IP LAN của máy tính và cấu hình `ALLOWED_HOSTS` thích hợp ở backend. Nếu cần chạy trên môi trường không phải Android/iOS, phải thay plugin lưu dữ liệu `sqflite` bằng bản hỗ trợ nền tảng đó. Cấu hình HTTP thường (`usesCleartextTraffic`) chỉ áp dụng **demo local**, không dùng cho bản triển khai thật.

**Backend**: Cài `requirements.txt`, chuẩn bị PostgreSQL và biến môi trường trong `.env` riêng, sau đó `python manage.py runserver 0.0.0.0:8000`. Mình không đưa file `.env` chứa bí mật trong bản ZIP mới. **M01 / đăng ký / đăng nhập không bị sửa.** Backend cần dữ liệu tài khoản và các trận đã hoàn thành để M02 hiện kết quả.

Demo `main.dart` chỉ có hai nút **M02 / M03**; đây là màn hình mở module cho mục đích kiểm tra, **không tự tạo hoặc sửa chức năng đăng nhập**. Khi ghép với Flutter app hiện có, gọi `LeaderboardPage(api: LeaderboardApi(baseUrl: url))` và `BotSetupPage(controller: BotGameController())` từ trang chủ sau đăng nhập.

## Kiểm thử và giới hạn

- Python `verify_backend_m02.py`: đã chạy với SQLite **test double** để kiểm tra SQL xếp hạng, phân trang, thống kê và lịch sử. Không thay cho test trên PostgreSQL thực tế.
- Flutter `test/module2_leaderboard_api_test.dart`, `test/module3_match_rules_test.dart`, `test/module3_controller_test.dart` có sẵn, **chưa chạy được trong môi trường tạo gói vì không có Flutter/Dart SDK**. Vui lòng chạy `flutter test` trên máy.
- Khác biệt kỹ thuật duy nhất so với chữ ký phương thức UML: hàm có truy cập SQLite/HTTP trả `Future<T>` của Dart thay cho `T` đồng bộ, nhưng **giữ tên, tham số nghiệp vụ, thứ tự xử lý và kết quả** như sơ đồ. Các phương thức giao diện được triển khai trong `State` của Flutter `StatefulWidget` theo quy ước Flutter.
- Code phía M03 dùng dữ liệu cục bộ như báo cáo đã chốt; Django `matches/*` server được **giữ nguyên** cho chức năng khác. Không dùng code Django BOT để giải thích Sequence M03 này.

## Đối chiếu sơ đồ → file code

| Hình / luồng | Thực hiện tại |
|---|---|
| Hình 5: `LeaderboardPage`, `PlayerStatisticsPage`, `MatchHistoryPage`, `LeaderboardApi` | `lib/module2/*.dart` |
| Hình 5: `LeaderboardView.get`, `UserStatsView.get`, `UserMatchesView.get` | `../leaderboard/views.py` |
| Hình 6: Ranking → Stats → History → back | `lib/module2/*_page.dart`, `leaderboard_api.dart` |
| Hình 7: `BotSetupPage`, `BotQuizPage`, `BotResultPage`, `BotGameController` | `lib/module3/bot_*` |
| Hình 7: `QuestionDAO`, `MatchDAO`, entities | `lib/module3/question_dao.dart`, `match_dao.dart`, `models.dart` |
| Hình 8: start → pick → generate bot → create → choose → submit/timeout → score → save → show result | `lib/module3/bot_game_controller.dart` và các Page |

**Không chỉnh bất kỳ nội dung nào của PDF thiết kế, không viết lại sơ đồ M01.**
