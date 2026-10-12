# -*- coding: utf-8 -*-
"""book-kb 通用推送脚本（复用自 zhishiku_sync_v110.py 四步法）。
功能：1) 仓库不存在则自动创建（含 description/topics）；2) 把 SRC_DIR 下全部文件
（递归，含 skills/ 子目录）以 Git Data API 四步法（blob->tree->commit->PATCH ref）推送到 main。
改头部 REPO_NAME / DESC / TOPICS / SRC_DIR / COMMIT_MSG 即可复用于任意一本新书。
用法：python push_book_kb.py [--create]  （--create 缺仓库时自动建仓）
"""
import json, os, base64, sys, urllib.request, urllib.error

OWNER = "openclawzhangchong"
REPO_NAME = "book-kb"
DESC = ("书本知识库（文档知识库）：把一本书整理成 AI 智能体可直接装载的结构化 Markdown 知识库"
        "（总纲/理论/招式/范例/调用规则五章，每节含关键词与触发场景三件套，RAG 切片友好）。"
        "首本：《厚黑学》知识库（16招+14范例）。与经验库 zhishiku 区分。")
TOPICS = ["book", "knowledge-base", "ai-agent", "rag", "markdown",
          "thick-black-theory", "li-zongwu", "chinese"]
SRC_DIR = r"C:\Users\Administrator\WorkBuddy\2026-10-12-21-00-15\book-kb"
COMMIT_MSG = ("feat: 建库并收录《厚黑学》知识库（2.87万字符：总纲3节/理论7节/招式16招/范例14组/路由表24行）\n\n"
              "- 厚黑学知识库.md：'厚黑学高手'人设智能体装载文件，每节三件套（标题/关键词/触发场景），"
              "招式四要素（使用条件/操作步骤/话术模板/禁区），80%现代方法+20%原著点题\n"
              "- 整理方法论-SOP.md：书本→知识库七步流水线（首本实战提炼）\n"
              "- skills/book-to-kb：可复用 Skill（含通用推送脚本 push_book_kb.py）\n"
              "- README：与经验库 zhishiku 的定位区分 + 收录书目登记表")

CFG = r"C:\Users\Administrator\.workbuddy\mcp.json"
API = "https://api.github.com"
SKIP_EXT = (".pyc",)


def load_token():
    cfg = json.load(open(CFG, encoding="utf-8"))
    for name, srv in cfg.get("mcpServers", {}).items():
        hdrs = srv.get("headers", {}) or {}
        auth = hdrs.get("Authorization", "")
        if auth.startswith("Bearer ") and name == "github-pat":
            return auth.split(" ", 1)[1].strip()
    for name, srv in cfg.get("mcpServers", {}).items():
        hdrs = srv.get("headers", {}) or {}
        auth = hdrs.get("Authorization", "")
        if auth.startswith("Bearer ghp_"):
            return auth.split(" ", 1)[1].strip()
    raise SystemExit("PAT not found in " + CFG)


TOKEN = load_token()


def req(method, path, body=None, ok404=False):
    url = API + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer " + TOKEN)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "book-kb-publisher/1.0")
    if body is not None:
        r.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            txt = resp.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return None
        detail = e.read().decode("utf-8", "replace")[:600]
        print("HTTP %s %s -> %s %s" % (method, path, e.code, detail))
        raise


def ensure_repo():
    if req("GET", "/repos/%s/%s" % (OWNER, REPO_NAME), ok404=True) is not None:
        print("repo exists:", REPO_NAME)
        return
    print("creating repo:", REPO_NAME)
    req("POST", "/user/repos", {"name": REPO_NAME, "description": DESC,
                                "private": False, "auto_init": True})
    req("PATCH", "/repos/%s/%s" % (OWNER, REPO_NAME),
        {"name": REPO_NAME, "description": DESC, "homepage": ""})
    try:
        req("PUT", "/repos/%s/%s/topics" % (OWNER, REPO_NAME), {"names": TOPICS})
        print("topics set:", TOPICS)
    except urllib.error.HTTPError:
        print("topics skipped (permission)")


def collect_files():
    files = {}
    for root, dirs, names in os.walk(SRC_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".workbuddy")]
        for fn in names:
            if fn.lower().endswith(SKIP_EXT):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, SRC_DIR).replace("\\", "/")
            with open(full, "rb") as f:
                files[rel] = f.read()
    return files


def main():
    do_create = "--create" in sys.argv or True  # 默认自动建仓
    if do_create:
        ensure_repo()
    b = req("GET", "/repos/%s/%s/branches/main" % (OWNER, REPO_NAME))
    head = b["commit"]["sha"]
    base_tree = b["commit"]["commit"]["tree"]["sha"]
    print("head:", head[:8], "base_tree:", base_tree[:8])

    files = collect_files()
    print("files:", len(files), sorted(files))

    entries = []
    for path, content in files.items():
        blob = req("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO_NAME),
                   {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = req("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO_NAME),
               {"base_tree": base_tree, "tree": entries})
    print("tree:", tree["sha"][:8])

    commit = req("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO_NAME),
                 {"message": COMMIT_MSG, "parents": [head], "tree": tree["sha"]})
    print("commit:", commit["sha"][:8])

    req("PATCH", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO_NAME),
        {"sha": commit["sha"], "force": True})
    print("ref updated")

    print("DONE https://github.com/%s/%s  commit=%s" % (OWNER, REPO_NAME, commit["sha"]))
    print("COMMIT_SHA=" + commit["sha"])


if __name__ == "__main__":
    main()
