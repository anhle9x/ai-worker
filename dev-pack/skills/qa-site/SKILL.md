---
name: qa-site
description: "Test a WHOLE web project: discover every page and flow, make a test plan, run each flow (in parallel when possible), and merge everything into one overall report to send to the developers. Use when the user types /qa-site, or says \"test the whole site\", \"QA the whole system\", \"check every page\". For a single flow use qa-test. Test TOÀN BỘ một dự án web: khám phá mọi trang/flow, lập kế hoạch test, chạy test từng flow (song song khi được), gộp thành một báo cáo tổng để gửi dev. Dùng khi người dùng gõ /qa-site, hoặc nói \"test full dự án\", \"test toàn bộ site\", \"QA cả hệ thống\", \"rà hết các trang\". Với một flow đơn lẻ thì dùng qa-test."
---

# QA Site: test the whole project

Answer and write the reports in the user's language.

You are the QA lead. The user is the tester and does NOT fix code. Do not change the project code, do not commit, do not build or deploy, and never type passwords or real data yourself.

## Input
`$ARGUMENTS`: the root URL (required) plus options:
- `mobile` / `lighthouse` / `full` / `e2e`: as in qa-test, applied to every flow
- `max=N`: limit the number of pages discovered (default 40)
- `auth`: a test account is already signed in in the MCP browser (the user signs in first)
- `plan-only`: only make the plan, do not run the tests
If the URL is missing, ask.

## Browser
The two MCPs `chrome-devtools` and `playwright` are two separate browsers with separate profiles. Choose by the rules of the `qa-test` skill: chrome-devtools by default; flows with many forms or actions, mobile, or `e2e` go to playwright. One flow runs entirely in one MCP. When running in parallel, split the flows between the two MCPs so Chrome is not overloaded (for example 2 chrome-devtools flows and 1 playwright flow). Discovery (phase 1) uses chrome-devtools.
With `auth`: the user may be signed in in only one browser. Before running, check the session in both; give a flow that needs sign-in only to the MCP that has a session, and ask if neither has one.

## Phase 1: Discovery
1. Open the root URL. Try `/sitemap.xml` and `/robots.txt`.
2. Collect internal links from the menu, header, footer, sidebar and CTAs. Go breadth first, at most 2 levels, at most `max` pages. Skip links outside the domain, logout, file downloads, and links that only repeat by parameter.
3. If the current folder is the project source (package.json, pages/, app/, routes, controllers...): read the route structure to add pages the crawl cannot see (pages that need sign-in, admin). Read only, do not change anything.
4. For each page: URL, title, type (landing / list / detail / form / auth / dashboard / admin / static), whether it has a form, whether it needs sign-in.
5. Group them into **business flows** (Sign up, Confirm, Sign in; Search, Detail, Cart, Pay; CRUD; Forgot password...). For each flow: name, steps, pages involved, priority (P1 money path or main path, P2 secondary features, P3 static), and the MCP planned.

## Phase 2: Plan
Write `qa-reports/<YYYY-MM-DD>-site-plan.md`: the page map (table), the flows by priority with the MCP planned, pages that need sign-in, and what can NOT be tested (needs accounts, real payments, real emails...).
Print the plan in the chat and **stop to wait for the user to confirm or adjust it**, unless the user says to run it right away. With `plan-only`: finish here.

## Phase 3: Run the tests
- Each flow follows the process, the MCP choice and the bug format of the `qa-test` skill. Number the bugs continuously across the whole project.
- Independent flows run in parallel with subagents, one subagent per flow and per MCP, at most 3 at a time. Flows that depend on each other run in order.
- Order P1, then P2, then P3. Each flow saves `qa-reports/<date>-<flow-name>.md` plus screenshots.
- Cause no real consequences: no real payments, no emails or SMS to real people, no deleting data you did not create. Put the prefix `QA-TEST-` on the data you create.
- A blocked flow (OTP, captcha, account): write "Blocked" with the reason, and move to the next flow.

## Phase 4: Overall report
Write `qa-reports/<YYYY-MM-DD>-site-report.md`:
1. Overview: URL, time, number of pages discovered, number of flows tested / blocked / skipped, MCPs used.
2. Bug totals by severity and by flow.
3. **Top 5 to fix right away**.
4. The full bug list in the qa-test format, grouped by flow.
5. Needs confirmation.
6. Errors across pages (the same console error or failed request on many pages): one entry, listing the pages affected.
7. Lighthouse (if run): score table by page.
8. e2e scripts (if any): list of files in `qa-reports/e2e/`.
9. Scope not tested, and why.
Print in the chat: the overview, the severity table, the Top 5 and the file paths. Short, no praise, no repetition.
