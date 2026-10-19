import ast
import json
import re
import sys

path = sys.argv[1]
DIAC = re.compile("[ăîâșțĂÎÂȘȚşţ]")
FUNCS = {"metric", "subheader", "header", "title", "caption", "markdown", "info", "warning", "error",
         "success", "expander", "button", "selectbox", "number_input", "text_input", "text_area",
         "checkbox", "radio", "toggle", "download_button"}
KW = {"help", "label", "placeholder"}

tree = ast.parse(open(path, encoding="utf-8").read())
skip = set()
for node in ast.walk(tree):
    if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        b = node.body
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
            skip.add(id(b[0].value))
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            skip.add(id(v))

out, seen = [], set()


def add(s):
    if s in seen or not s.strip() or s.strip().startswith("---"):
        return
    if not (DIAC.search(s) or re.search(r"[A-Za-z]{3}", s)):
        return
    seen.add(s)
    out.append(s)


for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in FUNCS:
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and id(node.args[0]) not in skip:
            add(node.args[0].value)
        for kw in node.keywords:
            if kw.arg in KW and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                add(kw.value.value)
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip and DIAC.search(node.value):
        add(node.value)

name = "ro_" + path.replace("/", "_").replace(".py", "") + ".json"
json.dump(out, open(name, "w", encoding="utf-8"), ensure_ascii=False)
for i, s in enumerate(out, 1):
    print(f"{i}|" + s.replace("\n", "\\n"))
print("total:", len(out), "| salvat in", name)
