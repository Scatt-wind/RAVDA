# tests/data

## 职责

- 存放可版本管理的静态测试数据文件
- 不包含运行时生成或用户上传数据

## 关键文件

| 文件 | 说明 |
|------|------|
| `sample_sales.csv` | 8 行精简 fixture：product_name, sales_amount, order_date, region（含 1 处空值）；pytest 默认使用 |
| `enterprise_retail_orders.csv` | **复杂真实场景**：1,848 行 × 20 列 B2C 零售订单明细（2024 全年） |
| `enterprise_retail_orders.xlsx` | 同上 CSV + 「区域品类汇总」Sheet；用于 Excel 上传与多 Sheet 验证 |

### enterprise_retail_orders 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `order_id` | 文本 | 订单编号（含 1 条近重复业务行，order_id 不同） |
| `order_date` | 日期 | 2024-01-01 ~ 2024-12-31 |
| `region` / `city` | 分类 | 六大区 + 对应城市 |
| `product_category` | 分类 | 电子产品 / 家居 / 服饰 / 食品 / 图书 |
| `product_name` / `sku_code` | 文本 | 商品名与 SKU |
| `quantity` / `unit_price` | 数值 | 数量、单价 |
| `discount_rate` | 数值 | 0~0.45，大促月份更高 |
| `sales_amount` | 数值 | 销售额（~1.8% 空值；含退货折损与少量离群大单） |
| `cost_amount` | 数值 | 成本，可用于毛利分析 |
| `payment_method` | 分类 | 支付宝 / 微信 / 信用卡 / 花呗 / 对公 |
| `customer_segment` | 分类 | 新客 / 普通 / VIP / 企业 |
| `sales_channel` | 分类 | 自营 App/Web、天猫、京东、线下门店 |
| `is_returned` | 是/否 | 退货标记（服饰品类退货率更高） |
| `satisfaction_score` | 数值 | 1~5 分（~3.7% 空值） |
| `shipping_days` | 整数 | 配送天数（线下为 0） |
| `salesperson_id` | 文本 | 线下导购工号（~71% 空值） |
| `is_promotion` | 是/否 | 是否参与 618/双11/双12 大促 |

内置数据特征：季节性（Q4 偏高）、周末效应、区域/渠道/客群差异、缺失值、退货、离群值。

### 推荐自然语言测试问题

- 按地区统计销售额并画柱状图
- 各产品品类销售额占比，画饼图
- 2024 年每月销售额趋势，画折线图
- VIP 客户平均客单价是多少
- 哪个销售渠道退货率最高
- 大促期间（is_promotion=是）与非大促销售额对比
- 按支付方式统计订单数量
- 华东 vs 华南 销售额对比
- 满意度评分低于 3 分的订单有多少
- 计算毛利率（sales_amount - cost_amount）按品类汇总

## 对外接口

- 无；供上传测试、画像断言、RAG 联调与手动 `/query` 验证引用
- 重新生成：`python scripts/generate_test_datasets.py`（固定种子 `20250610`）

## 依赖关系

- **上游**：`scripts/smoke_test.py`、`scripts/generate_test_datasets.py`、curl `-F file=@tests/data/...`
- **下游**：无

## 修改时注意

- `sample_sales.csv` 列名/行数变更需同步 `scripts/smoke_test.py` 与 `tests/test_query_pipeline.py`
- 复杂数据集变更后重新运行 `scripts/generate_test_datasets.py`，勿手改 CSV 以免不可复现
- 勿与 `uploads/` 混淆：此处为固定 fixture，`uploads/` 为 API 写入目录

## 子模块

无（叶子目录）
