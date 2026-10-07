# 规范化规则（影响 input_hash 稳定性）

1. 所有文本字段在 hash 前统一 NFC Unicode 规范化
2. 去除首尾空白字符
3. dict 按 key 字母序排列再序列化
4. 空值统一为 null，不使用空字符串代替
5. 布尔值使用 true/false，不使用 1/0
