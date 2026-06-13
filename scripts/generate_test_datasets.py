"""
Generate reproducible complex test datasets for RAVDA manual / integration testing.

Usage:
    python scripts/generate_test_datasets.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "tests" / "data"

SEED = 20250610
ROW_COUNT = 1847

REGIONS = ["华东", "华北", "华南", "西南", "西北", "东北"]
CITIES_BY_REGION: dict[str, list[str]] = {
    "华东": ["上海", "杭州", "南京", "苏州", "合肥"],
    "华北": ["北京", "天津", "石家庄", "太原", "呼和浩特"],
    "华南": ["广州", "深圳", "东莞", "佛山", "厦门"],
    "西南": ["成都", "重庆", "昆明", "贵阳", "拉萨"],
    "西北": ["西安", "兰州", "乌鲁木齐", "银川", "西宁"],
    "东北": ["沈阳", "大连", "哈尔滨", "长春", "齐齐哈尔"],
}

CATEGORIES = {
    "电子产品": [
        ("无线蓝牙耳机", "ELEC-BT-001", 199, 899),
        ("智能手表", "ELEC-WT-002", 899, 2499),
        ("平板电脑", "ELEC-TB-003", 1299, 4999),
        ("机械键盘", "ELEC-KB-004", 299, 1299),
        ("移动电源", "ELEC-PB-005", 79, 299),
    ],
    "家居": [
        ("记忆棉枕头", "HOME-PL-101", 89, 399),
        ("空气净化器", "HOME-AP-102", 699, 2999),
        ("乳胶床垫", "HOME-MT-103", 1299, 5999),
        ("收纳箱套装", "HOME-ST-104", 49, 199),
        ("智能台灯", "HOME-LP-105", 129, 599),
    ],
    "服饰": [
        ("轻薄羽绒服", "FASH-DW-201", 399, 1599),
        ("运动跑鞋", "FASH-SN-202", 299, 1299),
        ("商务衬衫", "FASH-SH-203", 129, 599),
        ("休闲牛仔裤", "FASH-JN-204", 199, 799),
        ("羊毛围巾", "FASH-SC-205", 99, 499),
    ],
    "食品": [
        ("有机坚果礼盒", "FOOD-NT-301", 68, 298),
        ("进口咖啡豆", "FOOD-CF-302", 88, 368),
        ("即食燕麦片", "FOOD-OT-303", 29, 89),
        ("特级初榨橄榄油", "FOOD-OL-304", 98, 398),
        ("冻干水果", "FOOD-FD-305", 39, 128),
    ],
    "图书": [
        ("Python数据分析", "BOOK-PY-401", 59, 128),
        ("商业思维入门", "BOOK-BZ-402", 39, 98),
        ("中国历史通史", "BOOK-HI-403", 78, 198),
        ("儿童绘本套装", "BOOK-KD-404", 88, 268),
        ("考研数学真题", "BOOK-EX-405", 45, 89),
    ],
}

CUSTOMER_SEGMENTS = ["新客", "普通", "VIP", "企业"]
CHANNELS = ["自营App", "自营Web", "天猫旗舰店", "京东POP", "线下门店"]
PAYMENT_METHODS = ["支付宝", "微信支付", "信用卡", "花呗分期", "对公转账"]
SALESPEOPLE = [f"SP-{i:03d}" for i in range(1, 41)] + [None] * 5


def _seasonal_multiplier(d: date) -> float:
    month = d.month
    if month in (11, 12):
        return 1.35
    if month in (6, 7, 8):
        return 0.92
    if month == 2:
        return 1.12
    return 1.0


def _weekend_boost(d: date) -> float:
    return 1.18 if d.weekday() >= 5 else 1.0


def _pick_product(rng: random.Random) -> tuple[str, str, str, float, float]:
    category = rng.choice(list(CATEGORIES.keys()))
    name, sku, low, high = rng.choice(CATEGORIES[category])
    unit_price = round(rng.uniform(low, high), 2)
    return category, name, sku, unit_price, low / high


def generate_retail_orders(n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    start = date(2024, 1, 1)
    end = date(2024, 12, 31)
    span_days = (end - start).days

    rows: list[dict] = []
    for i in range(n):
        region = rng.choices(REGIONS, weights=[22, 18, 20, 14, 8, 18], k=1)[0]
        city = rng.choice(CITIES_BY_REGION[region])
        order_day = start + timedelta(days=rng.randint(0, span_days))
        segment = rng.choices(
            CUSTOMER_SEGMENTS,
            weights=[28, 45, 18, 9],
            k=1,
        )[0]
        channel = rng.choices(
            CHANNELS,
            weights=[25, 15, 22, 18, 20],
            k=1,
        )[0]
        if channel == "线下门店":
            payment = rng.choice(["支付宝", "微信支付", "信用卡"])
        elif segment == "企业":
            payment = rng.choices(PAYMENT_METHODS, weights=[5, 5, 10, 5, 75], k=1)[0]
        else:
            payment = rng.choices(PAYMENT_METHODS, weights=[30, 35, 15, 18, 2], k=1)[0]

        category, product_name, sku, unit_price, _ = _pick_product(rng)
        qty = int(np_rng.integers(1, 6))
        if segment == "企业":
            qty = int(np_rng.integers(5, 51))
        elif segment == "VIP" and rng.random() < 0.3:
            qty = int(np_rng.integers(2, 9))

        base_discount = rng.uniform(0, 0.15)
        if order_day.month in (11, 12):
            base_discount += rng.uniform(0.05, 0.25)
        if channel in ("天猫旗舰店", "京东POP"):
            base_discount += rng.uniform(0.02, 0.08)
        discount_rate = round(min(base_discount, 0.45), 4)

        season = _seasonal_multiplier(order_day)
        weekend = _weekend_boost(order_day)
        segment_boost = {"新客": 0.85, "普通": 1.0, "VIP": 1.45, "企业": 2.1}[segment]

        gross = unit_price * qty * season * weekend * segment_boost
        sales_amount = round(gross * (1 - discount_rate), 2)

        if rng.random() < 0.015:
            sales_amount = None

        cost_ratio = rng.uniform(0.42, 0.72)
        if category == "图书":
            cost_ratio = rng.uniform(0.35, 0.55)
        elif category == "食品":
            cost_ratio = rng.uniform(0.48, 0.65)
        cost_amount = round((sales_amount or gross * (1 - discount_rate)) * cost_ratio, 2)

        is_returned = rng.random() < (0.045 if category == "服饰" else 0.018)
        if is_returned and sales_amount is not None:
            sales_amount = round(sales_amount * rng.uniform(0, 0.3), 2)

        shipping_days = int(np_rng.integers(1, 8))
        if region in ("西北", "东北"):
            shipping_days += int(np_rng.integers(1, 4))
        if channel == "线下门店":
            shipping_days = 0

        satisfaction: float | None = round(float(np_rng.uniform(2.5, 5.0)), 1)
        if is_returned:
            satisfaction = round(float(np_rng.uniform(1.0, 3.2)), 1)
        if rng.random() < 0.032:
            satisfaction = None

        salesperson = rng.choice(SALESPEOPLE)
        if channel != "线下门店":
            salesperson = None if rng.random() < 0.85 else salesperson

        promo_flag = order_day.month in (6, 11, 12) and rng.random() < 0.62

        rows.append(
            {
                "order_id": f"ORD-2024-{i + 1:06d}",
                "order_date": order_day.isoformat(),
                "region": region,
                "city": city,
                "product_category": category,
                "product_name": product_name,
                "sku_code": sku,
                "quantity": qty,
                "unit_price": unit_price,
                "discount_rate": discount_rate,
                "sales_amount": sales_amount,
                "cost_amount": cost_amount,
                "payment_method": payment,
                "customer_segment": segment,
                "sales_channel": channel,
                "is_returned": "是" if is_returned else "否",
                "satisfaction_score": satisfaction,
                "shipping_days": shipping_days,
                "salesperson_id": salesperson if salesperson else "",
                "is_promotion": "是" if promo_flag else "否",
            }
        )

    df = pd.DataFrame(rows)

    outlier_idx = rng.sample(range(n), k=max(3, n // 400))
    for idx in outlier_idx:
        df.at[idx, "sales_amount"] = round(float(df.at[idx, "sales_amount"] or 0) * rng.uniform(3.5, 8.0), 2)
        df.at[idx, "quantity"] = int(df.at[idx, "quantity"]) * rng.randint(2, 5)

    dup_source = rng.randint(0, n - 1)
    dup_row = df.iloc[dup_source].copy()
    dup_row["order_id"] = f"ORD-2024-DUP-{dup_source + 1:06d}"
    dup_row["order_date"] = (date.fromisoformat(dup_row["order_date"]) + timedelta(days=1)).isoformat()
    df = pd.concat([df, dup_row.to_frame().T], ignore_index=True)

    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = generate_retail_orders(ROW_COUNT, SEED)
    csv_path = OUTPUT_DIR / "enterprise_retail_orders.csv"
    xlsx_path = OUTPUT_DIR / "enterprise_retail_orders.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="订单明细", index=False)
        summary = (
            df.groupby(["region", "product_category"], dropna=False)["sales_amount"]
            .agg(订单数="count", 销售额合计="sum", 均价="mean")
            .reset_index()
        )
        summary.to_excel(writer, sheet_name="区域品类汇总", index=False)

    print(f"Generated {len(df):,} rows x {len(df.columns)} cols")
    print(f"  CSV : {csv_path}")
    print(f"  XLSX: {xlsx_path} (sheets: 订单明细, 区域品类汇总)")
    print(f"  Null sales_amount: {df['sales_amount'].isna().sum()}")
    print(f"  Null satisfaction_score: {df['satisfaction_score'].isna().sum()}")
    print(f"  Returns (是): {(df['is_returned'] == '是').sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
