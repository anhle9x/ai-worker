#!/usr/bin/env python3
"""Test of the Telegram bot process, standard library only: python3 -m unittest test_telegram_bot (run in the server folder).
Telegram is played by FakeTelegram and the webhook by FakeBoard, two small HTTP servers on this machine: nothing here reaches
the Internet, and no real token is used. The bot process against the real webhook is tried in test_webhook.py (TelegramAsk).
  Test của tiến trình bot Telegram, chỉ dùng thư viện chuẩn: python3 -m unittest test_telegram_bot (chạy trong thư mục server).
  FakeTelegram đóng vai Telegram và FakeBoard đóng vai webhook, hai máy chủ HTTP nhỏ trên máy này: ở đây không có gì ra
  Internet, và không dùng khoá thật nào. Tiến trình bot chạy với webhook thật được thử ở test_webhook.py (TelegramAsk)."""
import json
import os
import re
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telegram_bot

TOKEN = "123456789:" + "A" * 35
KEY = "k" * 40
HOA = 700100200


class Recording(ThreadingHTTPServer):
    """A local HTTP server that keeps what it was sent and answers through its owner.
    Một máy chủ HTTP trên máy này, giữ lại những gì nó nhận và trả lời qua chủ của nó."""
    daemon_threads = True

    def __init__(self, owner):
        self.owner = owner
        super().__init__(("127.0.0.1", 0), Recorder)


class Recorder(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        status, answer = self.server.owner.answer(self.path, body, dict(self.headers.items()))
        data = json.dumps(answer).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


class Served:
    def __init__(self):
        self.lock = threading.Lock()
        self.server = Recording(self)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        # a short poll, so closing the server at the end of a test does not wait half a second
        # vòng chờ ngắn, để việc đóng máy chủ cuối mỗi bài test không phải chờ nửa giây
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeTelegram(Served):
    """Telegram's Bot API, as far as the bot process uses it: getMe, getUpdates with its offset, sendMessage, setMyCommands, leaveChat.
    It never holds a call open: with no message waiting, getUpdates answers an empty list at once.
    Bot API của Telegram, trong phạm vi tiến trình bot dùng: getMe, getUpdates cùng offset của nó, sendMessage, setMyCommands, leaveChat.
    Nó không bao giờ giữ lời gọi lại: không có tin chờ thì getUpdates trả ngay một danh sách rỗng."""

    def __init__(self, token: str = TOKEN, bot_name: str = "example_ask_bot"):
        self.token, self.bot_name = token, bot_name
        self.queue, self.next_id = [], 1000
        # how long getUpdates may wait for a message, as the real one does; 0 answers at once
        # getUpdates được chờ tin bao lâu, như bản thật; 0 thì trả lời ngay
        self.hold, self.arrived = 0.0, threading.Event()
        # every call as (method, body); and for a method, answers to give in place of the usual one, used once each
        # mọi lời gọi dạng (hàm, thân); và với một hàm, các câu trả lời đưa thay cho câu thường lệ, mỗi câu dùng một lần
        self.calls, self.scripted = [], {}
        super().__init__()

    def say(self, text, who: int = HOA, chat: str = "private", chat_id=None, age: float = 0, username: str = "hoa_ql", lang: str = "en", **more) -> int:
        """A person sends the bot a message. Returns the update's id.
        Một người gửi tin cho bot. Trả mã của tin đó."""
        with self.lock:
            self.next_id += 1
            message = {"message_id": self.next_id, "date": int(time.time() - age), "chat": {"id": who if chat_id is None else chat_id, "type": chat},
                       "from": {"id": who, "is_bot": False, "first_name": "Hoa", "username": username, "language_code": lang}}
            if text is not None:
                message["text"] = text
            message.update(more)
            self.queue.append({"update_id": self.next_id, "message": message})
            self.arrived.set()
            return self.next_id

    def script(self, method: str, status: int, body: dict) -> None:
        with self.lock:
            self.scripted.setdefault(method, []).append((status, body))

    def sent(self) -> list:
        return [body for method, body in self.calls if method == "sendMessage"]

    def answer(self, path: str, body, headers: dict):
        prefix = "/bot%s/" % self.token
        if not path.startswith(prefix):
            return 404 if path.startswith("/bot") else 400, {"ok": False, "error_code": 404, "description": "Not Found"}
        method = path[len(prefix):]
        if method == "getUpdates" and self.hold and not self.queue:
            self.arrived.clear()
            self.arrived.wait(self.hold)
        with self.lock:
            self.calls.append((method, body))
            if self.scripted.get(method):
                return self.scripted[method].pop(0)
            if method == "getMe":
                return 200, {"ok": True, "result": {"id": 123456789, "is_bot": True, "first_name": "Ask", "username": self.bot_name}}
            if method == "getUpdates":
                offset = (body or {}).get("offset")
                if isinstance(offset, int):
                    self.queue = [u for u in self.queue if u["update_id"] >= offset]
                return 200, {"ok": True, "result": list(self.queue)}
            if method == "sendMessage":
                return 200, {"ok": True, "result": {"message_id": 1, "chat": {"id": (body or {}).get("chat_id")}}}
            if method in ("setMyCommands", "leaveChat", "setChatMenuButton"):
                return 200, {"ok": True, "result": True}
        return 404, {"ok": False, "error_code": 404, "description": "Not Found"}


class FakeBoard(Served):
    """The webhook's /bot/telegram, as the bot process sees it. reply(message) decides what a message is answered with.
    Đường /bot/telegram của webhook, như tiến trình bot nhìn thấy. reply(message) quyết định một tin nhắn được trả lời bằng gì."""

    COMMANDS = {"en": [["waiting", "Who is waiting"], ["cost", "Cost today"]], "vi": [["cho", "Ai dang cho"], ["chiphi", "Chi phi"]]}

    def __init__(self, key: str = KEY):
        self.key = key
        self.calls, self.headers = [], []
        self.status = 200
        self.reply = lambda message: {"text": "You said: %s" % message.get("text")}
        # what the next round's question about menu buttons is answered with, once
        # câu trả lời cho câu hỏi về nút menu của vòng kế tiếp, dùng một lần
        self.menus = []
        super().__init__()

    def messages(self) -> list:
        return [c for c in self.calls if "report" not in c and "tick" not in c]

    def reports(self) -> list:
        return [(c["report"], c["bot"]) for c in self.calls if "report" in c]

    def answer(self, path: str, body, headers: dict):
        with self.lock:
            self.headers.append(headers)
            if path != "/bot/telegram":
                return 404, {"error": "Not found"}
            if headers.get("Authorization") != "Bearer " + self.key:
                return 401, {"error": "wrong bot key"}
            if self.status != 200:
                return self.status, {"error": "scripted"}
            self.calls.append(body)
            if isinstance(body, dict) and "report" in body:
                return 200, {"ok": True, "commands": self.COMMANDS}
            if isinstance(body, dict) and body.get("tick") is True:
                menus, self.menus = self.menus, []
                return 200, {"ok": True, "menus": menus, "menuText": "AI Worker"}
            return 200, self.reply(body)


class Clock:
    """Time the tests move by hand; sleeping moves it and is written down.
    Thời gian do bài test tự vặn; ngủ thì đẩy nó đi và được ghi lại."""

    def __init__(self):
        self.now, self.slept = time.time(), []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class BotCase(unittest.TestCase):
    def setUp(self):
        self.telegram, self.board, self.clock, self.lines = FakeTelegram(), FakeBoard(), Clock(), []
        self.addCleanup(self.telegram.close)
        self.addCleanup(self.board.close)
        self.bot = self.make()

    def make(self, token: str = TOKEN, key: str = KEY, api=None, board=None):
        return telegram_bot.Bot(token, board or self.board.url, key, api or self.telegram.url, sleep=self.clock.sleep, clock=self.clock, log=self.lines.append, poll_seconds=0)


class Reading(BotCase):
    def test_the_first_round_names_the_bot_reports_and_sets_the_commands(self):
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual(self.bot.bot_name, "example_ask_bot")
        self.assertEqual(self.board.reports(), [("ok", "example_ask_bot")])
        commands = [body for method, body in self.telegram.calls if method == "setMyCommands"]
        self.assertEqual(commands, [
            {"commands": [{"command": "waiting", "description": "Who is waiting"}, {"command": "cost", "description": "Cost today"}]},
            {"commands": [{"command": "cho", "description": "Ai dang cho"}, {"command": "chiphi", "description": "Chi phi"}], "language_code": "vi"},
        ])
        self.assertTrue(self.bot.commands_set)
        self.assertIn("telegram bot: reading messages as @example_ask_bot", self.lines)
        # the commands are set once, not at every round
        # danh sách lệnh chỉ đặt một lần, không đặt lại ở mỗi vòng
        self.bot.step()
        self.assertEqual(len([m for m, _ in self.telegram.calls if m == "setMyCommands"]), 2)
        self.assertEqual(len([m for m, _ in self.telegram.calls if m == "getMe"]), 1)

    def test_it_says_it_is_reading_before_the_first_long_wait_for_messages(self):
        order = []
        real = self.bot.telegram

        def watched(method, payload, timeout=20):
            if method == "getUpdates":
                order.append((list(self.board.reports()), list(self.lines), self.bot.commands_set))
            return real(method, payload, timeout)
        self.bot.telegram = watched
        self.bot.step()
        reports, lines, commands_set = order[0]
        self.assertEqual(reports, [("ok", "example_ask_bot")])
        self.assertIn("telegram bot: reading messages as @example_ask_bot", lines)
        self.assertTrue(commands_set)

    def test_it_asks_for_messages_only_and_waits_at_telegram(self):
        bot = telegram_bot.Bot(TOKEN, self.board.url, KEY, self.telegram.url, sleep=self.clock.sleep, clock=self.clock, log=self.lines.append, poll_seconds=0)
        bot.step()
        ask = [body for method, body in self.telegram.calls if method == "getUpdates"][0]
        self.assertEqual(ask, {"timeout": 0, "allowed_updates": ["message"]})
        self.assertEqual(telegram_bot.POLL_SECONDS, 50)

    def test_an_empty_answer_that_came_at_once_does_not_become_a_loop_without_pause(self):
        bot = telegram_bot.Bot(TOKEN, self.board.url, KEY, self.telegram.url, sleep=self.clock.sleep, clock=self.clock, log=self.lines.append, poll_seconds=50)
        self.assertEqual(bot.step(), 1)
        self.telegram.say("hi")
        self.assertEqual(bot.step(), 0)
        # when Telegram held the call as it should, the next one follows at once
        # khi Telegram đã giữ lời gọi như lẽ thường, lời gọi kế tiếp đi ngay
        real = bot.telegram

        def held(method, payload, timeout=20):
            if method == "getUpdates":
                self.clock.now += 50
            return real(method, payload, timeout)
        bot.telegram = held
        self.assertEqual(bot.step(), 0)

    def test_a_message_goes_to_the_board_and_the_answer_goes_back(self):
        self.telegram.say("how much today?")
        self.bot.step()
        self.assertEqual(self.board.messages(), [{"from": HOA, "chat": "private", "username": "hoa_ql", "lang": "en", "text": "how much today?"}])
        self.assertEqual(self.telegram.sent(), [{"chat_id": HOA, "text": "You said: how much today?", "protect_content": True, "link_preview_options": {"is_disabled": True}}])

    def test_the_board_is_called_with_the_key_and_looks_like_a_direct_call(self):
        self.telegram.say("hi")
        self.bot.step()
        for headers in self.board.headers:
            self.assertEqual(headers["Authorization"], "Bearer " + KEY)
            self.assertEqual(headers["Content-Type"], "application/json")
            for name in ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Real-IP", "Forwarded", "Via", "Origin", "Cookie"):
                self.assertNotIn(name, headers)

    def test_the_board_is_never_called_through_a_proxy(self):
        before = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY")}
        try:
            for k in before:
                os.environ.pop(k, None)
            os.environ["http_proxy"] = os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
            bot = self.make()
            self.assertEqual(bot.board({"report": "ok", "bot": "x"})[0], 200)
        finally:
            for k, v in before.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_buttons_and_their_removal(self):
        self.board.reply = lambda message: {"text": "Pick one", "keyboard": [["Who is waiting", "Cost"], ["Quota"]]}
        self.telegram.say("hi")
        self.bot.step()
        self.assertEqual(self.telegram.sent()[-1]["reply_markup"], {"keyboard": [[{"text": "Who is waiting"}, {"text": "Cost"}], [{"text": "Quota"}]], "resize_keyboard": True, "is_persistent": True})
        self.board.reply = lambda message: {"text": "Bye", "removeKeyboard": True}
        self.telegram.say("/stop")
        self.bot.step()
        self.assertEqual(self.telegram.sent()[-1]["reply_markup"], {"remove_keyboard": True})
        # a keyboard that is not rows of labels is left out, the text still goes
        # bàn phím không phải các hàng chữ thì bị bỏ, chữ vẫn được gửi
        for bad in ("x", [], [[]], [["ok"], "x"], [[5]], [[""]], {"a": 1}):
            self.board.reply = lambda message, bad=bad: {"text": "Plain", "keyboard": bad}
            self.telegram.say("hi")
            self.bot.step()
            self.assertEqual(self.telegram.sent()[-1], {"chat_id": HOA, "text": "Plain", "protect_content": True, "link_preview_options": {"is_disabled": True}}, bad)

    def test_an_empty_answer_sends_nothing(self):
        for answer in ({"text": ""}, {}, {"text": None}, {"text": 5}, {"keyboard": [["x"]]}):
            self.board.reply = lambda message, answer=answer: answer
            self.telegram.say("hi")
            self.bot.step()
        self.assertEqual(self.telegram.sent(), [])
        self.assertEqual(len(self.board.messages()), 5)

    def test_a_long_answer_is_cut_at_telegrams_limit(self):
        self.board.reply = lambda message: {"text": "x" * 5000}
        self.telegram.say("hi")
        self.bot.step()
        self.assertEqual(len(self.telegram.sent()[0]["text"]), 4096)

    def test_a_group_is_left_when_the_board_says_so(self):
        self.board.reply = lambda message: {"text": "", "leave": True}
        self.telegram.say("/cost", chat="supergroup", chat_id=-100500)
        self.bot.step()
        self.assertEqual(self.board.messages()[0]["chat"], "supergroup")
        self.assertEqual([body for method, body in self.telegram.calls if method == "leaveChat"], [{"chat_id": -100500}])
        self.assertEqual(self.telegram.sent(), [])
        # a private chat cannot be left, whatever the answer says
        # chat riêng thì không rời được, dù câu trả lời nói gì
        self.telegram.say("/cost")
        self.bot.step()
        self.assertEqual(len([m for m, _ in self.telegram.calls if m == "leaveChat"]), 1)

    def test_each_message_is_handled_once(self):
        first = self.telegram.say("one")
        self.bot.step()
        self.assertEqual(self.bot.offset, first + 1)
        second = self.telegram.say("two")
        self.bot.step()
        self.bot.step()
        self.assertEqual([m["text"] for m in self.board.messages()], ["one", "two"])
        asks = [body.get("offset") for method, body in self.telegram.calls if method == "getUpdates"]
        self.assertEqual(asks, [None, first + 1, second + 1])

    def test_several_messages_in_one_round_keep_their_order(self):
        for text in ("a", "b", "c"):
            self.telegram.say(text)
        self.bot.step()
        self.assertEqual([m["text"] for m in self.board.messages()], ["a", "b", "c"])
        self.assertEqual([m["text"] for m in self.telegram.sent()], ["You said: a", "You said: b", "You said: c"])

    def test_what_is_not_text_is_still_handed_over_with_no_text(self):
        self.telegram.say(None, photo=[{"file_id": "x"}])
        self.bot.step()
        self.assertEqual(self.board.messages(), [{"from": HOA, "chat": "private", "username": "hoa_ql", "lang": "en", "text": None}])

    def test_only_what_the_board_needs_is_passed_on(self):
        self.telegram.say("hi", contact={"phone_number": "+15550100"}, location={"latitude": 1, "longitude": 2})
        self.bot.step()
        self.assertEqual(set(self.board.messages()[0]), {"from", "chat", "username", "lang", "text"})
        self.assertNotIn("+15550100", json.dumps(self.board.calls))
        self.assertNotIn("Hoa", json.dumps(self.board.calls))


class LeftOut(BotCase):
    def test_an_old_message_is_not_answered(self):
        self.telegram.say("yesterday's question", age=telegram_bot.STALE_SECONDS + 5)
        self.telegram.say("fresh", age=telegram_bot.STALE_SECONDS - 30)
        self.bot.step()
        self.assertEqual([m["text"] for m in self.board.messages()], ["fresh"])
        self.assertTrue(any("too old" in line for line in self.lines))
        # it is confirmed all the same, so it does not come back
        # nó vẫn được xác nhận, nên không quay lại
        self.bot.step()
        self.assertEqual(len(self.board.messages()), 1)

    def test_a_message_from_a_bot_or_without_a_sender_is_dropped(self):
        self.telegram.say("from a bot")
        self.telegram.queue[-1]["message"]["from"]["is_bot"] = True
        self.telegram.say("no sender")
        del self.telegram.queue[-1]["message"]["from"]
        self.telegram.say("no chat")
        del self.telegram.queue[-1]["message"]["chat"]
        self.telegram.say("chat id is text", chat_id="@somewhere")
        self.telegram.say("no date")
        del self.telegram.queue[-1]["message"]["date"]
        self.bot.step()
        self.assertEqual(self.board.messages(), [])
        self.assertEqual(self.telegram.sent(), [])

    def test_updates_that_are_not_messages_do_not_stop_the_round(self):
        with self.telegram.lock:
            self.telegram.queue += ["junk", {"update_id": "x"}, {"update_id": True, "message": {}}, {"update_id": 5000}, {"update_id": 5001, "message": "x"},
                                    {"update_id": 5002, "edited_message": {"text": "edited"}}]
        last = self.telegram.say("real")
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual([m["text"] for m in self.board.messages()], ["real"])
        self.assertEqual(self.bot.offset, last + 1)


class Trouble(BotCase):
    def test_a_refused_token_is_reported_and_waited_on(self):
        for status in (401, 404):
            telegram, board, bot = FakeTelegram(), FakeBoard(), None
            self.addCleanup(telegram.close)
            self.addCleanup(board.close)
            telegram.script("getMe", status, {"ok": False, "error_code": status, "description": "Unauthorized"})
            bot = self.make(api=telegram.url, board=board.url)
            self.assertEqual(bot.step(), 60)
            self.assertEqual(board.reports(), [("unauthorized", "")])
            self.assertEqual([m for m, _ in telegram.calls], ["getMe"])
        self.assertTrue(any("Telegram refuses the token" in line for line in self.lines))

    def test_a_token_refused_later_is_reported_too(self):
        self.bot.step()
        self.telegram.script("getUpdates", 401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        self.assertEqual(self.bot.step(), 60)
        self.assertEqual(self.board.reports(), [("ok", "example_ask_bot"), ("unauthorized", "example_ask_bot")])
        # and it reads again once Telegram takes the token
        # và nó đọc lại khi Telegram nhận khoá
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual(self.board.reports()[-1], ("ok", "example_ask_bot"))

    def test_another_reader_of_the_same_bot_is_reported(self):
        self.telegram.script("getUpdates", 409, {"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"})
        self.assertEqual(self.bot.step(), 30)
        # the token was taken first, so it said it was reading; the last word is what counts
        # khoá được nhận trước, nên nó đã báo là đang đọc; lời báo sau cùng mới là điều có giá trị
        self.assertEqual(self.board.reports(), [("ok", "example_ask_bot"), ("conflict", "example_ask_bot")])
        self.assertTrue(any("one bot, one reader" in line for line in self.lines))

    def test_telegram_saying_slow_down_is_obeyed(self):
        self.telegram.script("getUpdates", 429, {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 7}})
        self.assertEqual(self.bot.step(), 7)
        self.telegram.script("getUpdates", 429, {"ok": False, "parameters": {"retry_after": 9999}})
        self.assertEqual(self.bot.step(), 60)
        self.telegram.script("getUpdates", 429, {"ok": False})
        self.assertEqual(self.bot.step(), 5)
        # being told to slow down is not a state of its own: the bot still counts as reading
        # bị bảo chậm lại không phải một trạng thái riêng: bot vẫn được tính là đang đọc
        self.assertEqual(self.board.reports(), [("ok", "example_ask_bot")])

    def test_telegram_out_of_reach_is_reported_after_three_tries_and_waited_on_longer_each_time(self):
        closed = FakeTelegram()
        url = closed.url
        closed.close()
        bot = self.make(api=url)
        self.assertEqual([bot.step() for _ in range(4)], [5, 10, 15, 20])
        self.assertEqual(self.board.reports(), [("unreachable", "")])
        bot.failures = 50
        self.assertEqual(bot.step(), 60)

    def test_a_broken_answer_from_telegram_counts_as_out_of_reach(self):
        self.bot.step()
        for body in ({"ok": True, "result": "x"}, {"ok": False, "result": []}, {"result": []}, {}):
            self.telegram.script("getUpdates", 200, body)
        self.assertEqual([self.bot.step() for _ in range(4)], [5, 10, 15, 20])
        self.assertEqual(self.board.reports()[-1], ("unreachable", "example_ask_bot"))
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual(self.bot.failures, 0)

    def test_an_answer_telegram_refuses_once_for_speed_is_sent_again(self):
        self.telegram.say("hi")
        self.telegram.script("sendMessage", 429, {"ok": False, "parameters": {"retry_after": 3}})
        self.bot.step()
        self.assertEqual(self.clock.slept, [3])
        self.assertEqual(len(self.telegram.sent()), 2)
        self.assertEqual(self.telegram.sent()[0], self.telegram.sent()[1])

    def test_an_answer_that_cannot_be_sent_is_logged_and_the_round_goes_on(self):
        self.telegram.say("blocked the bot")
        self.telegram.say("still here", who=HOA + 1)
        self.telegram.script("sendMessage", 403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual(len(self.telegram.sent()), 2)
        self.assertIn("telegram bot: an answer could not be sent (status 403)", self.lines)

    def test_the_board_not_answering_is_tried_three_times_and_the_message_dropped(self):
        self.bot.step()
        gone = FakeBoard()
        url = gone.url
        gone.close()
        bot = self.make(board=url)
        bot.bot_name, bot.state, bot.reported_at, bot.commands_set = "example_ask_bot", "ok", self.clock.now, True
        self.telegram.say("hi")
        self.assertEqual(bot.step(), 0)
        self.assertEqual(self.clock.slept, [1, 1])
        self.assertEqual(self.telegram.sent(), [])
        self.assertIn("telegram bot: the board did not answer on this machine", self.lines)

    def test_an_error_inside_the_board_drops_the_message_only(self):
        self.bot.step()
        self.board.status = 500
        self.telegram.say("hi")
        self.assertEqual(self.bot.step(), 0)
        self.assertEqual(self.telegram.sent(), [])
        self.board.status = 200
        self.telegram.say("again")
        self.bot.step()
        self.assertEqual([m["text"] for m in self.telegram.sent()], ["You said: again"])

    def test_a_board_that_does_not_take_this_process_stops_it(self):
        for change in ({"key": "other-" + "k" * 40}, {"status": 404}, {"status": 401}):
            board = FakeBoard()
            self.addCleanup(board.close)
            bot = self.make(board=board.url, key=change.get("key", KEY))
            board.status = change.get("status", 200)
            with self.assertRaises(telegram_bot.Refused) as caught:
                bot.run()
            self.assertIn("TELEGRAM_ASK", str(caught.exception))
            self.assertNotIn(KEY, str(caught.exception))

    def test_run_waits_for_the_board_then_keeps_going_after_a_bad_round(self):
        rounds = []

        def step():
            rounds.append(len(rounds))
            if len(rounds) == 1:
                raise RuntimeError("boom " + TOKEN)
            if len(rounds) == 2:
                return 30
            raise telegram_bot.Refused("stop the test")
        self.bot.step = step
        self.board.status = 503
        waited = []

        def sleep(seconds):
            waited.append(seconds)
            self.board.status = 200
        self.bot.sleep = sleep
        with self.assertRaises(telegram_bot.Refused):
            self.bot.run()
        self.assertEqual(waited, [5, 5, 30])
        self.assertEqual(len(rounds), 3)
        self.assertIn("telegram bot: a round failed (RuntimeError)", self.lines)

    def test_the_bot_says_it_is_alive_every_few_minutes(self):
        self.bot.step()
        self.bot.step()
        self.assertEqual(len(self.board.reports()), 1)
        self.clock.now += telegram_bot.HEARTBEAT_SECONDS - 1
        self.bot.step()
        self.assertEqual(len(self.board.reports()), 1)
        self.clock.now += 2
        self.bot.step()
        self.assertEqual(self.board.reports(), [("ok", "example_ask_bot")] * 2)

    def test_commands_that_could_not_be_set_are_tried_again_later(self):
        self.telegram.script("setMyCommands", 500, {"ok": False})
        self.bot.step()
        self.assertFalse(self.bot.commands_set)
        self.clock.now += telegram_bot.HEARTBEAT_SECONDS + 1
        self.bot.step()
        self.assertTrue(self.bot.commands_set)

    def test_a_command_list_that_is_not_one_is_not_sent(self):
        for commands in (None, "x", {}, {"vi": [["cho", "x"]]}, {"en": "x"}):
            self.assertFalse(self.bot.set_commands(commands), commands)
        self.assertEqual([m for m, _ in self.telegram.calls if m == "setMyCommands"], [])
        self.assertTrue(self.bot.set_commands({"en": [["cost", "Cost"], ["Bad Name", "x"], ["ok", ""], "junk", ["long", "d" * 300]], "EN-us": [["x", "y"]], "vi": "junk"}))
        sent = [body for method, body in self.telegram.calls if method == "setMyCommands"]
        self.assertEqual(sent, [{"commands": [{"command": "cost", "description": "Cost"}, {"command": "long", "description": "d" * 256}]}])


class Secrets(BotCase):
    def test_the_token_and_the_key_never_reach_the_log(self):
        closed = FakeTelegram()
        url = closed.url
        closed.close()
        bot = self.make(api=url)
        for _ in range(4):
            bot.step()
        self.telegram.script("getUpdates", 401, {"ok": False, "description": "Unauthorized for bot" + TOKEN})
        self.bot.step()
        self.telegram.say("hi")
        self.telegram.script("sendMessage", 400, {"ok": False, "description": TOKEN})
        self.bot.step()
        self.bot.log("something went wrong with " + TOKEN)
        text = "\n".join(self.lines)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(KEY, text)
        self.assertIn("***", text)
        self.assertTrue(all(line.startswith("telegram bot: ") for line in self.lines))

    def test_what_people_wrote_never_reaches_the_log(self):
        self.board.reply = lambda message: {"text": "ANSWERTEXT for SECRETNAME"}
        self.telegram.say("QUESTIONTEXT", username="secret_user")
        self.telegram.say("old QUESTIONTEXT", age=500, username="secret_user")
        self.telegram.script("sendMessage", 403, {"ok": False, "description": "Forbidden"})
        self.bot.step()
        text = "\n".join(self.lines)
        for private in ("QUESTIONTEXT", "ANSWERTEXT", "SECRETNAME", "secret_user", str(HOA)):
            self.assertNotIn(private, text)

    def test_the_process_keeps_nothing_on_disk_and_imports_nothing_of_the_board(self):
        with open(telegram_bot.__file__, encoding="utf-8") as f:
            src = f.read()
        code = src.split('"""', 2)[2]
        for word in ("import board", "from board", "sqlite3", "INGEST_KEY", "OTP", "tempfile", "os.makedirs", ".write_text", "pickle", "shelve"):
            self.assertFalse(word in code, word)
        # no file is opened: the only "open" is that of a network address
        # không mở file nào: "open" duy nhất là mở một địa chỉ mạng
        self.assertEqual(re.findall(r"(?<![.\w])open\(", code), [])


class Settings(unittest.TestCase):
    GOOD = {"TELEGRAM_ASK_TOKEN": TOKEN, "TELEGRAM_ASK_KEY": KEY}

    def test_the_defaults(self):
        self.assertEqual(telegram_bot.settings_from(self.GOOD), (TOKEN, "http://127.0.0.1:8788", KEY, "https://api.telegram.org"))
        self.assertEqual(telegram_bot.settings_from(dict(self.GOOD, PORT="9595"))[1], "http://127.0.0.1:9595")
        self.assertEqual(telegram_bot.settings_from(dict(self.GOOD, PORT=""))[1], "http://127.0.0.1:8788")
        self.assertEqual(telegram_bot.settings_from(dict(self.GOOD, BOARD_URL="http://localhost:8788", TELEGRAM_API_URL="http://127.0.0.1:8081"))[1:], ("http://localhost:8788", KEY, "http://127.0.0.1:8081"))
        self.assertEqual(telegram_bot.settings_from({k: "  %s  " % v for k, v in self.GOOD.items()})[0], TOKEN)

    def test_a_token_that_is_not_one_is_refused(self):
        for token in ("", "abc", "123456789", "123456789:short", ":" + "A" * 35, "123456789:" + "A" * 34 + " x", "bot" + TOKEN):
            with self.assertRaises(ValueError) as caught:
                telegram_bot.settings_from(dict(self.GOOD, TELEGRAM_ASK_TOKEN=token))
            self.assertIn("TELEGRAM_ASK_TOKEN", str(caught.exception))
            if token:
                self.assertNotIn(token, str(caught.exception))

    def test_a_short_key_is_refused(self):
        for key in ("", "k" * 31):
            with self.assertRaises(ValueError) as caught:
                telegram_bot.settings_from(dict(self.GOOD, TELEGRAM_ASK_KEY=key))
            self.assertIn("TELEGRAM_ASK_KEY", str(caught.exception))

    def test_the_board_must_be_on_this_machine(self):
        for board in ("http://board.example.com", "https://127.0.0.1:8788", "http://192.168.1.5:8788", "http://127.0.0.1.example.com:8788", "ftp://127.0.0.1", "127.0.0.1:8788", "http://[::1"):
            with self.assertRaises(ValueError) as caught:
                telegram_bot.settings_from(dict(self.GOOD, BOARD_URL=board))
            self.assertIn("BOARD_URL", str(caught.exception), board)
        self.assertEqual(telegram_bot.settings_from(dict(self.GOOD, BOARD_URL="http://[::1]:8788"))[1], "http://[::1]:8788")

    def test_the_token_goes_out_only_over_https(self):
        for api in ("http://api.telegram.org", "http://example.com", "ftp://api.telegram.org", "api.telegram.org", "https://"):
            with self.assertRaises(ValueError) as caught:
                telegram_bot.settings_from(dict(self.GOOD, TELEGRAM_API_URL=api))
            self.assertIn("TELEGRAM_API_URL", str(caught.exception), api)
        self.assertEqual(telegram_bot.settings_from(dict(self.GOOD, TELEGRAM_API_URL="https://bot-api.example.com"))[3], "https://bot-api.example.com")

    def test_the_address_called_holds_the_token_the_way_telegram_wants_it(self):
        bot = telegram_bot.Bot(TOKEN, "http://127.0.0.1:1", KEY, "https://api.telegram.org/")
        self.assertEqual(bot.api_base, "https://api.telegram.org/bot%s/" % TOKEN)
        self.assertEqual(bot.board_endpoint, "http://127.0.0.1:1/bot/telegram")


class MenuButtons(BotCase):
    """The board's window inside Telegram: once in a while the bot process asks the webhook which chats' menu buttons to change.
    Khung bảng bên trong Telegram: thỉnh thoảng tiến trình bot hỏi webhook cần đổi nút menu của chat nào."""

    def buttons(self):
        return [body for method, body in self.telegram.calls if method == "setChatMenuButton"]

    def test_a_chat_gets_the_window_or_the_plain_menu(self):
        self.board.menus = [{"to": 700100200, "url": "https://board.example.com/tg/app"}, {"to": 700100201, "url": None}]
        self.bot.step()
        self.assertEqual(self.buttons(), [
            {"chat_id": 700100200, "menu_button": {"type": "web_app", "text": "AI Worker", "web_app": {"url": "https://board.example.com/tg/app"}}},
            {"chat_id": 700100201, "menu_button": {"type": "default"}},
        ])

    def test_only_an_https_address_opens_a_window(self):
        self.board.menus = [{"to": 1, "url": "http://board.example.com/tg/app"}, {"to": 2, "url": "javascript:alert(1)"}, {"to": True, "url": None}, {"to": -5, "url": None}, "x"]
        self.bot.step()
        self.assertEqual(self.buttons(), [{"chat_id": 1, "menu_button": {"type": "default"}}, {"chat_id": 2, "menu_button": {"type": "default"}}])

    def test_the_webhook_is_asked_at_most_every_twenty_seconds(self):
        ticks = lambda: [c for c in self.board.calls if isinstance(c, dict) and c.get("tick") is True]
        self.bot.step()
        self.bot.step()
        self.assertEqual(len(ticks()), 1)
        self.clock.now += telegram_bot.MENU_SECONDS
        self.bot.step()
        self.assertEqual(len(ticks()), 2)

    def test_not_asked_while_the_webhook_does_not_answer(self):
        self.bot.step()
        self.board.status = 500
        self.bot.board_down = True
        self.clock.now += telegram_bot.MENU_SECONDS
        self.bot.sync_menus()
        self.assertEqual(len([c for c in self.board.calls if isinstance(c, dict) and c.get("tick") is True]), 1)


if __name__ == "__main__":
    unittest.main()
