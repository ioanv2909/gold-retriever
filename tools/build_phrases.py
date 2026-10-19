import json
import os
import sys

src, answers = sys.argv[1], sys.argv[2]
ro = json.load(open(src, encoding="utf-8"))
pf = "i18n_phrases.json"
phr = json.load(open(pf, encoding="utf-8")) if os.path.exists(pf) else {}
n = 0
for line in open(answers, encoding="utf-8"):
    line = line.rstrip("\n")
    if "|" not in line:
        continue
    i, en = line.split("|", 1)
    try:
        i = int(i.strip())
    except ValueError:
        continue
    if not (1 <= i <= len(ro)) or not en.strip():
        continue
    r, en = ro[i - 1], en.replace("\\n", "\n")
    phr[r] = en
    phr["**" + r + "**"] = "**" + en + "**"
    phr[r + ": n/a"] = en + ": n/a"
    n += 1
json.dump(phr, open(pf, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("adaugate:", n, "| total in dictionar:", len(phr))

