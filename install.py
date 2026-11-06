#!/usr/bin/env python3
import curses
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "2442X/actions-v5"
BRANCH = "main"
DEST = ".github/workflows"
PATTERN = re.compile(r"^(common|cpp|python)/[^/]+$")


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "workflow-installer"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def list_files():
    data = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"))
    return sorted(e["path"] for e in data.get("tree", []) if e.get("type") == "blob" and PATTERN.match(e["path"]))


def install(path):
    out = os.path.join(DEST, os.path.basename(path))
    body = fetch(f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}")
    os.makedirs(DEST, exist_ok=True)
    with open(out, "wb") as f:
        f.write(body)
    return out


def draw_box_text(scr, lines, title=""):
    scr.erase()
    h, w = scr.getmaxyx()
    scr.addnstr(0, 0, f" {title} ".ljust(w), w, curses.color_pair(1) | curses.A_BOLD)
    for i, line in enumerate(lines[: h - 2]):
        scr.addnstr(i + 2, 2, line, w - 4)
    scr.refresh()


def select_screen(scr, files, root):
    existing = {f: os.path.exists(os.path.join(DEST, os.path.basename(f))) for f in files}
    checked = set()
    cur = top = 0
    while True:
        h, w = scr.getmaxyx()
        view = max(1, h - 5)
        if cur < top:
            top = cur
        elif cur >= top + view:
            top = cur - view + 1

        scr.erase()
        scr.addnstr(0, 0, f" Install workflows  ·  {REPO}".ljust(w), w, curses.color_pair(1) | curses.A_BOLD)
        scr.addnstr(1, 1, f"into {os.path.join(root, DEST)}", w - 2, curses.A_DIM)

        for row, idx in enumerate(range(top, min(top + view, len(files)))):
            f = files[idx]
            d, name = f.split("/", 1)
            mark = "[x]" if idx in checked else "[ ]"
            attr = curses.A_REVERSE if idx == cur else 0
            line = f" {mark} {d + '/':<8}{name}"
            if existing[f]:
                line += "  (exists)"
            scr.addnstr(row + 3, 0, line.ljust(w), w, attr | (curses.color_pair(2) if idx in checked else 0))

        status = f" {len(checked)}/{len(files)} selected"
        scr.addnstr(h - 2, 0, status.ljust(w), w, curses.A_BOLD)
        keys = " ↑/↓ move   space toggle   a all/none   enter install   q quit"
        scr.addnstr(h - 1, 0, keys.ljust(w), w, curses.color_pair(1))
        scr.refresh()

        k = scr.getch()
        if k in (curses.KEY_UP, ord("k")):
            cur = (cur - 1) % len(files)
        elif k in (curses.KEY_DOWN, ord("j")):
            cur = (cur + 1) % len(files)
        elif k == curses.KEY_PPAGE:
            cur = max(0, cur - view)
        elif k == curses.KEY_NPAGE:
            cur = min(len(files) - 1, cur + view)
        elif k in (curses.KEY_HOME, ord("g")):
            cur = 0
        elif k in (curses.KEY_END, ord("G")):
            cur = len(files) - 1
        elif k == ord(" "):
            checked ^= {cur}
        elif k == ord("a"):
            checked = set() if len(checked) == len(files) else set(range(len(files)))
        elif k in (10, 13, curses.KEY_ENTER):
            if checked:
                return [files[i] for i in sorted(checked)], existing
        elif k in (ord("q"), 27):
            return None, existing


def confirm_overwrites(scr, selected, existing):
    """Returns the list of files to actually install."""
    keep, overwrite_all = [], False
    for f in selected:
        out = os.path.join(DEST, os.path.basename(f))
        if not existing[f] or overwrite_all:
            keep.append(f)
            continue
        draw_box_text(
            scr,
            [f"{out} already exists.", "", "  y  overwrite", "  n  keep existing", "  a  overwrite this and all remaining", "  q  cancel"],
            "Confirm overwrite",
        )
        while True:
            k = scr.getch()
            if k in (ord("y"), ord("Y")):
                keep.append(f)
                break
            if k in (ord("n"), ord("N")):
                break
            if k in (ord("a"), ord("A")):
                keep.append(f)
                overwrite_all = True
                break
            if k in (ord("q"), 27):
                return None
    return keep


def run(scr, root):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    scr.keypad(True)

    draw_box_text(scr, [f"Fetching file list from {REPO}..."], "Workflow installer")
    try:
        files = list_files()
    except Exception as e:
        return [f"Failed to fetch file list: {e}"]
    if not files:
        return ["No files found."]

    selected, existing = select_screen(scr, files, root)
    if selected is None:
        return ["Cancelled."]
    todo = confirm_overwrites(scr, selected, existing)
    if todo is None:
        return ["Cancelled."]

    results = []
    skipped = [f for f in selected if f not in todo]
    for i, f in enumerate(todo, 1):
        draw_box_text(scr, [f"({i}/{len(todo)}) {f}"], "Installing")
        try:
            results.append(f"Installed {install(f)}")
        except Exception as e:
            results.append(f"Failed {f}: {e}")
    results += [f"Kept {os.path.join(DEST, os.path.basename(f))}" for f in skipped]
    results.append("Done!")
    return results


def main():
    try:
        root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        die("This is not a GitHub repository.")
    os.chdir(root)

    if not sys.stdin.isatty():
        try:
            fd = os.open("/dev/tty", os.O_RDWR)
            os.dup2(fd, 0)
        except OSError:
            die("No compatible terminal found.")

    messages = curses.wrapper(run, root)
    print("\n".join(messages))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled.")
