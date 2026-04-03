import os

filepath = r"f:\AI-ML\FactForensic\FactForensic\pages\management\commands\fetch.py"
with open(filepath, "r", encoding="utf-8") as f:
    code = f.read()

replacements = {
    "└─": "|-",
    "⛔": "[FAIL]",
    "✅": "[OK]",
    "💾": "[SAVE]",
    "→": "->",
    "⚠️": "[WARN]"
}

for k, v in replacements.items():
    code = code.replace(k, v)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(code)

print("Fixed!")
