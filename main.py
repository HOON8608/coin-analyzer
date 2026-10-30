
import tkinter as tk
from tkinter import ttk
import urllib.request
import urllib.parse
import json
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "https://api.upbit.com/v1"
REFRESH_SECONDS = 300
MAX_COINS = 30

def api(path):
    url = API + path
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "CoinAnalyzer/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    changes = [values[i] - values[i-1]
               for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0

    return 100 - 100 / (1 + avg_gain / avg_loss)

def ema(values, period):
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * k + result[-1] * (1-k))
    return result

def analyze(ticker):
    market = ticker["market"]

    four = api(
        f"/candles/minutes/240?market={market}&count=80"
    )
    daily = api(
        f"/candles/days?market={market}&count=80"
    )

    four.reverse()
    daily.reverse()

    closes = [x["trade_price"] for x in four]
    days = [x["trade_price"] for x in daily]

    r4 = rsi(closes)
    rd = rsi(days)

    fast = ema(closes, 12)
    slow = ema(closes, 26)
    macd = [a-b for a, b in zip(fast, slow)]
    signal = ema(macd, 9)

    golden = macd[-2] <= signal[-2] and macd[-1] > signal[-1]
    improving = macd[-1] > macd[-2]

    volumes = [x["candle_acc_trade_volume"] for x in four]
    average = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / average if average else 0

    high = max(x["high_price"] for x in four[-42:])
    price = ticker["trade_price"]
    drawdown = (price / high - 1) * 100 if high else 0

    score = 0
    reasons = []

    if r4 <= 35:
        score += 2
        reasons.append("4시간 RSI 과매도")

    if rd <= 45:
        score += 1
        reasons.append("일봉 RSI 낮음")

    if golden:
        score += 2
        reasons.append("MACD 골든크로스")
    elif improving:
        score += 1
        reasons.append("MACD 개선")

    if volume_ratio >= 1.5:
        score += 1
        reasons.append("거래량 증가")

    if drawdown <= -8:
        score += 1
        reasons.append("고점 대비 조정")

    change = ticker["signed_change_rate"] * 100

    if change <= -12:
        status = "위험"
    elif score >= 5 and r4 <= 40:
        status = "매수 관심"
    elif score >= 3:
        status = "관찰"
    else:
        status = "대기"

    return {
        "market": market,
        "price": price,
        "change": change,
        "r4": r4,
        "rd": rd,
        "score": score,
        "volume": volume_ratio,
        "drawdown": drawdown,
        "status": status,
        "reasons": reasons
    }

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("코인 분석실 | Upbit Altcoin Analyzer")
        self.root.geometry("1050x680")
        self.root.minsize(800, 500)

        self.results = []
        self.busy = False
        self.filter = tk.StringVar(value="전체")

        header = ttk.Frame(root, padding=12)
        header.pack(fill="x")

        ttk.Label(
            header, text="📊 코인 분석실",
            font=("Malgun Gothic", 20, "bold")
        ).pack(side="left")

        self.status = tk.StringVar(value="시작 준비")
        ttk.Label(header, textvariable=self.status).pack(side="right")

        controls = ttk.Frame(root, padding=10)
        controls.pack(fill="x")

        ttk.Label(controls, text="분석 결과").pack(side="left")

        combo = ttk.Combobox(
            controls, textvariable=self.filter,
            values=["전체", "매수 관심", "관찰", "대기", "위험"],
            state="readonly", width=12
        )
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda e: self.render())

        self.scan_button = ttk.Button(
            controls, text="지금 분석하기",
            command=self.start_scan
        )
        self.scan_button.pack(side="right")

        columns = (
            "coin", "price", "change", "r4",
            "rd", "score", "volume", "status"
        )

        self.table = ttk.Treeview(
            root, columns=columns, show="headings"
        )

        labels = {
            "coin": "코인",
            "price": "현재가(KRW)",
            "change": "24시간 변동",
            "r4": "4시간 RSI",
            "rd": "일봉 RSI",
            "score": "점수",
            "volume": "거래량 배수",
            "status": "분석 결과"
        }

        for key, label in labels.items():
            self.table.heading(key, text=label)
            self.table.column(key, width=120, anchor="center")

        self.table.pack(
            fill="both", expand=True, padx=12, pady=8
        )
        self.table.bind("<<TreeviewSelect>>", self.show_detail)

        self.detail = tk.Text(root, height=7, wrap="word")
        self.detail.pack(fill="x", padx=12, pady=8)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=5)

        ttk.Label(
            root,
            text="공개 시세 기반 참고 분석 | 자동매매 기능 없음",
            foreground="gray"
        ).pack(pady=5)

        self.root.after(1000, self.start_scan)
        self.root.after(REFRESH_SECONDS * 1000, self.auto_refresh)

    def start_scan(self):
        if self.busy:
            return

        self.busy = True
        self.scan_button.configure(state="disabled")
        self.status.set("업비트 시세 수집 중...")

        threading.Thread(
            target=self.scan, daemon=True
        ).start()

    def scan(self):
        results = []
        try:
            markets = api("/market/all?isDetails=false")
            names = [
                x["market"] for x in markets
                if x["market"].startswith("KRW-")
                and x["market"] != "KRW-BTC"
            ]

            tickers = []
            for i in range(0, len(names), 50):
                query = urllib.parse.urlencode(
                    {"markets": ",".join(names[i:i+50])}
                )
                tickers.extend(api("/ticker?" + query))

            tickers.sort(
                key=lambda x: x["acc_trade_price_24h"],
                reverse=True
            )
            selected = tickers[:MAX_COINS]

            self.root.after(
                0, lambda: self.progress.configure(
                    maximum=len(selected), value=0
                )
            )

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    pool.submit(analyze, item): item
                    for item in selected
                }

                for index, future in enumerate(as_completed(futures), 1):
                    try:
                        results.append(future.result())
                    except Exception:
                        pass

                    self.root.after(
                        0, lambda n=index:
                        self.progress.configure(value=n)
                    )

            results.sort(
                key=lambda x: (-x["score"], -x["volume"])
            )

            self.results = results
            now = datetime.now().strftime("%H:%M:%S")

            self.root.after(0, self.render)
            self.root.after(
                0, lambda: self.status.set(
                    f"분석 완료 {now} | 성공 {len(results)}종목"
                )
            )

        except Exception as error:
            message = str(error)[:120]
            self.root.after(
                0, lambda: self.status.set("연결 오류: " + message)
            )

        finally:
            self.busy = False
            self.root.after(
                0, lambda: self.scan_button.configure(state="normal")
            )

    def render(self):
        self.table.delete(*self.table.get_children())

        for x in self.results:
            if self.filter.get() not in ("전체", x["status"]):
                continue

            self.table.insert("", "end", values=(
                x["market"].replace("KRW-", ""),
                f'{x["price"]:,.0f}',
                f'{x["change"]:+.2f}%',
                f'{x["r4"]:.1f}',
                f'{x["rd"]:.1f}',
                f'{x["score"]}/7',
                f'{x["volume"]:.2f}배',
                x["status"]
            ))

    def show_detail(self, event=None):
        selected = self.table.selection()
        if not selected:
            return

        coin = self.table.item(selected[0])["values"][0]
        item = next(
            (x for x in self.results
             if x["market"] == "KRW-" + coin),
            None
        )
        if not item:
            return

        self.detail.delete("1.0", "end")
        reasons = ", ".join(item["reasons"]) or "특별한 조건 없음"

        self.detail.insert(
            "end",
            f'{coin} 분석 상세\n'
            f'4시간 RSI: {item["r4"]:.1f} | '
            f'일봉 RSI: {item["rd"]:.1f}\n'
            f'고점 대비: {item["drawdown"]:.2f}% | '
            f'거래량: {item["volume"]:.2f}배\n'
            f'감지 조건: {reasons}\n'
            f'판정: {item["status"]}\n'
            '기술적 참고 정보이며 매수 추천이나 수익 보장이 아닙니다.'
        )

    def auto_refresh(self):
        self.start_scan()
        self.root.after(
            REFRESH_SECONDS * 1000, self.auto_refresh
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
