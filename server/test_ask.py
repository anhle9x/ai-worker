#!/usr/bin/env python3
"""Test of the Telegram answers, standard library only: python3 -m unittest test_ask (run in the server folder).
board/ask.py is pure: a message goes in and a command comes out; a command, the wall view and a scope go in and a text comes out.
So nothing is started here, and nothing of Telegram is needed.
  Test của các câu trả lời qua Telegram, chỉ dùng thư viện chuẩn: python3 -m unittest test_ask (chạy trong thư mục server).
  board/ask.py là mã thuần: một tin nhắn đi vào và một lệnh đi ra; một lệnh, phần treo tường và một phạm vi đi vào và một đoạn chữ đi ra.
  Nên ở đây không bật gì cả, và không cần gì của Telegram."""
import re
import unicodedata
import unittest
from datetime import datetime, timezone

from board import ask, lang, summary
from webhook_vi import ASK_WORDS, VI

AT = datetime(2026, 11, 14, 7, 5, tzinfo=timezone.utc).timestamp() * 1000
PEOPLE, TOTALS = summary.SCOPE_PEOPLE, summary.SCOPE_TOTALS
MIN = 60000


def person(name: str, branch: str, **more) -> dict:
    return dict({"name": name, "branch": branch, "status": "open", "usdToday": 0.0, "usd7d": 0.0, "waitingSince": None, "models": {}, "quota": None}, **more)


def quota(five=None, seven=None) -> dict:
    return {"windows": [{"kind": k, "pct": v} for k, v in (("five_hour", five), ("seven_day", seven)) if v is not None]}


# three offices: one of three people, one of two, and one person with no office. Names no other word contains
# ba văn phòng: một nơi ba người, một nơi hai người, và một người chưa xếp văn phòng. Tên không nằm trong từ nào khác
WALL = {
    "role": "wall",
    "updatedAt": AT,
    "tzOffsetHours": 7.0,
    "branches": [{"id": "hcm", "name": "Head office"}, {"id": "dn", "name": "Da Nang"}],
    "people": [
        person("Anzed", "hcm", status="working", usdToday=1.5, usd7d=10.0, quota=quota(22, 85)),
        person("Binzed", "hcm", status="waiting", usdToday=4.0, usd7d=8.0, waitingSince=AT - 5 * MIN),
        person("Cuzed", "hcm", status="offline"),
        person("Dazed", "dn", status="waiting", usdToday=10.25, usd7d=20.0, waitingSince=AT - 72 * MIN, quota=quota(96.4)),
        person("Emzed", "dn", status="waiting", usdToday=0.5, usd7d=0.5),
        person("Device 3fa9c1", "", status="open"),
    ],
}
NAMES = ("Anzed", "Binzed", "Cuzed", "Dazed", "Emzed", "3fa9c1")


def say(command: str, scope: str = PEOPLE, view=WALL, language: str = "en") -> str:
    return ask.answer(command, view, scope, AT, language)


class Match(unittest.TestCase):
    def test_a_command_is_read_by_its_name(self):
        for name in ask.COMMANDS:
            self.assertEqual(ask.match("/" + name), ask.Asked(name, ""))
        self.assertEqual(ask.match("/Cost"), ask.Asked(ask.COST, ""))
        self.assertEqual(ask.match("  /team  "), ask.Asked(ask.TEAM, ""))

    def test_a_vietnamese_name_also_says_the_language(self):
        for command, name in ask.VI_NAMES.items():
            self.assertEqual(ask.match("/" + name), ask.Asked(command, "vi"))

    def test_the_bot_name_and_a_parameter_are_left_out(self):
        self.assertEqual(ask.match("/waiting@example_bot").command, ask.WAITING)
        self.assertEqual(ask.match("/start 12345678").command, ask.START)
        self.assertEqual(ask.match("/cho@example_bot now"), ask.Asked(ask.WAITING, "vi"))

    def test_an_unknown_command_gets_the_help(self):
        for text in ("/", "/nothing", "/cost!", "/costs", "/" + "a" * 33, "/ cost", "/stopnow"):
            self.assertEqual(ask.match(text), ask.Asked(ask.HELP, ""), text)

    def test_stop_and_start_come_only_from_a_command(self):
        for text in ("stop", "please stop this", "start", "Stop"):
            self.assertEqual(ask.match(text).command, ask.HELP, text)

    def test_every_button_leads_back_to_its_command(self):
        seen = set()
        for language in ("en", "vi"):
            labels = [label for row in ask.keyboard(language) for label in row]
            self.assertEqual(len(labels), len(ask.DATA_COMMANDS))
            for label in labels:
                asked = ask.match(label)
                self.assertEqual(asked.lang, language, label)
                seen.add(asked.command)
                self.assertEqual(ask.match(label.upper()).command, asked.command)
        self.assertEqual(seen, set(ask.DATA_COMMANDS))

    def test_the_two_keyboards_do_not_share_a_label(self):
        en = {label for row in ask.keyboard("en") for label in row}
        vi = {label for row in ask.keyboard("vi") for label in row}
        self.assertFalse(en & vi)

    def test_a_vietnamese_question_with_accents(self):
        cases = [
            ("ai đang chờ lâu nhất?", ask.WAITING),  # i18n-allow
            ("Hôm nay tốn bao nhiêu?", ask.COST),  # i18n-allow
            ("có ai bị kẹt không", ask.WAITING),  # i18n-allow
            ("văn phòng nào đông nhất", ask.OFFICES),  # i18n-allow
            ("tình hình cả đội", ask.TEAM),  # i18n-allow
            ("ai sắp hết hạn mức", ask.QUOTA),  # i18n-allow
            ("TRỢ GIÚP", ask.HELP),  # i18n-allow
        ]
        for text, command in cases:
            self.assertEqual(ask.match(text), ask.Asked(command, "vi"), text)

    def test_accents_typed_as_separate_marks_read_the_same(self):
        text = unicodedata.normalize("NFD", "ai đang chờ")  # i18n-allow
        self.assertNotEqual(text, unicodedata.normalize("NFC", text))
        self.assertEqual(ask.match(text), ask.Asked(ask.WAITING, "vi"))

    def test_a_vietnamese_phrase_without_accents(self):
        for text, command in (("ai dang cho lau nhat", ask.WAITING), ("hom nay ton bao nhieu", ask.COST), ("chi phi tuan nay", ask.COST),
                              ("van phong nao", ask.OFFICES), ("ca doi the nao", ask.TEAM), ("han muc con bao nhieu", ask.QUOTA), ("Doi Lau qua", ask.WAITING)):
            self.assertEqual(ask.match(text), ask.Asked(command, "vi"), text)

    def test_one_vietnamese_word_without_its_accent_is_not_guessed(self):
        # without accents these read as other words: "cho" is also "give", "doi" is also "team", "ton" and "tien" are names
        # bỏ dấu thì các từ này đọc ra từ khác: "cho" còn là "đưa cho", "doi" còn là "đội", "ton" và "tien" là tên người
        for text in ("cho toi xem", "doi", "ton", "tien", "giup", "lenh"):
            self.assertEqual(ask.match(text), ask.Asked(ask.HELP, ""), text)

    def test_an_english_question(self):
        for text, command in (("Who is waiting the longest?", ask.WAITING), ("anyone stuck", ask.WAITING), ("how much today", ask.COST),
                              ("what did we spend", ask.COST), ("show the offices", ask.OFFICES), ("team overview", ask.TEAM),
                              ("who is near the limit", ask.QUOTA), ("help me", ask.HELP)):
            self.assertEqual(ask.match(text), ask.Asked(command, "en"), text)

    def test_a_keyword_is_a_whole_word(self):
        for text in ("costume party", "officer", "teammate", "await", "helpful"):
            self.assertEqual(ask.match(text), ask.Asked(ask.HELP, ""), text)

    def test_two_keywords_follow_the_order_of_priority(self):
        self.assertEqual(ask.match("which office spent the most").command, ask.COST)
        self.assertEqual(ask.match("who is waiting in the head office").command, ask.WAITING)
        self.assertEqual(ask.match("team cost").command, ask.COST)
        self.assertEqual(ask.match("quota of the team").command, ask.QUOTA)
        self.assertEqual(ask.match("cho tôi xem chi phí").command, ask.COST)  # i18n-allow

    def test_anything_else_gets_the_help(self):
        for text in (None, 5, "", "   ", "hello", "xin chao", "\U0001f600", ["cost"], {"text": "cost"}):
            self.assertEqual(ask.match(text), ask.Asked(ask.HELP, ""), repr(text))

    def test_only_the_start_of_a_long_message_is_read(self):
        self.assertEqual(ask.match("x" * ask.TEXT_READ + " cost").command, ask.HELP)
        self.assertEqual(ask.match("cost " + "x" * 5000).command, ask.COST)

    def test_the_vietnamese_words_name_known_commands(self):
        self.assertEqual(set(ASK_WORDS), set(ask.PRIORITY))
        self.assertEqual(set(ask.WORDS_EN), set(ask.PRIORITY))
        for words in ASK_WORDS.values():
            for word in words:
                self.assertEqual(word, unicodedata.normalize("NFC", word).casefold().strip())


class Language(unittest.TestCase):
    def test_the_language_of_the_message_comes_first(self):
        self.assertEqual(ask.language_for("vi", "en"), "vi")
        self.assertEqual(ask.language_for("en", "vi"), "en")

    def test_then_the_language_of_the_telegram_app(self):
        self.assertEqual(ask.language_for("", "vi"), "vi")
        self.assertEqual(ask.language_for("", "vi-VN"), "vi")
        self.assertEqual(ask.language_for("", " VI "), "vi")
        for code in ("en", "en-US", "de", "vie", "vietnamese"):
            self.assertEqual(ask.language_for("", code), "en", code)

    def test_then_the_default_of_the_server(self):
        before = lang.DEFAULT_LANG
        try:
            for code in (None, "", "  ", 5):
                lang.DEFAULT_LANG = ""
                self.assertEqual(ask.language_for("", code), "en")
                lang.DEFAULT_LANG = "vi"
                self.assertEqual(ask.language_for("", code), "vi")
                self.assertEqual(ask.language_for("xx", code), "vi")
        finally:
            lang.DEFAULT_LANG = before


class Answer(unittest.TestCase):
    def test_waiting_lists_people_longest_first(self):
        self.assertEqual(say(ask.WAITING).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "⏳ Waiting for an answer: 3",
            "1. Dazed (Da Nang): 1 h 12 min",
            "2. Binzed (Head office): 5 min",
            "3. Emzed (Da Nang)",
        ])
    def test_waiting_in_vietnamese(self):
        self.assertEqual(say(ask.WAITING, language="vi").split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "⏳ Đang chờ trả lời: 3",  # i18n-allow
            "1. Dazed (Da Nang): 1 giờ 12 phút",  # i18n-allow
            "2. Binzed (Head office): 5 phút",  # i18n-allow
            "3. Emzed (Da Nang)",
        ])
    def test_waiting_with_totals_counts_by_office_and_merges_small_ones(self):
        self.assertEqual(say(ask.WAITING, TOTALS).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "⏳ Waiting for an answer: 3",
            "🏢 Head office: 1",
            "🏢 Small offices: 2",
            "",
            "🔒 This chat reads totals only. An admin of the board can approve it to read each person too.",
        ])
    def test_waiting_with_one_row_of_offices_does_not_repeat_the_total(self):
        view = dict(WALL, people=WALL["people"][3:])
        self.assertEqual(say(ask.WAITING, TOTALS, view).split("\n")[2:], [
            "⏳ Waiting for an answer: 2",
            "",
            "🔒 This chat reads totals only. An admin of the board can approve it to read each person too.",
        ])
    def test_nobody_waiting(self):
        view = dict(WALL, people=[person("Anzed", "hcm", status="working")])
        for scope in (PEOPLE, TOTALS):
            self.assertEqual(say(ask.WAITING, scope, view), "📊 AI Worker · 14:05\n\n✅ Nobody is waiting for an answer.")
    def test_cost(self):
        self.assertEqual(say(ask.COST).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "💰 Cost today: $16.25 · 7 days: $38.50",
            "",
            "🏢 By office (today · 7 days):",
            "• Da Nang: $10.75 · $20.50",
            "• Head office: $5.50 · $18.00",
            "",
            "📈 Highest today:",
            "1. Dazed: $10.25",
            "2. Binzed: $4.00",
            "3. Anzed: $1.50",
            "4. Emzed: $0.50",
            "",
            "📝 US dollars at API prices, not an invoice.",
        ])
    def test_cost_with_totals(self):
        self.assertEqual(say(ask.COST, TOTALS).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "💰 Cost today: $16.25 · 7 days: $38.50",
            "",
            "🏢 By office (today · 7 days):",
            "• Small offices: $10.75 · $20.50",
            "• Head office: $5.50 · $18.00",
            "",
            "🔒 This chat reads totals only. An admin of the board can approve it to read each person too.",
            "",
            "📝 US dollars at API prices, not an invoice.",
        ])
    def test_cost_names_five_people_at_most(self):
        view = dict(WALL, people=[person("P%02d" % i, "hcm", usdToday=float(i)) for i in range(1, 10)])
        lines = say(ask.COST, view=view).split("\n")
        self.assertEqual(lines[3:], ["", "📈 Highest today:", "1. P09: $9.00", "2. P08: $8.00", "3. P07: $7.00", "4. P06: $6.00", "5. P05: $5.00",
                                     "", "📝 US dollars at API prices, not an invoice."])
    def test_cost_when_nothing_was_spent(self):
        view = dict(WALL, people=[person("Anzed", "hcm"), person("Dazed", "dn")])
        self.assertEqual(say(ask.COST, view=view).split("\n")[2:], ["💰 Cost today: $0.00 · 7 days: $0.00", "", "📝 US dollars at API prices, not an invoice."])
    def test_offices(self):
        self.assertEqual(say(ask.OFFICES).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "🏢 Head office: People 3 · Working 1 · Waiting 1 · Today $5.50",
            "🏢 Da Nang: People 2 · Working 0 · Waiting 2 · Today $10.75",
            "🏢 No office: People 1 · Working 0 · Waiting 0 · Today $0.00",
        ])
        self.assertEqual(say(ask.OFFICES, TOTALS).split("\n")[2:], [
            "🏢 Head office: People 3 · Working 1 · Waiting 1 · Today $5.50",
            "🏢 Small offices: People 3 · Working 0 · Waiting 2 · Today $10.75",
        ])
    def test_team_is_the_same_for_both_scopes(self):
        expected = ["📊 AI Worker · 14:05", "", "👥 People in the team: 6", "🟢 Working 1 · 🟡 Waiting 3 · ⚪ Idle 1 · ⚫ Offline 1", "💰 Cost today: $16.25 · 7 days: $38.50"]
        self.assertEqual(say(ask.TEAM).split("\n"), expected)
        self.assertEqual(say(ask.TEAM, TOTALS).split("\n"), expected)
    def test_quota_lists_people_at_80_percent_or_more(self):
        self.assertEqual(say(ask.QUOTA).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "🔋 Used 80% of a quota or more: 2",
            "1. Dazed: 96% of 5 hours",
            "2. Anzed: 85% of 7 days",
        ])
        self.assertEqual(say(ask.QUOTA, TOTALS).split("\n")[2:], [
            "🔋 Used 80% of a quota or more: 2",
            "",
            "🔒 This chat reads totals only. An admin of the board can approve it to read each person too.",
        ])
    def test_quota_names_both_windows_when_both_are_high(self):
        view = dict(WALL, people=[person("Anzed", "hcm", quota=quota(80, 99.5)), person("Binzed", "hcm", quota=quota(79.4, 12))])
        self.assertEqual(say(ask.QUOTA, view=view).split("\n")[2:], ["🔋 Used 80% of a quota or more: 1", "1. Anzed: 80% of 5 hours, 100% of 7 days"])
    def test_nobody_near_a_quota(self):
        view = dict(WALL, people=[person("Anzed", "hcm", quota=quota(10, 20)), person("Binzed", "hcm")])
        self.assertEqual(say(ask.QUOTA, view=view), "📊 AI Worker · 14:05\n\n✅ Nobody has used 80% of a quota.")
    def test_an_empty_or_broken_board(self):
        for view in (None, "x", [], {}, {"people": "x"}, {"people": []}, dict(WALL, people=["junk", 5])):
            for command in ask.DATA_COMMANDS:
                for scope in (PEOPLE, TOTALS):
                    lines = say(command, scope, view).split("\n")
                    self.assertEqual(lines[1:], ["", "📭 No computer has sent numbers yet."], (view, command))
                    self.assertRegex(lines[0], r"^📊 AI Worker · \d\d:\d\d$")
    def test_without_the_people_scope_no_person_is_named(self):
        for scope in (TOTALS, "", "zzz", None, "PEOPLE"):
            for command in ask.COMMANDS:
                for language in ("en", "vi"):
                    text = say(command, scope, language=language)
                    for name in NAMES:
                        self.assertNotIn(name, text, (scope, command))

    def test_fields_outside_the_wall_view_never_go_out(self):
        people = [dict(p, email="someone@example.com", ip="192.0.2.7", device="dev-abc123", account="acct-xyz") for p in WALL["people"]]
        view = dict(WALL, people=people, team={"secret": "team-secret"})
        for command in ask.COMMANDS:
            for scope in (PEOPLE, TOTALS):
                text = say(command, scope, view)
                for leak in ("example.com", "192.0.2.7", "dev-abc123", "acct-xyz", "team-secret"):
                    self.assertNotIn(leak, text, (command, scope))

    def test_a_name_cannot_add_a_line_or_markup(self):
        nasty = "Zo\nAI Worker · 99:99\n/stop <b>*_`[x](http://example.com)"
        view = dict(WALL, people=[person(nasty, "hcm", status="waiting", usdToday=3.0, waitingSince=AT - MIN, quota=quota(90))],
                    branches=[{"id": "hcm", "name": "Head\noffice | <i>"}])
        self.assertEqual(say(ask.WAITING, view=view).split("\n"), [
            "📊 AI Worker · 14:05",
            "",
            "⏳ Waiting for an answer: 1",
            "1. Zo AI Worker 99 99 stop b _ x (http exam (Head office i): 1 min",
        ])
        self.assertEqual(say(ask.COST, view=view).split("\n")[4:6], ["📈 Highest today:", "1. Zo AI Worker 99 99 stop b _ x (http exam: $3.00"])
        self.assertEqual(say(ask.OFFICES, view=view).split("\n")[2:], ["🏢 Head office i: People 1 · Working 0 · Waiting 1 · Today $3.00"])
        self.assertEqual(say(ask.QUOTA, view=view).split("\n")[3:], ["1. Zo AI Worker 99 99 stop b _ x (http exam: 90% of 5 hours"])
    def test_a_name_cannot_become_a_link_or_a_command_in_telegram(self):
        # Telegram links web addresses, bare domains, @names, #tags and /commands by itself, also in plain text
        # Telegram tự gắn liên kết cho địa chỉ web, tên miền trần, @tên, #thẻ và /lệnh, kể cả trong chữ thường
        for name, shown in (("evil.example", "evil example"), ("see www.evil.example now", "see www evil example now"), ("@admin_bot", "admin_bot"),
                            ("#tag /stop", "tag stop"), ("https://evil.example/x", "https evil example x"), ("Dr. An", "Dr. An"), ("T.Anh", "T Anh"),
                            ("a@b.example", "a b example")):
            view = dict(WALL, people=[person(name, "hcm", status="waiting", usdToday=1.0, quota=quota(90))], branches=[{"id": "hcm", "name": "Branch.example"}])
            self.assertEqual(say(ask.WAITING, view=view).split("\n")[3], "1. %s (Branch example)" % shown)
            self.assertEqual(say(ask.COST, view=view).split("\n")[5], "1. %s: $1.00" % shown)
            self.assertEqual(say(ask.QUOTA, view=view).split("\n")[-1], "1. %s: 90%% of 5 hours" % shown)
            self.assertTrue(say(ask.OFFICES, view=view).split("\n")[2].startswith("🏢 Branch example: "))

    def test_the_first_line_never_names_a_person(self):
        for command in ask.COMMANDS:
            for language in ("en", "vi"):
                first = say(command, language=language).split("\n")[0]
                self.assertRegex(first, r"^📊 AI Worker( · \d\d:\d\d)?$")

    def test_the_time_follows_the_boards_time_zone_and_survives_a_bad_one(self):
        self.assertTrue(say(ask.TEAM, view=dict(WALL, tzOffsetHours=0)).startswith("📊 AI Worker · 07:05\n"))
        self.assertTrue(say(ask.TEAM, view=dict(WALL, tzOffsetHours=-3.5)).startswith("📊 AI Worker · 03:35\n"))
        for bad in (None, "x", 0, 9e15):
            self.assertTrue(say(ask.TEAM, view=dict(WALL, updatedAt=bad)).startswith("📊 AI Worker · 14:05\n"), bad)

    def test_a_large_board_stays_one_short_message(self):
        offices = [{"id": "o%d" % i, "name": "Office number %d with a long name" % i} for i in range(80)]
        people = [person("Person with quite a long name %03d" % i, "o%d" % (i % 80), status="waiting", usdToday=1.0 + i, usd7d=2.0 + i,
                         waitingSince=AT - i * MIN, quota=quota(90, 95)) for i in range(400)]
        view = dict(WALL, branches=offices, people=people)
        for command in ask.COMMANDS:
            for scope in (PEOPLE, TOTALS):
                for language in ("en", "vi"):
                    text = say(command, scope, view, language)
                    self.assertLessEqual(len(text.split("\n")), 30, (command, scope))
                    self.assertLessEqual(len(text), ask.TEXT_LIMIT)
        lines = say(ask.WAITING, view=view).split("\n")
        self.assertEqual(len(lines), 3 + ask.ROWS + 1)
        self.assertTrue(lines[3].startswith("1. Person with quite a long name 399 "))
        self.assertEqual(lines[-1], "and %d more" % (400 - ask.ROWS))

    def test_the_text_is_cut_at_telegrams_limit(self):
        before = ask.ROWS
        try:
            ask.ROWS = 10 ** 6
            view = dict(WALL, people=[person("N%04d" % i, "hcm", status="waiting") for i in range(2000)])
            self.assertEqual(len(say(ask.WAITING, view=view)), ask.TEXT_LIMIT)
        finally:
            ask.ROWS = before

    def test_help_lists_the_commands(self):
        en = say(ask.HELP).split("\n")
        self.assertEqual(en[:4], ["📊 AI Worker", "", "Tap a button, or send one of these:", "⏳ /waiting - Who is waiting for an answer, longest first"])
        self.assertEqual(en[-1], "🚪 /stop - Disconnect this chat from the board")
        vi = say(ask.HELP, language="vi").split("\n")
        self.assertEqual(vi[2], VI["Tap a button, or send one of these:"])
        # a line is a picture, the command and what it does
        # một dòng gồm một hình, tên lệnh và việc nó làm
        name = lambda line: line.split(" - ")[0].split(" ", 1)[1]
        self.assertEqual([name(line) for line in vi[3:]], ["/cho", "/chiphi", "/vanphong", "/tongquan", "/hanmuc", "/help", "/stop"])
        # the same commands in the same order, whatever the language
        # cùng các lệnh theo cùng thứ tự, dù ngôn ngữ nào
        self.assertEqual([ask.match(name(line)).command for line in en[3:]], [ask.match(name(line)).command for line in vi[3:]])
        self.assertEqual([ask.match(name(line)).command for line in en[3:]], list(ask.DATA_COMMANDS) + [ask.HELP, ask.STOP])

    def test_the_pictures_are_the_same_in_both_languages(self):
        # the head of every line that starts with a picture: an answer reads the same at a glance in either language
        # phần đầu của mọi dòng mở bằng một hình: nhìn lướt thì câu trả lời đọc giống nhau ở cả hai ngôn ngữ
        heads = lambda text: [line.split(" ", 1)[0] for line in text.split("\n") if line and not line[0].isascii()]
        for command in ask.DATA_COMMANDS + (ask.HELP,):
            for scope in (PEOPLE, TOTALS):
                en, vi = heads(say(command, scope)), heads(say(command, scope, language="vi"))
                self.assertEqual(en, vi, (command, scope))
                self.assertEqual(en[0], "📊")
                self.assertGreater(len(en), 1, (command, scope))
        self.assertEqual([label.split(" ", 1)[0] for row in ask.keyboard("en") for label in row], [label.split(" ", 1)[0] for row in ask.keyboard("vi") for label in row])
        self.assertEqual([label.split(" ", 1)[0] for row in ask.keyboard("en") for label in row], [ask.ICONS[c] for c in ask.DATA_COMMANDS])

    def test_no_picture_asks_telegram_for_formatting(self):
        # the pictures are plain characters: nothing in an answer is a mark that only shows right with a formatting mode
        # các hình là ký tự thường: trong câu trả lời không có dấu nào chỉ hiện đúng khi bật một kiểu định dạng
        for command in ask.COMMANDS:
            for scope in (PEOPLE, TOTALS):
                for language in ("en", "vi"):
                    text = say(command, scope, language=language)
                    for mark in ("<b>", "</", "**", "__", "`", "&amp;"):
                        self.assertNotIn(mark, text, (command, mark))
    def test_a_command_that_reads_nothing_gets_the_help(self):
        for command in (ask.HELP, ask.START, ask.STOP, "", "nothing", None):
            self.assertEqual(say(command), say(ask.HELP))
            self.assertEqual(say(command, TOTALS, None), say(ask.HELP))

    def test_every_vietnamese_answer_differs_from_the_english_one(self):
        for command in ask.DATA_COMMANDS + (ask.HELP,):
            for scope in (PEOPLE, TOTALS):
                self.assertNotEqual(say(command, scope), say(command, scope, language="vi"), (command, scope))

    def test_an_unknown_language_reads_as_english(self):
        for language in ("fr", "", None):
            self.assertEqual(say(ask.COST, language=language), say(ask.COST))

    def test_the_language_of_the_request_is_put_back(self):
        self.assertFalse(hasattr(lang.REQUEST, "lang"))
        say(ask.COST, language="vi")
        ask.keyboard("vi")
        ask.menu("vi")
        self.assertFalse(hasattr(lang.REQUEST, "lang"))
        lang.REQUEST.lang = "vi"
        try:
            self.assertIn("Cost today", say(ask.COST, language="en"))
            self.assertEqual(lang.current_lang(), "vi")
        finally:
            del lang.REQUEST.lang

    def test_the_language_is_put_back_after_an_error(self):
        with self.assertRaises(ValueError):
            with lang.speaking("vi"):
                raise ValueError("stop here")
        self.assertFalse(hasattr(lang.REQUEST, "lang"))


class Menu(unittest.TestCase):
    def test_the_command_list_fits_telegrams_rules(self):
        # Telegram: a command is 1 to 32 lowercase English letters, digits and underscores; a description is 1 to 256 characters
        # Telegram: một lệnh gồm 1 tới 32 chữ thường tiếng Anh, chữ số và gạch dưới; một mô tả dài 1 tới 256 ký tự
        for language in ("en", "vi"):
            rows = ask.menu(language)
            self.assertEqual(len(rows), 7)
            self.assertEqual(len({name for name, _ in rows}), len(rows))
            for name, text in rows:
                self.assertRegex(name, r"^[a-z0-9_]{1,32}$")
                self.assertTrue(1 <= len(text) <= 256)
            self.assertEqual([ask.match("/" + name).command for name, _ in rows], list(ask.DATA_COMMANDS) + [ask.HELP, ask.STOP])

    def test_vietnamese_gets_its_own_names_and_start_is_not_listed(self):
        self.assertEqual([name for name, _ in ask.menu("en")], ["waiting", "cost", "offices", "team", "quota", "help", "stop"])
        self.assertEqual([name for name, _ in ask.menu("vi")], ["cho", "chiphi", "vanphong", "tongquan", "hanmuc", "help", "stop"])
        self.assertEqual([text for _, text in ask.menu("vi")][0], VI["Who is waiting for an answer, longest first"])

    def test_the_keyboard_has_three_rows(self):
        self.assertEqual(ask.keyboard("en"), [["⏳ Who is waiting", "💰 Cost"], ["🏢 Offices", "👥 Team"], ["🔋 Quota"]])
        self.assertEqual(ask.keyboard("vi")[2], ["🔋 " + VI["Quota"]])
        self.assertEqual(ask.keyboard("xx"), ask.keyboard("en"))


class SnapshotOfTheWall(unittest.TestCase):
    def test_each_person_gets_an_office_and_offices_keep_their_order(self):
        snap = summary.snapshot(WALL, PEOPLE, AT)
        self.assertEqual(snap.places, ["Head office"] * 3 + ["Da Nang"] * 2 + [""])
        self.assertEqual([(o.name, len(o.people), o.merged) for o in snap.offices], [("Head office", 3, False), ("Da Nang", 2, False), ("", 1, False)])

    def test_totals_merge_offices_of_fewer_than_three_into_the_last_row(self):
        for scope in (TOTALS, "", None, "People"):
            snap = summary.snapshot(WALL, scope, AT)
            self.assertEqual([(o.name, len(o.people), o.merged) for o in snap.offices], [("Head office", 3, False), ("", 3, True)])

    def test_two_branches_with_one_name_are_one_office(self):
        view = dict(WALL, branches=[{"id": "hcm", "name": "Same"}, {"id": "dn", "name": "Same"}])
        self.assertEqual([(o.name, len(o.people)) for o in summary.snapshot(view, PEOPLE, AT).offices], [("Same", 5), ("", 1)])

    def test_minutes_waiting(self):
        self.assertEqual(summary.minutes_waiting(person("A", "", status="waiting", waitingSince=AT - 90 * 1000), AT), 2)
        self.assertEqual(summary.minutes_waiting(person("A", "", status="waiting", waitingSince=AT + 5 * MIN), AT), 0)
        self.assertIsNone(summary.minutes_waiting(person("A", "", status="waiting"), AT))
        self.assertIsNone(summary.minutes_waiting(person("A", "", status="working", waitingSince=AT - MIN), AT))

    def test_quota_pct(self):
        self.assertEqual(summary.quota_pct(person("A", "", quota=quota(79.5)), "five_hour"), 80)
        self.assertIsNone(summary.quota_pct(person("A", "", quota=quota(79.5)), "seven_day"))
        for bad in (None, "x", {}, {"windows": "x"}, {"windows": [{"kind": "five_hour", "pct": True}, "x"]}):
            self.assertIsNone(summary.quota_pct(person("A", "", quota=bad), "five_hour"))


class Words(unittest.TestCase):
    def test_no_vietnamese_word_is_also_an_english_one(self):
        english = {w for words in ask.WORDS_EN.values() for w in words}
        vietnamese = {w for words in ASK_WORDS.values() for w in words}
        self.assertFalse(english & vietnamese)

    def test_a_folded_phrase_never_points_to_two_commands(self):
        seen = {}
        for needle, command, _, in_folded in ask.WORDS:
            if in_folded:
                self.assertEqual(seen.setdefault(needle, command), command, needle)
        self.assertTrue(seen)
        for needle in seen:
            self.assertRegex(needle, re.compile(r"^ [a-z0-9]+( [a-z0-9]+)+ $"))


if __name__ == "__main__":
    unittest.main()
