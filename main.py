
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import json
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

API = "https://api.upbit.com/v1"

def get_api(path):
    req = urllib.request.Request(
        API + path,
        headers={"User-Agent": "CoinAnalyzer/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100 if avg_gain else 50
    return 100 - 100 / (1 + avg_gain / avg_loss)

def ema(values, period):
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * k + result[-1] * (1-k))
    return result

def analyze(market, ticker):
    four = get_api(
        f"/candles/minutes/240?market={market}&count=80"
    )
    daily = get_api(
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

    cross = macd[-2] <= signal[-2] and macd[-1] > signal[-1]
    improving = macd[-1] > macd[-2]

    volumes = [x["candle_acc_trade_volume"] for x in four]
    avg_volume = sum(volumes[-21:-1]) / 20
    volume_ratio = volumes[-1] / avg_volume if avg_volume else 0

    high = max(x["high_price"] for x in four[-42:])
    drawdown = (ticker["trade_price"] / high - 1) * 100

    score = 0
    reasons = []

    if r4 <= 35:
        score += 2
        reasons.append("4시간 RSI 과매도")

    if rd <= 45:
        score += 1
        reasons.append("일봉 RSI 낮음")

    if cross:
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

    return {
        "market": market,
        "price": ticker["trade_price"],
        "change": ticker["signed_change_rate"] * 100,
        "rsi4": r4,
        "rsid": rd,
        "score": score,
        "volume": volume_ratio,
        "drawdown": drawdown,
        "reasons": reasons
    }

class CoinAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("코인 분석실 - Upbit")
        self.root.geometry("950x650")
        self.root.minsize(750, 500)
        self.busy = False
        self.results = []

        top = ttk.Frame(root, padding=12)
        top.pack(fill="x")

        ttk.Label(
            top, text="📊 코인 분석실",
            font=("Malgun Gothic", 19, "bold")
        ).pack(side="left")

        self.status = tk.StringVar(value="분석 대기 중")
        ttk.Label(top, textvariable=self.status).pack(side="right")

        controls = ttk.Frame(root, padding=10)
        controls.pack(fill="x")

        self.filter = tk.StringVar(value="전체")
        ttk.Label(controls, text="분류").pack(side="left")

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
            "coin", "price", "change", "rsi4",
            "rsid", "score", "volume", "status"
        )

        self.table = ttk.Treeview(
            root, columns=columns, show="headings"
        )

        headers = {
            "coin": "코인",
            "price": "현재가",
            "change": "24시간 변동",
            "rsi4": "4H RSI",
            "rsid": "일봉 RSI",
            "score": "점수",
            "volume": "거래량 배수",
            "status": "분석 결과"
        }

        for col, title in headers.items():
            self.table.heading(col, text=title)
            self.table.column(col, width=105, anchor="center")

        self.table.pack(fill="both", expand=True, padx=12, pady=8)

        self.details = tk.Text(root, height=7, wrap="word")
        self.details.pack(fill="x", padx=12, pady=8)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=5)

        self.root.after(300000, self.auto_refresh)
        self.start_scan()

    def start_scan(self):
        if self.busy:
            return
        self.busy = True
        self.scan_button.configure(state="disabled")
        self.status.set("업비트 시세 수집 및 분석 중...")
        threading.Thread(
            target=self.scan, daemon=True
        ).start()

    def scan(self):
        try:
            markets = get_api("/market/all?isDetails=false")
            names = [
                x["market"] for x in markets
                if x["market"].startswith("KRW-")
                and x["market"] != "KRW-BTC"
            ]

            tickers = []
            for i in range(0, len(names), 50):
                tickers += get_api(
                    "/ticker?markets=" + ",".join(names[i:i+50])
                )

            tickers.sort(
                key=lambda x: x["acc_trade_price_24h"],
                reverse=True
            )
            selected = tickers[:30]
            results = []

            self.root.after(
                0, lambda: self.progress.configure(
                    maximum=len(selected), value=0
                )
            )

            def work(item):
                try:
                    return analyze(item["market"], item)
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(work, x) for x in selected]
                for i, future in enumerate(futures):
                    result = future.result()
                    if result:
                        results.append(result)
                    self.root.after(
                        0, lambda n=i+1:
                        self.progress.configure(value=n)
                    )

            results.sort(
                key=lambda x: (-x["score"], x["change"])
            )

            self.results = results
            self.root.after(0, self.render)
            self.root.after(
                0, lambda: self.status.set(
                    "분석 완료 · " +
                    datetime.now().strftime("%H:%M:%S")
                )
            )

        except Exception as e:
            self.root.after(
                0, lambda: self.status.set(
                    "연결 오류: " + str(e)[:80]
                )
            )
        finally:
            self.busy = False
            self.root.after(
                0, lambda: self.scan_button.configure(
                    state="normal"
                )
            )

    def render(self):
        self.table.delete(*self.table.get_children())
        self.details.delete("1.0", "end")

        count = 0
        for x in self.results:
            if x["score"] >= 5 and x["rsi4"] <= 40:
                status = "매수 관심"
            elif x["score"] >= 3:
                status = "관찰"
            else:
                status = "대기"

            if x["change"] <= -12:
                status = "위험"

            if self.filter.get() != "전체" and self.filter.get() != status:
                continue

            count += 1
            self.table.insert("", "end", values=(
                x["market"].replace("KRW-", ""),
                f'{x["price"]:,.0f}',
                f'{x["change"]:+.2f}%',
                f'{x["rsi4"]:.1f}',
                f'{x["rsid"]:.1f}',
                f'{x["score"]}/7',
                f'{x["volume"]:.2f}배',
                status
            ))

        self.details.insert(
            "end",
            f"분석 종목 {count}개\n"
            "RSI·MACD·거래량을 종합한 참고 지표입니다.\n"
            "매수 관심은 실제 매수 추천이나 수익 보장이 아닙니다."
        )

    def auto_refresh(self):
        self.start_scan()
        self.root.after(300000, self.auto_refresh)

if __name__ == "__main__":
    window = tk.Tk()
    app = CoinAnalyzer(window)
    window.mainloop()
