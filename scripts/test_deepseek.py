# -*- coding: utf-8 -*-
"""快速测试 DeepSeek API 连通性。"""

import os
import sys
from pathlib import Path

# 修复 Windows 终端编码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 加载 .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    print(f"[OK] 已加载 .env: {env_file}")
else:
    print(f"[ERR] 未找到 .env 文件: {env_file}")
    sys.exit(1)

api_key = os.environ.get("DEEPSEEK_API_KEY", "")
base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
thinking = os.environ.get("DEEPSEEK_THINKING", "disabled")

if not api_key or api_key == "sk-your-key-here":
    print("[ERR] 未找到有效的 DEEPSEEK_API_KEY，请检查 .env 文件")
    sys.exit(1)

print(f"[INFO] 连接：{base_url}")
print(f"[INFO] 模型：{model}")
print(f"[INFO] Thinking：{thinking}")
print(f"[INFO] Key：{api_key[:8]}{'*' * 20}")
print()

try:
    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "回复数字1，不要多说任何话。"}],
        "max_tokens": 64,
        "thinking": {"type": thinking},
    }
    if thinking == "enabled":
        payload["reasoning_effort"] = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{base_url}/v1/chat/completions", json=payload, headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print("[OK] 连接成功！")
        print(f"     模型回复：{reply}")
        print(f"     Token消耗：{usage}")
    else:
        print(f"[ERR] 请求失败：HTTP {resp.status_code}")
        print(f"      响应：{resp.text[:300]}")
        sys.exit(1)

except ImportError:
    print("[ERR] 缺少 httpx，请运行：pip install httpx")
    sys.exit(1)
except Exception as e:
    print(f"[ERR] 连接异常：{e}")
    sys.exit(1)
