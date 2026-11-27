Tiếng Việt | [English](BENCHMARK.md)

# Đo chịu tải

Một máy chủ bảng gánh được bao nhiêu máy, có số đo, vượt mức đó thì chuyện gì xảy ra, và cần nhiều hơn thì làm gì. Các con số của riêng máy chủ Python lấy từ [`tests/load/load_test.py`](../tests/load/load_test.py): chạy nó trên máy chủ của bạn để có số của bạn. Các con số trên Linux có bộ nhận Go lấy từ công cụ ngoài repo, nêu trong mục đó.

## Tóm tắt

| | Trước (0.49.1) | Sau (từ bản 0.50.0) |
|---|---|---|
| Phần việc của máy chủ cho một lần gửi, 300 máy | 79 ms | 0,5 ms |
| Phần việc của máy chủ cho một lần gửi, 10.000 máy | (chưa đo, 1,3 giây ở 5.000 máy) | 0,6 ms |
| Dựng bảng, 10.000 máy | (chưa đo, 1,4 giây ở 5.000 máy) | 164 ms, lúc đo nhiều nhất 2 giây một lần cho mỗi vai (từ bản 0.50.0 là 0,5 giây, `VIEW_CACHE_SECONDS`) |
| 300 máy gửi mỗi 10 giây, 30 bảng đang mở | Sập: câu trả lời mất 19–24 giây, 20% lần gửi và 33% lần đọc bị cắt | p95 gửi 5 ms, đọc 43 ms, 0 lỗi, 10% một nhân CPU |
| Số lần gửi mỗi giây nhận được, 300 máy | khoảng 12 | 400–600 |
| Khi tới nhiều hơn mức nhận được | Mọi yêu cầu chờ tới khi tất cả hết giờ | Lần gửi và người chưa đăng nhập nhận ngay 503 kèm `Retry-After`; người đã đăng nhập vẫn xem được bảng |

**Một lần gửi không còn tốn thêm khi số máy tăng.** Trước đây mỗi lần gửi và mỗi lần đọc bảng đều làm sạch lại dữ liệu 8 ngày của mọi máy, nên phần việc tăng theo từng máy thêm vào. Giờ lần gửi mới nhất của mỗi máy được làm sạch một lần rồi giữ trong bộ nhớ.

**Mặc định vẫn là 300 máy (`MAX_DEVICES`); nâng được trong `/etc/ai-worker.env`.** Mỗi máy là một dòng: một người có laptop, máy bàn và Codex là ba máy, nên 300 máy là khoảng 100 tới 150 người. Mã gánh được nhiều hơn rất nhiều: tới 10.000 máy mới đo trên máy Mac (bên dưới), và máy chủ Python một mình, không có bộ nhận Go, chưa được đo trên máy chủ Linux; các số đo Linux phía dưới là có bộ nhận Go. Cỡ nào cài thế nào: [INSTALL.vi.md](INSTALL.vi.md#chọn-cách-cài-theo-quy-mô).

## Cách đo

```bash
python3 tests/load/load_test.py --json load.json
```

```bash
python3 tests/load/load_test.py --scale 20,300,1000,3000,5000,10000
```

- Bài đo bật đúng máy chủ thật (`server/webhook.py`) trên 127.0.0.1 trong một thư mục tạm, chạy thành tiến trình riêng, và không nói chuyện với nơi nào khác. Không thể trỏ nó vào bảng thật.
- Mỗi máy giả gửi đúng thứ plugin gửi, đúng cỡ và dạng: chi phí theo giờ của 8 ngày, khoảng 12 KB.
- Mỗi bảng đang mở đọc `/data` mỗi 10 giây, như trang thật lúc đo. Từ bản 0.50.0 bảng đang hiện trên màn hình hỏi mỗi giây (tab nằm dưới nền hỏi mỗi 10 giây), nên 30 bảng mở nay hỏi dày gấp mười so với các lượt này; bản dựng chúng dùng chung vẫn chỉ được làm nhiều nhất một lần mỗi `VIEW_CACHE_SECONDS`.
- Lượt **office**: 20, 50, 150 và 300 máy, mỗi máy gửi mỗi 10 giây (gấp ba mức nhiều nhất của plugin lúc đo, khi đó là 30 giây một lần) hoặc mỗi 60 giây (ngày thường). Từ bản 0.50.0 plugin gửi một giây sau khi số liệu hay trạng thái của nó đổi, nhiều nhất 2 giây một lần, và từ bản 0.50.15 chỉ gửi các giờ đã đổi, nên máy đang bận nay gửi dày hơn và mỗi lần ít hơn so với các lượt này. Cứ mười máy có một bảng đang mở.
- Lượt **stress**: một số client cố định gửi, hoặc đọc, lại ngay khi nhận câu trả lời, để tìm mức trần.
- **scale**: quá 300 máy thì máy chủ từ chối máy mới qua HTTP, nên phần này gọi thẳng mã của máy chủ trong cùng tiến trình và đo một lần gửi, một lần dựng bảng.
- Mỗi máy giả ghi danh bằng khoá chung rồi gửi bằng khoá riêng từ đó, như plugin. Lượt stress và lượt tìm trần nới giới hạn số lần gửi mỗi máy (`INGEST_BURST`, `INGEST_PER_SECOND`), để đo máy chủ chứ không đo giới hạn đó.
- p95 nghĩa là 95% yêu cầu xong trong thời gian đó.

Máy đo: Mac chip Apple M-series, 15 nhân, Python 3.15, máy chủ và bài đo chạy cùng một máy.

## Kết quả trước khi sửa (0.49.1)

| Số máy | Gửi mỗi 10 giây | Gửi mỗi 60 giây |
|---|---|---|
| 20 | p95 16 ms, CPU 3% | p95 17 ms, CPU 1% |
| 50 | p95 30 ms, CPU 11% | p95 29 ms, CPU 3% |
| 150 | p95 236 ms, CPU 67% | p95 77 ms, CPU 20% |
| 300 | sập (xem trên), CPU 100% | p95 494 ms, CPU 67% |

Lượt stress kẹt ở khoảng 12 yêu cầu mỗi giây dù 4, 16 hay 32 client cùng hỏi: một nhân CPU đã đầy.

| Số máy | 300 | 1.000 | 3.000 | 5.000 |
|---|---|---|---|---|
| Một lần gửi | 79 ms | 293 ms | 821 ms | 1.339 ms |
| Một lần dựng bảng | 81 ms | 312 ms | 861 ms | 1.446 ms |

Profile ở 300 máy cho thấy khoảng 90% thời gian nằm ở việc làm sạch lại dữ liệu vốn đã được làm sạch lúc nhận.

## Kết quả sau khi sửa

Lượt **office**, gửi và đọc, tất cả 0 lỗi và 0 lần gửi trễ:

| Số máy | Mỗi 10 giây: gửi p95 / đọc p95 / CPU | Mỗi 60 giây: gửi p95 / đọc p95 / CPU |
|---|---|---|
| 20 | 5 ms / 6 ms / 0,6% | 5 ms / 7 ms / 0,3% |
| 50 | 5 ms / 12 ms / 1,8% | 5 ms / 12 ms / 0,4% |
| 150 | 5 ms / 27 ms / 4,9% | 5 ms / 26 ms / 1,7% |
| 300 | 5 ms / 43 ms / 9,5% | 5 ms / 43 ms / 3,2% |

Bộ nhớ máy chủ nằm trong khoảng 42 tới 64 MB.

Lượt **stress**, đã có 300 máy:

| Client | Lần gửi mỗi giây | p95 | Ghi chú |
|---|---|---|---|
| 4 | 629 | 12 ms | |
| 16 | 416 | 54 ms | |
| 32 | 429 | 101 ms | 34 trên 13.000 lần nhận 503: máy chủ đang bận và nói rõ như vậy |

Lượt đọc bảng chạy được 2.700 tới 6.000 lần mỗi giây, vì mọi bảng đang mở của cùng một vai giờ dùng chung một lần dựng mỗi 2 giây (mức đặt lúc đo; nay là 0,5 giây). Lỗi trong các lượt đó là của chính bài đo: một máy Mac mở hàng nghìn kết nối mới mỗi giây thì hết cổng cục bộ. Máy chủ không trả lỗi nào.

**scale**, sau khi sửa và sau khi cộng sẵn giờ một lần cùng giữ dòng theo từng người:

| Số máy | Một lần gửi | Lần dựng bảng đầu sau các lần gửi | Các lần dựng sau | Một lần đọc gặp bản đang giữ |
|---|---|---|---|---|
| 20 | 0,63 ms | 1 ms | dưới 1 ms | dưới 0,01 ms |
| 300 | 0,58 ms | 8 ms | 4 ms | dưới 0,01 ms |
| 1.000 | 0,53 ms | 25 ms | 14 ms | dưới 0,01 ms |
| 3.000 | 0,61 ms | 69 ms | 47 ms | dưới 0,01 ms |
| 5.000 | 0,57 ms | 167 ms | 77 ms | dưới 0,01 ms |
| 10.000 | 0,63 ms | 241 ms | 164 ms | dưới 0,01 ms |

Một lần gửi giữ nguyên. Lần dựng đầu sau nhiều lần gửi đếm lại mọi người; các lần sau chỉ đếm những người đã đổi, cộng với những phần của bảng mà người nào cũng có mặt (biểu đồ 24 giờ của từng dòng, các chi nhánh). Ở 10.000 máy, vòng lịch sử 30 giây mất khoảng 31 ms và lần đếm theo ngày 5 phút khoảng 250 ms, phần lớn là ghi các dòng của ngày. Bảng được dựng nhiều nhất một lần mỗi `VIEW_CACHE_SECONDS` cho mỗi vai, dù có bao nhiêu bảng đang mở: 2 giây lúc đo, nay mặc định 0,5, và 5 khi có bộ nhận Go.

## Vượt 10.000 máy

Đo cùng cách (`--scale`), với `MAX_DEVICES` được nâng cho bài đo:

| Số máy | Một lần gửi | Các lần dựng bảng sau | Khởi động (nạp và làm sạch mọi máy) | Bộ nhớ |
|---|---|---|---|---|
| 10.000 | 0,8 ms | 154 ms | 3,4 giây | 1,5 GB |
| 30.000 | 0,7 ms | 596 ms | 11 giây | 4,4 GB |
| 50.000 | 0,7 ms | 1,0 giây | 19 giây | 7,3 GB |
| 100.000 | 0,8 ms | 2,1 giây | 40 giây | 14,6 GB |

Một lần gửi vẫn tốn như cũ. Bộ nhớ thì không: sổ 8 ngày theo giờ của mỗi máy giữ dưới dạng dict Python tốn khoảng 150 KB, nên 100.000 máy cần 14,6 GB và 40 giây để khởi động. Đó là giới hạn của thiết kế lúc ấy, không phải của một lần gửi. Bảng trên là số đo cũ đó: từ đó tới nay sổ giờ của mỗi máy là các dòng riêng trong cơ sở dữ liệu và một lần gửi chỉ mang các giờ đã đổi, và trên Linux máy chủ Python giữ sổ của 100.000 máy khi cả máy dùng 6,4 GB ([Trên Linux, có bộ nhận Go](#trên-linux-có-bộ-nhận-go)). Bảng này chưa được đo lại trên Mac.

Mức trần của một tiến trình máy chủ (`--ceiling`, 8 tiến trình phát tải):

| Đo gì | Câu trả lời mỗi giây | CPU máy chủ |
|---|---|---|
| Chỉ `/health`, tầng HTTP không có gì phía sau | hơn 4.500 | khoảng 65% một nhân |
| Lần gửi 12 KB | 650 tới 810 | khoảng 95% một nhân |
| Lần gửi với 112 client cùng lúc | 3.400 được trả lời, 19.000 nhận 503 | máy chủ vẫn chạy |

Con số `/health` bị chính bài đo kìm lại: máy chủ nói HTTP/1.0, nên mỗi yêu cầu là một kết nối mới, và một máy mở hàng nghìn kết nối mỗi giây thì hết cổng cục bộ. Caddy đứng trước máy chủ trên Linux cũng sẽ gặp đúng điều này: không giữ kết nối mở giữa Caddy và máy chủ thì vài trăm kết nối mới mỗi giây đã làm cạn cổng một lúc.

100.000 máy gửi mỗi 30 giây là khoảng 3.300 lần gửi mỗi giây, và 40 MB mỗi giây với 12 KB mỗi lần. Như vậy là khoảng năm tiến trình như thế này trên máy Mac này, và nhiều hơn trên một máy chủ Linux nhỏ. Vì vậy 100.000 máy khi đó cần, theo thứ tự: lần gửi gọn hơn (chỉ các giờ đã đổi), nhịp gửi do máy chủ đặt, khoá riêng cho từng máy, sổ giờ để trên đĩa và chỉ giữ tổng theo ngày trong bộ nhớ, giữ kết nối mở, và nhiều tiến trình nhận số. Ba việc đầu đã làm, sổ giờ đã là các dòng riêng trong cơ sở dữ liệu, và bộ nhận Go tuỳ chọn giữ kết nối của các máy mở ở phía trước Python; nhiều tiến trình nhận số thì chưa. Đã làm gì và còn gì: [Việc tiếp theo](#việc-tiếp-theo).

## Trên Linux, có bộ nhận Go

Đo ngày 2026-11-23 trên hai máy thuê ở Hetzner chung một mạng riêng: máy chủ (CPX32: 4 vCPU AMD, 8 GB, Ubuntu 26.04, Python 3.14) chạy máy chủ Python và bộ nhận Go ([RECEIVER.vi.md](RECEIVER.vi.md)); tải đến từ máy thứ hai (CPX42: 8 vCPU, 16 GB). Mỗi máy giả giữ một kết nối TLS mở và gửi `v: 2` mỗi 2 giây, hoặc thưa hơn khi bộ nhận dặn; lần gửi nào cũng đổi tiền (mức xấu nhất). Máy chủ Python giữ 100.000 máy, mỗi máy sổ 8 ngày (cơ sở dữ liệu 2,4 GB). Công cụ đo nằm ngoài repo: một bộ tạo tải viết bằng Go và bài đo riêng tốc độ ghi của Python.

| | 40.000 máy, 100 bảng | 100.000 máy, 300 bảng |
|---|---|---|
| Giữ kết nối | 40.000 | khoảng 49.500 (phần còn lại được bảo quay lại: 503) |
| Khoảng cách giữa hai lần gửi bộ nhận dặn | 4 giây | 5 giây |
| Số trực tiếp trên bảng, p99 | 1,5 giây | 1,7 giây |
| `/data`, p95 cả lượt | 0,9 giây (phần lớn các giây 45 tới 240 ms) | 0,6 giây |
| CPU của máy | 56% (bộ nhận 1,2 nhân, Python 0,97) | 67% (bộ nhận 1,7, Python 0,93) |
| Bộ nhớ dùng | 6,0 GB | 6,4 GB |
| Python tụt sau (dòng chờ quá một phút) | có lúc | 35 tới 75 giây, lúc có lúc không |

Riêng tốc độ ghi của Python, 100.000 máy, lô 2.000 dòng theo thứ tự mã máy: 5.100 dòng mỗi giây khi không có bảng nào đọc, 1.650 khi có một bảng đọc `/data` liên tục. Đó là giới hạn còn lại trên máy cỡ này; số trực tiếp không phải chờ nó.

Trước các bản sửa của đợt này, cùng máy đó để bộ nhận hết bộ nhớ ở khoảng 60.000 kết nối (bị nhân giết 13 lần trong mười phút, vì mọi máy kết nối lại sau mỗi lần khởi động), và ở 40.000 máy CPU ở mức 94%, số trực tiếp p99 3,1 giây, `/data` p95 4,2 giây. Đã đổi: bộ nhận giữ dưới một giới hạn bộ nhớ và một trần kết nối, tạo ít rác hơn, và dặn các máy gửi thưa hơn khi đông; bảng tìm chi nhánh của từng người qua một chỉ mục. Sau khi `kill -9` bộ nhận rồi Python ở 40.000 máy, tiền của từng người khớp với bộ tạo tải tới từng micro-đô (đo trước các bản sửa này; đường ghi không đổi từ đó).

Đo lại ngày 25/11/2026 trên cùng loại máy, với lần gửi thật của plugin. Gửi như bản 0.50.13 (`v: 1`, cả sổ 8 ngày mỗi lần) thì bộ nhận hết bộ nhớ trong chưa tới 30 giây ở 40.000 máy, và các máy cùng lúc quay về thì quá sức Python; với giới hạn bộ nhớ cứng của 0.50.14 nó không còn chết nhưng chỉ nhận khoảng 800 lần gửi mỗi giây trong khi các máy cần khoảng 20.000. Với `v: 2` như plugin 0.50.15 gửi (các giờ đã đổi, cả sổ mỗi giờ một lần) và bộ nhận 0.50.16 (từ chối theo bộ nhớ thật sự còn dùng, không theo phần rác Go giữ tới lần dọn): nhận mọi lần gửi trước khi `kill -9`, khoảng 12.850 lần mỗi giây, p99 0,15 tới 0,4 giây; bộ nhận chạy hết sức lại khoảng 2,5 phút sau khi khởi động lại; chỉ còn từ chối trong lúc Python bị dừng; và ngay sau lượt đo, tiền của cả 16.000 người khớp với số các máy giữ, tới từng phần triệu đô la, ở cả Python và bộ nhận.

Cùng lượt đo đó với Caddy 2.6 đứng trước Python trên cùng máy, cài như `server/aiworker.caddy` (TLS, nén, nhật ký, danh sách mạng được vào), các bảng và các lần gửi quay về đi qua nó: lúc không có sự cố thì như khi không có Caddy (nhận mọi lần gửi, khoảng 12.000 lần mỗi giây, số trực tiếp p99 1,3 tới 1,6 giây). Bộ nhớ lên 7,0 tới 7,4 GB trên 7,7 (Caddy 0,2 tới 0,5 GB), và sau khi bộ nhận và Python bị `kill -9`, Python ghi lô chậm khoảng 10 lần vì còn quá ít bộ nhớ để đệm cơ sở dữ liệu: các dòng của bộ nhận chờ tới 10 phút, nên bảng của Python và `/data` chậm chừng ấy, trong khi số trực tiếp vẫn đúng giờ. Không mất đồng nào máy chủ đã trả lời là đã nhận: số người mà máy chủ giữ ít hơn các lần gửi nó đã nhận là 0. Có Caddy cùng máy thì 40.000 máy cần 16 GB.

## Đã sửa gì

- `DeviceCache` trong `server/board/devices.py`: lần gửi mới nhất của mỗi máy, làm sạch một lần, giữ trong bộ nhớ. Bảng trong cơ sở dữ liệu vẫn là bản gốc: bộ nhớ đệm được ghi cùng lúc với bảng, nạp lại khi máy chủ khởi động, và nạp lại khi chương trình khác như `webhook.py --forget-device` đổi file (`PRAGMA data_version`).
- `hours_of` trong `server/board/devices.py`: giờ của mỗi máy được cộng theo ngày địa phương một lần, lúc lưu, rồi dùng lại cho bảng, lịch sử và lần đếm theo ngày thay vì đi qua từng giờ của mọi máy mỗi lần. Ngày địa phương được tính bằng số học, vì múi giờ của máy chủ là độ lệch cố định.
- `_person_row` trong `server/board/devices.py`: dòng của mỗi người trên bảng được giữ cho tới khi một máy của họ gửi hoặc tới một thời điểm làm nó đổi: giờ kế tiếp, nửa đêm địa phương kế tiếp, một máy im, việc của bộ nối hết còn mới, một khung hạn mức làm mới. Một bài test so dòng đang giữ với một lần đếm mới qua đúng các thời điểm đó.
- Một lần gửi chỉ cập nhật lịch sử tua lại của người vừa gửi. Vòng 30 giây vẫn xem mọi người, cho những máy đã im.
- `ViewCache` trong `server/board/views.py`: bảng được dựng nhiều nhất một lần mỗi `VIEW_CACHE_SECONDS` cho mỗi vai (2 giây lúc đo; từ bản 0.50.0 mặc định 0,5, và 5 khi có bộ nhận Go), và mọi bảng của vai đó nhận cùng một chuỗi byte. Một vai không bao giờ nhận bản dựng của vai khác. Bảng đang hiện trên màn hình hỏi mỗi giây, nên thứ nó hiện cũ hơn nhiều nhất chừng đó.
- `Load` và `Handler.shed` trong `server/webhook.py`: quá `BUSY_REQUESTS` (mặc định 32) yêu cầu đang được trả lời cùng lúc, lần gửi hay yêu cầu của người chưa đăng nhập nhận ngay 503 kèm `Retry-After` từ 30 tới 90 giây, rải ngẫu nhiên để cả đám máy không cùng quay lại trong một giây. Plugin không gửi gì trước thời điểm đó. Người đã đăng nhập, thiết bị có khoá riêng và `/health` vẫn được trả lời, và nhật ký ghi mỗi phút một lần số yêu cầu bị từ chối.

## Những gì các con số này chưa cho thấy

- **Máy chủ Linux, với Python một mình.** Bảng chạy trên Linux; một máy chủ cloud nhỏ chậm hơn máy Mac này. Linux mới được đo khi có bộ nhận Go đứng trước ([Trên Linux, có bộ nhận Go](#trên-linux-có-bộ-nhận-go)). Hãy chạy bài đo trên máy chủ của bạn trước khi tin các con số này cho cỡ của bạn.
- **Một địa chỉ cho nhiều máy.** Bài đo cho mỗi máy một địa chỉ riêng. Lần gửi giờ được giới hạn theo từng máy, không theo địa chỉ (`INGEST_BURST`, `INGEST_PER_SECOND`), nên một văn phòng đi ra ngoài qua một địa chỉ công cộng không còn dùng chung một giới hạn; chỉ máy mới là vẫn được đếm theo địa chỉ mỗi ngày.
- **HTTPS và Caddy.** Bài đo nói chuyện thẳng với máy chủ, không qua TLS.
- **Chính bài đo thành nút thắt.** Tải đến từ một tiến trình Python trên cùng máy. Quá vài trăm yêu cầu mỗi giây thì có thể bài đo, chứ không phải máy chủ, là thứ chạm trần.

## Python, Rust hay Go

Máy chủ Python không bị viết lại. Các số đo ở trên cho thấy thời gian đi đâu: làm sạch đi làm sạch lại cùng một dữ liệu, việc mà ngôn ngữ nhanh hơn sẽ làm nhanh hơn nhưng vẫn làm đi làm lại. Sửa ngay trong Python, phần việc của máy chủ cho một lần gửi còn khoảng 0,5 ms. Phần còn lại là tầng HTTP của một tiến trình Python. Rust an toàn bộ nhớ ở chỗ C và C++ không an toàn; Python vốn đã an toàn. Viết lại cũng bỏ mất thứ máy chủ được dựng trên đó: chỉ thư viện chuẩn, cài bằng một lệnh, mã mà ai trong đội IT cũng đọc được.

Dấu hiệu để đổi là nhu cầu kéo dài trên khoảng 500 lần gửi mỗi giây mà thêm tiến trình cũng không đáp ứng được, và kể cả khi đó cũng chỉ viết lại phần nhận số, đối chiếu với bộ dữ liệu thử chung để chứng minh nó làm sạch đúng y như bản Python. Phần đó nay đã có, và là tuỳ chọn: bộ nhận trong `receiver/` ([RECEIVER.vi.md](RECEIVER.vi.md)), viết bằng Go để cài chỉ là một file, đối chiếu với Python bằng bộ mẫu chung trong `tests/contract/ingest-v2/`. Python vẫn là bản gốc và ở một văn phòng vẫn tự nhận mọi lần gửi.

## Việc tiếp theo

1. **Đo trên Linux**: đã đo với bộ nhận Go ([Trên Linux, có bộ nhận Go](#trên-linux-có-bộ-nhận-go)); cả khi đi qua Caddy có TLS (25/11/2026).
2. **Trang bảng theo chi nhánh** cho đội lớn, thay cho trả mọi người trong một câu trả lời: đã làm (`/data?scope=`, [RECEIVER.vi.md](RECEIVER.vi.md#mã-dòng-và-phạm-vi)).
3. **Nâng `MAX_DEVICES`**: đặt được trong `/etc/ai-worker.env`; mặc định giữ 300 cho tới khi Python một mình được đo trên Linux.
4. **Vượt một tiến trình**, cho tổ chức 100.000 máy trở lên: nhiều tiến trình nhận số cấp cho một tiến trình phục vụ người xem. Đã làm và đo tới nay: plugin gửi gọn hơn (chỉ các giờ đã đổi, 0.50.15), máy chủ đặt nhịp gửi, khoá riêng cho từng máy, và một bộ nhận Go đứng trước Python ([Trên Linux, có bộ nhận Go](#trên-linux-có-bộ-nhận-go)).
