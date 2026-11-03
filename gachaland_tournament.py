# -*- coding: utf-8 -*-
"""
GacchaLand - Epic seven | Quản lý giải đấu RTA (loại trực tiếp, BO3)
Chạy:  pip install pillow   rồi   python gachaland_tournament.py
Tiến trình tự động lưu vào file gachaland_save.json (cùng thư mục).
"""
import json
import os
import random
import re
import tkinter as tk
import webbrowser
from tkinter import messagebox, font as tkfont

from PIL import Image, ImageDraw, ImageTk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(APP_DIR, "gachaland_save.json")
DISCORD_URL = "https://discord.gg/3YsBE2UTYf"
BG_CANDIDATES = [os.path.join(APP_DIR, n) for n in
                 ("background.jpg", "background.png", "background.jpeg")]

# ---------- màu ----------
PANEL = "#1b1630"
BOX = "#241d3b"
BOX_LINE = "#6b5aa8"
INPUT = "#120e22"
GOLD = "#f6d27a"
WHITE = "#f4efff"
MUTED = "#8f86b0"
ACCENT = "#7c4dff"
GREEN = "#1fa968"
GREY = "#4a4466"


# =====================================================================
#  LOGIC THUẦN (không phụ thuộc giao diện)
# =====================================================================
def new_match():
    return {"a": None, "b": None, "sa": "", "sb": ""}


def schedule(n):
    """Số trận mỗi vòng khi xếp cặp liên tiếp; số lẻ thì 1 người đi thẳng.
    Trả về list (số_trận, có_người_đi_thẳng)."""
    out = []
    while n > 1:
        k, odd = n // 2, n % 2 == 1
        out.append((k, odd))
        n = k + (1 if odd else 0)
    return out


def _bye_first(state, r):
    """Vòng lẻ-người: vòng chẵn (0,2..) người đi thẳng là người CUỐI,
    vòng lẻ (1,3..) là người ĐẦU -> không ai được miễn đấu 2 vòng liên tiếp."""
    return bool(state["odd"][r]) and r % 2 == 1


def slot_of(state, r, e):
    """Entry thứ e của vòng r nằm ở đâu: ('bye',) hoặc ('m', trận, 'a'/'b')."""
    if state["odd"][r]:
        if _bye_first(state, r):
            if e == 0:
                return ("bye",)
            e -= 1
        elif e == 2 * len(state["rounds"][r]):
            return ("bye",)
    return ("m", e // 2, "a" if e % 2 == 0 else "b")


def next_entry(state, r, kind, m=None):
    """Vị trí entry ở vòng r+1 của: người thắng trận m ('win') hoặc người
    đi thẳng của vòng r ('bye')."""
    first = _bye_first(state, r)
    if kind == "win":
        return m + (1 if first else 0)
    return 0 if first else len(state["rounds"][r])


def entry_name(state, r, e):
    if r >= len(state["rounds"]):
        return state["champion"]
    sl = slot_of(state, r, e)
    if sl[0] == "bye":
        return state["byes"][r]
    return state["rounds"][r][sl[1]][sl[2]]


def place(state, r, e, name):
    """Đặt người chơi vào entry e của vòng r (tự đi tiếp nếu là người đi thẳng)."""
    rounds = state["rounds"]
    if r >= len(rounds):
        state["champion"] = name
        return
    sl = slot_of(state, r, e)
    if sl[0] == "bye":
        old = state["byes"][r]
        if old == name:
            return
        if old:
            remove_name(state, r, "bye", old)
        state["byes"][r] = name
        place(state, r + 1, next_entry(state, r, "bye"), name)
    else:
        _, j, sd = sl
        m = rounds[r][j]
        old = m[sd]
        if old == name:
            return
        if old:
            remove_name(state, r, j, old)
        m[sd] = name
        m["s" + sd] = ""


def remove_name(state, r, where, name):
    """Xóa name khỏi trận `where` (hoặc 'bye') của vòng r và mọi vòng sau."""
    rounds = state["rounds"]
    if where == "bye":
        if state["byes"][r] != name:
            return
        state["byes"][r] = None
        _clear_entry(state, r + 1, next_entry(state, r, "bye"), name)
        return
    match = rounds[r][where]
    found = False
    for sd in ("a", "b"):
        if match[sd] == name:
            match[sd] = None
            match["s" + sd] = ""
            found = True
    if found:
        _clear_entry(state, r + 1, next_entry(state, r, "win", where), name)


def _clear_entry(state, r, e, name):
    if r >= len(state["rounds"]):
        if state["champion"] == name:
            state["champion"] = None
        return
    sl = slot_of(state, r, e)
    remove_name(state, r, "bye" if sl[0] == "bye" else sl[1], name)


def build_rounds(players, shuffle):
    """Xếp cặp lần lượt; người chơi lẻ cuối cùng tự động vào vòng sau."""
    plist = list(players)
    if shuffle:
        random.shuffle(plist)
    sched = schedule(len(plist))
    state = {
        "rounds": [[new_match() for _ in range(k)] for k, _ in sched],
        "odd": [o for _, o in sched],
        "byes": [None] * len(sched),
        "champion": None,
    }
    for e, name in enumerate(plist):
        place(state, 0, e, name)
    return state


def advance(state, r, m, side):
    name = state["rounds"][r][m][side]
    if not name:
        return
    place(state, r + 1, next_entry(state, r, "win", m), name)


def unadvance(state, r, m, name):
    _clear_entry(state, r + 1, next_entry(state, r, "win", m), name)


def is_advanced(state, r, m, side):
    name = state["rounds"][r][m][side]
    return bool(name) and entry_name(
        state, r + 1, next_entry(state, r, "win", m)) == name


def layout_positions(state, UNIT, ROWH):
    """Tọa độ y (chưa dịch) của từng trận và ô 'đi thẳng' ở mỗi vòng."""
    rounds = state["rounds"]
    k0 = len(rounds[0])
    n0 = 2 * k0 + (1 if state["odd"][0] else 0)
    ent = [(e // 2) * UNIT + ROWH for e in range(n0)]
    ycent, ybye = [], []
    for r in range(len(rounds)):
        k, odd = len(rounds[r]), state["odd"][r]
        first = _bye_first(state, r)
        if first:
            yb, pairs = ent[0], ent[1:]
        elif odd:
            yb, pairs = ent[-1], ent[:-1]
        else:
            yb, pairs = None, ent
        yc = [(pairs[2 * j] + pairs[2 * j + 1]) / 2 for j in range(k)]
        ycent.append(yc)
        ybye.append(yb)
        ent = ([yb] if first else []) + yc + ([yb] if odd and not first else [])
    return ycent, ybye


def round_title(r, total):
    left = total - r
    return {1: "CHUNG KẾT", 2: "BÁN KẾT", 3: "TỨ KẾT"}.get(left, f"VÒNG {r + 1}")


WIN_GAMES = 2   # BO3: thắng 2 ván là thắng trận
WIN_GAMES_FINALS = 3   # BO5: Bán kết + Chung kết, thắng 3 ván


def wins_needed(state, r):
    """Số ván cần thắng ở vòng r: 2 vòng cuối (Bán kết, Chung kết) là BO5."""
    return WIN_GAMES_FINALS if r >= len(state["rounds"]) - 2 else WIN_GAMES


def bo_of(state, r):
    return 2 * wins_needed(state, r) - 1


def get_score(m, side):
    try:
        return int(m["s" + side] or 0)
    except (ValueError, TypeError):
        return 0


def set_score(m, side, v):
    m["s" + side] = str(v)


def bump_score(state, r, mi, side, delta):
    """Tăng/giảm tỷ số. Đủ số ván thắng -> tự đi tiếp; giảm xuống dưới -> tự rút lại."""
    need = wins_needed(state, r)
    m = state["rounds"][r][mi]
    if not (m["a"] and m["b"]):
        return
    other = "b" if side == "a" else "a"
    cur = get_score(m, side)
    if delta > 0:
        if cur >= need or get_score(m, other) >= need:
            return
        cur += 1
        set_score(m, side, cur)
        if cur >= need:
            advance(state, r, mi, side)
    else:
        if cur <= 0:
            return
        was_adv = is_advanced(state, r, mi, side)
        cur -= 1
        set_score(m, side, cur)
        if was_adv and cur < need:
            unadvance(state, r, mi, m[side])


# =====================================================================
#  GIAO DIỆN
# =====================================================================
class App:
    def __init__(self, root):
        self.root = root
        root.title("GacchaLand - Epic seven | RTA Tournament")
        root.geometry("1500x860")
        root.minsize(1100, 650)

        self.state = {"players": [], "rounds": [], "champion": None,
                      "shuffle": True, "bracket_players": [],
                      "left_hidden": False, "odd": [], "byes": []}
        self.load()
        self.validate_state()

        self.src = self.load_bg()
        self.bg_photo = None
        self.bc_photo = None
        self.layout_info = None
        self._cfg_job = None
        self.btn_items = {}

        fam = "Segoe UI"
        self.f_norm = tkfont.Font(family=fam, size=11)
        self.f_bold = tkfont.Font(family=fam, size=11, weight="bold")
        self.f_name = tkfont.Font(family=fam, size=12)
        self.f_namebold = tkfont.Font(family=fam, size=12, weight="bold")
        self.f_small = tkfont.Font(family=fam, size=9)
        self.f_head = tkfont.Font(family=fam, size=10, weight="bold")
        self.f_title = tkfont.Font(family=fam, size=13, weight="bold")
        self.f_big = tkfont.Font(family=fam, size=16, weight="bold")

        self.cv = tk.Canvas(root, highlightthickness=0, bg="#2a1840")
        self.cv.pack(fill="both", expand=True)
        self.bg_id = self.cv.create_image(0, 0, anchor="nw")

        self.build_left()
        self.build_bracket_area()
        self.build_qr()

        self.cv.bind("<Configure>", self.on_configure)
        root.bind_all("<MouseWheel>", self.on_wheel)
        root.bind_all("<Button-4>", lambda e: self.on_wheel(e, 120))
        root.bind_all("<Button-5>", lambda e: self.on_wheel(e, -120))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.refresh_list()
        self.update_status()

    # ---------- lưu / tải ----------
    def load(self):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in self.state:
                if k in data:
                    self.state[k] = data[k]
        except Exception:
            pass

    def validate_state(self):
        st = self.state
        R = len(st["rounds"])
        if R and (len(st.get("odd", [])) != R or len(st.get("byes", [])) != R):
            # file lưu của phiên bản cũ -> bỏ bảng cũ
            st.update(rounds=[], champion=None, odd=[], byes=[],
                      bracket_players=[])

    def save(self):
        try:
            tmp = SAVE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SAVE_FILE)
        except Exception as e:
            print("Lỗi lưu:", e)

    def on_close(self):
        self.save()
        self.root.destroy()

    def load_bg(self):
        for p in BG_CANDIDATES:
            if os.path.exists(p):
                try:
                    im = Image.open(p).convert("RGB")
                    im.thumbnail((2400, 2400))
                    return im
                except Exception:
                    pass
        im = Image.new("RGB", (1600, 800), "#3a2060")
        d = ImageDraw.Draw(im)
        for y in range(800):
            c = int(40 + 90 * y / 800)
            d.line([(0, y), (1600, y)], fill=(c, 30, c + 40))
        return im

    # ---------- khung trái ----------
    def build_left(self):
        self.left = tk.Frame(self.cv, bg=PANEL, highlightthickness=2,
                             highlightbackground=BOX_LINE)
        self.left_win = self.cv.create_window(0, 0, anchor="nw",
                                              window=self.left)
        L = self.left
        tk.Label(L, text="DANH SÁCH NGƯỜI CHƠI", bg=PANEL, fg=GOLD,
                 font=self.f_title).pack(pady=(14, 0))
        self.count_var = tk.StringVar()
        tk.Label(L, textvariable=self.count_var, bg=PANEL, fg=MUTED,
                 font=self.f_small).pack()

        row = tk.Frame(L, bg=PANEL)
        row.pack(fill="x", padx=14, pady=(10, 2))
        self.name_var = tk.StringVar()
        self.entry = tk.Entry(row, textvariable=self.name_var, bg=INPUT,
                              fg=WHITE, insertbackground=WHITE, relief="flat",
                              font=self.f_name)
        self.entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.entry.bind("<Return>", lambda e: self.add_players())
        self.mkbtn(row, "+ Thêm", self.add_players, ACCENT).pack(
            side="left", padx=(6, 0))
        tk.Label(L, text="Thêm nhiều người: ngăn cách bằng dấu phẩy",
                 bg=PANEL, fg=MUTED, font=self.f_small).pack(anchor="w",
                                                              padx=14)

        lf = tk.Frame(L, bg=PANEL)
        lf.pack(fill="both", expand=True, padx=14, pady=8)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(lf, bg=INPUT, fg=WHITE, relief="flat",
                                  selectbackground=ACCENT, font=self.f_name,
                                  activestyle="none", highlightthickness=0,
                                  selectmode="extended",
                                  yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Delete>", lambda e: self.remove_selected())

        self.mkbtn(L, "Xóa người đã chọn", self.remove_selected, GREY).pack(
            fill="x", padx=14, pady=2)
        self.mkbtn(L, "Xóa toàn bộ danh sách", self.clear_players,
                   "#a23b4a").pack(fill="x", padx=14, pady=2)
        self.shuffle_var = tk.BooleanVar(value=bool(self.state["shuffle"]))
        tk.Checkbutton(L, text="Xáo trộn khi tạo bảng", variable=self.shuffle_var,
                       command=self.on_shuffle, bg=PANEL, fg=WHITE,
                       selectcolor=INPUT, activebackground=PANEL,
                       activeforeground=WHITE, font=self.f_norm).pack(
            anchor="w", padx=12, pady=(6, 0))
        self.mkbtn(L, "TẠO BẢNG ĐẤU", self.make_bracket, GREEN,
                   bold=True).pack(fill="x", padx=14, pady=(6, 2), ipady=4)
        self.mkbtn(L, "Reset bảng đấu", self.reset_bracket, "#a23b4a").pack(
            fill="x", padx=14, pady=2)
        self.status_var = tk.StringVar()
        tk.Label(L, textvariable=self.status_var, bg=PANEL, fg=MUTED,
                 font=self.f_small, wraplength=250, justify="left").pack(
            fill="x", padx=14, pady=(6, 12))

    def mkbtn(self, parent, text, cmd, color, bold=False):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                         activebackground=color, activeforeground="white",
                         relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                         font=self.f_bold if bold else self.f_norm)

    # ---------- khung bảng đấu ----------
    def build_bracket_area(self):
        self.bf = tk.Frame(self.cv, bg=PANEL, highlightthickness=2,
                           highlightbackground=BOX_LINE)
        self.bf_win = self.cv.create_window(0, 0, anchor="nw", window=self.bf)
        self.bf.grid_rowconfigure(1, weight=1)
        self.bf.grid_columnconfigure(0, weight=1)
        tb = tk.Frame(self.bf, bg=PANEL)
        tb.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.toggle_btn = self.mkbtn(tb, "◀ Ẩn danh sách", self.toggle_left,
                                     ACCENT)
        self.toggle_btn.pack(side="left", padx=8, pady=5)
        tk.Label(tb, text="GacchaLand - Epic seven  |  Boss LeXuan",
                 bg=PANEL, fg=GOLD, font=self.f_title).place(
            relx=0.5, rely=0.5, anchor="center")
        self.sby = tk.Scrollbar(self.bf, orient="vertical")
        self.sbx = tk.Scrollbar(self.bf, orient="horizontal")
        self.bc = tk.Canvas(self.bf, highlightthickness=0, bg="#201838",
                            xscrollcommand=self._xs, yscrollcommand=self._ys)
        self.bc.grid(row=1, column=0, sticky="nsew")
        self.sby.grid(row=1, column=1, sticky="ns")
        self.sbx.grid(row=2, column=0, sticky="ew")
        self.sby.config(command=self.bc.yview)
        self.sbx.config(command=self.bc.xview)
        self.bc_bg = self.bc.create_image(0, 0, anchor="nw", tags="bgimg")

    # ---------- ô QR donate + link Discord (góc phải dưới) ----------
    def build_qr(self):
        f = tk.Frame(self.cv, bg=PANEL, highlightthickness=2,
                     highlightbackground=GOLD)
        self.qr_frame = f
        self.qr_win = self.cv.create_window(0, 0, anchor="se", window=f)
        tk.Label(f, text="DONATE", bg=PANEL, fg=GOLD,
                 font=self.f_head).pack(pady=(6, 2))
        self.qr_label = tk.Label(f, bg=PANEL)
        self.qr_label.pack(padx=8)
        self.load_qr()
        tk.Label(f, text="Discord bình luận trận đấu", bg=PANEL, fg=MUTED,
                 font=self.f_small).pack(pady=(8, 0), padx=8)
        link = tk.Label(f, text="discord.gg/3YsBE2UTYf", bg=PANEL,
                        fg="#7aa2ff", cursor="hand2",
                        font=tkfont.Font(family="Segoe UI", size=9,
                                         underline=True))
        link.pack(pady=(0, 7), padx=8)
        link.bind("<Button-1>", lambda e: webbrowser.open(DISCORD_URL))

    @staticmethod
    def find_qr():
        exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
        try:
            for fn in os.listdir(APP_DIR):
                stem, ext = os.path.splitext(fn)
                if stem.lower() == "qr" and ext.lower() in exts:
                    return os.path.join(APP_DIR, fn)
        except OSError:
            pass
        return None

    def load_qr(self):
        path = self.find_qr()
        self.qr_path = path
        self.qr_photo = None
        if path:
            try:
                im = Image.open(path).convert("RGBA")
                im.thumbnail((130, 130))
                self.qr_photo = ImageTk.PhotoImage(im)
            except Exception:
                path = None
        if self.qr_photo:
            self.qr_label.config(image=self.qr_photo, text="", cursor="hand2")
            self.qr_label.bind("<Button-1>", lambda e: self.show_qr_big())
        else:
            self.qr_label.config(image="", cursor="",
                                 text="Chưa có ảnh QR\n(đặt file QR.png\ncạnh chương trình)",
                                 fg=MUTED, font=self.f_small, width=20,
                                 height=7, justify="center")

    def show_qr_big(self):
        try:
            im = Image.open(self.qr_path).convert("RGBA")
        except Exception:
            return
        im.thumbnail((460, 460))
        top = tk.Toplevel(self.root)
        top.title("QR Donate")
        top.configure(bg=PANEL)
        top.photo = ImageTk.PhotoImage(im)
        tk.Label(top, image=top.photo, bg=PANEL).pack(padx=12, pady=12)

    def _xs(self, *a):
        self.sbx.set(*a)
        self.reposition_bg()

    def _ys(self, *a):
        self.sby.set(*a)
        self.reposition_bg()

    def reposition_bg(self):
        self.bc.coords(self.bc_bg, self.bc.canvasx(0), self.bc.canvasy(0))
        self.bc.tag_lower(self.bc_bg)

    def on_wheel(self, e, delta=None):
        d = delta if delta is not None else e.delta
        x, y = self.root.winfo_pointerxy()
        w = self.root.winfo_containing(x, y)
        inside = False
        while w is not None:
            if w is self.bc:
                inside = True
                break
            w = getattr(w, "master", None)
        if not inside:
            return
        step = -1 if d > 0 else 1
        if e.state & 0x0001:
            self.bc.xview_scroll(step * 3, "units")
        else:
            self.bc.yview_scroll(step * 3, "units")

    # ---------- bố cục / nền ----------
    def on_configure(self, e):
        if self._cfg_job:
            self.root.after_cancel(self._cfg_job)
        self._cfg_job = self.root.after(120, self.do_layout)

    @staticmethod
    def cover(img, W, H):
        s = max(W / img.width, H / img.height)
        nw, nh = int(img.width * s) + 1, int(img.height * s) + 1
        im = img.resize((nw, nh), Image.BILINEAR)
        l, t = (nw - W) // 2, (nh - H) // 2
        return im.crop((l, t, l + W, t + H))

    def toggle_left(self):
        self.state["left_hidden"] = not self.state.get("left_hidden", False)
        self.save()
        self.do_layout()

    def do_layout(self):
        W, H = self.cv.winfo_width(), self.cv.winfo_height()
        if W < 300 or H < 300:
            return
        M, LW = 18, 290
        hidden = bool(self.state.get("left_hidden"))
        bh = H - 2 * M
        if hidden:
            self.cv.itemconfigure(self.left_win, state="hidden")
            bx = M
        else:
            self.cv.coords(self.left_win, M, M)
            self.cv.itemconfigure(self.left_win, state="normal", width=LW,
                                  height=bh)
            bx = M + LW + M
        bw = W - M - bx
        self.cv.coords(self.bf_win, bx, M)
        self.cv.itemconfigure(self.bf_win, width=bw, height=bh)
        self.cv.coords(self.qr_win, W - M - 30, H - M - 30)
        self.qr_frame.lift()
        self.toggle_btn.config(text="▶ Hiện danh sách" if hidden
                               else "◀ Ẩn danh sách")

        base = self.cover(self.src, W, H)
        crop = base.crop((bx, M, bx + bw, M + bh))
        dark = Image.new("RGB", crop.size, (12, 8, 30))
        crop = Image.blend(crop, dark, 0.5)
        self.bc_photo = ImageTk.PhotoImage(crop)
        self.bc.itemconfigure(self.bc_bg, image=self.bc_photo)
        self.bg_photo = ImageTk.PhotoImage(base)
        self.cv.itemconfigure(self.bg_id, image=self.bg_photo)
        self.cv.tag_lower(self.bg_id)
        self.draw_bracket()

    # ---------- cúp vàng (nằm trên ô vô địch) ----------
    def draw_trophy(self, cx, bt):
        bc = self.bc
        s = 0.6
        cy = bt - 36 - 135 * s

        def P(dx, dy):
            return cx + dx * s, cy + dy * s

        def poly(pts, **kw):
            flat = [c for p in pts for c in P(*p)]
            bc.create_polygon(flat, tags="br", **kw)

        poly([(-75, 108), (75, 108), (75, 135), (-75, 135)],
             fill="#9a6d08", outline="#6b4a05", width=2)
        poly([(-55, 88), (55, 88), (55, 110), (-55, 110)],
             fill="#d4a017", outline="#8a6508", width=2)
        poly([(-13, 38), (13, 38), (24, 90), (-24, 90)],
             fill="#e8b923", outline="#8a6508", width=2)
        for sign in (-1, 1):
            x0, y0 = P(sign * 135, -108)
            x1, y1 = P(sign * 62, -30)
            bc.create_arc(min(x0, x1), y0, max(x0, x1), y1,
                          start=90 if sign < 0 else -90, extent=180,
                          style="arc", outline="#e8b923", width=8, tags="br")
        poly([(-88, -122), (88, -122), (82, -42), (44, 24), (13, 42),
              (-13, 42), (-44, 24), (-82, -42)], fill="#f7c52f",
             outline="#8a6508", width=3, smooth=True)
        poly([(-66, -112), (-46, -112), (-54, -38), (-34, 6), (-44, 6),
              (-66, -38)], fill="#fde68a", outline="", smooth=True)
        x, y = P(0, -66)
        bc.create_text(x, y, text="E7", fill="#8a6508",
                       font=("Georgia", 32, "bold"), tags="br")
        bc.create_text(cx + 1, bt - 17, text="GacchaLand - Epic seven",
                       fill="#000", font=self.f_head, tags="br")
        bc.create_text(cx, bt - 18, text="GacchaLand - Epic seven",
                       fill=GOLD, font=self.f_head, tags="br")

    # ---------- danh sách người chơi ----------
    def refresh_list(self):
        self.listbox.delete(0, "end")
        for i, p in enumerate(self.state["players"], 1):
            self.listbox.insert("end", f"{i}. {p}")
        self.count_var.set(f"Tổng: {len(self.state['players'])} người")

    def add_players(self):
        raw = self.name_var.get()
        names = [n.strip() for n in re.split(r"[,;\n]", raw) if n.strip()]
        have = {p.casefold() for p in self.state["players"]}
        added = 0
        for n in names:
            if n.casefold() in have:
                continue
            self.state["players"].append(n)
            have.add(n.casefold())
            added += 1
        self.name_var.set("")
        if added:
            self.refresh_list()
            self.listbox.see("end")
            self.save()
        self.update_status()
        self.entry.focus_set()

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self.state["players"][i]
        self.refresh_list()
        self.save()
        self.update_status()

    def clear_players(self):
        if not self.state["players"]:
            return
        if not messagebox.askyesno(
                "Xóa toàn bộ danh sách",
                f"Xóa tất cả {len(self.state['players'])} người chơi?\n"
                "Bảng đấu hiện tại (nếu có) vẫn giữ nguyên cho tới khi bạn "
                "tạo bảng mới hoặc reset."):
            return
        self.state["players"] = []
        self.refresh_list()
        self.save()
        self.update_status()

    def on_shuffle(self):
        self.state["shuffle"] = bool(self.shuffle_var.get())
        self.save()

    def update_status(self):
        if self.state["rounds"] and \
                self.state["players"] != self.state["bracket_players"]:
            self.status_var.set("⚠ Danh sách đã thay đổi. Bấm TẠO BẢNG ĐẤU để "
                                "áp dụng (tiến trình hiện tại sẽ bị reset).")
        else:
            self.status_var.set("✔ Tiến trình được tự động lưu.")

    # ---------- tạo / reset ----------
    def make_bracket(self):
        n = len(self.state["players"])
        if n < 2:
            messagebox.showinfo("Chưa đủ người", "Cần ít nhất 2 người chơi.")
            return
        if self.state["rounds"] and not messagebox.askyesno(
                "Tạo bảng mới", "Tạo bảng mới sẽ xóa tiến trình hiện tại. "
                                "Tiếp tục?"):
            return
        st = build_rounds(self.state["players"], self.shuffle_var.get())
        self.state.update(rounds=st["rounds"], odd=st["odd"],
                          byes=st["byes"], champion=None)
        self.state["bracket_players"] = list(self.state["players"])
        self.save()
        self.update_status()
        self.draw_bracket()

    def reset_bracket(self):
        if not self.state["rounds"]:
            return
        if not messagebox.askyesno("Reset", "Xóa toàn bộ bảng đấu và tiến "
                                            "trình? (danh sách người chơi giữ nguyên)"):
            return
        self.state.update(rounds=[], odd=[], byes=[], champion=None,
                          bracket_players=[])
        self.save()
        self.update_status()
        self.draw_bracket()

    # ---------- vẽ bảng đấu ----------
    ROWH, BOXW, GAP = 38, 310, 64
    LEFT, TROPH = 24, 215

    def fit(self, text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def btn(self, x, y, w, h, text, cmd, fill, enabled=True):
        """Nút vẽ trên canvas."""
        bc = self.bc
        fill = fill if enabled else "#2c2644"
        r = bc.create_rectangle(x, y, x + w, y + h, fill=fill, outline="",
                                tags="br")
        t = bc.create_text(x + w / 2, y + h / 2, text=text, tags="br",
                           fill="white" if enabled else "#6d6690",
                           font=self.f_bold)
        if enabled:
            for i in (r, t):
                bc.tag_bind(i, "<Button-1>", lambda e, c=cmd: c())
                bc.tag_bind(i, "<Enter>",
                            lambda e: bc.config(cursor="hand2"))
                bc.tag_bind(i, "<Leave>", lambda e: bc.config(cursor=""))

    def draw_bracket(self):
        bc = self.bc
        bc.delete("br")
        st = self.state
        rounds = st["rounds"]
        if not rounds:
            bc.create_text(30, 30, anchor="nw", fill=WHITE, font=self.f_big,
                           tags="br",
                           text="Chưa có bảng đấu.\nThêm người chơi rồi bấm "
                                "'TẠO BẢNG ĐẤU'.")
            bc.configure(scrollregion=(0, 0, 10, 10))
            self.reposition_bg()
            return

        R = len(rounds)
        ROWH, BOXW, GAP = self.ROWH, self.BOXW, self.GAP
        PITCH = BOXW + GAP
        UNIT = 2 * ROWH + 28

        ycent, ybye = layout_positions(st, UNIT, ROWH)
        TOP = max(64, 8 + self.TROPH + ROWH - ycent[-1][0])
        ycent = [[y + TOP for y in col] for col in ycent]
        ybye = [None if y is None else y + TOP for y in ybye]
        X = lambda r: self.LEFT + r * PITCH
        xc = X(R)
        cyf = ycent[-1][0]
        ymax = max([y for col in ycent for y in col] +
                   [y for y in ybye if y is not None]) + ROWH

        # --- tiêu đề vòng ---
        for r in range(R):
            cx = X(r) + BOXW / 2
            bc.create_rectangle(cx - 90, 14, cx + 90, 42, fill=PANEL,
                                outline=BOX_LINE, tags="br")
            bc.create_text(cx, 28, fill=GOLD, font=self.f_head, tags="br",
                           text=f"{round_title(r, R)}  ·  BO{bo_of(st, r)}")

        # --- đường nối ---
        def dest_y(r2, e):
            sl = slot_of(st, r2, e)
            return ybye[r2] if sl[0] == "bye" else ycent[r2][sl[1]]

        for r in range(R - 1):
            srcs = [(ycent[r][j], next_entry(st, r, "win", j))
                    for j in range(len(rounds[r]))]
            if ybye[r] is not None:
                srcs.append((ybye[r], next_entry(st, r, "bye")))
            for ys, e in srcs:
                yd = dest_y(r + 1, e)
                xs, xe = X(r) + BOXW, X(r + 1)
                xm = xs + GAP / 2
                bc.create_line(xs, ys, xm, ys, xm, yd, xe, yd,
                               fill=BOX_LINE, width=2, tags="br")
        bc.create_line(X(R - 1) + BOXW, cyf, xc, cyf, fill=GOLD, width=2,
                       tags="br")

        # --- các trận và ô đi thẳng ---
        for r in range(R):
            for mi in range(len(rounds[r])):
                self.draw_match(r, mi, X(r), ycent[r][mi])
            if ybye[r] is not None:
                self.draw_bye(r, X(r), ybye[r])

        # --- ô vô địch + cúp ---
        champ = st.get("champion")
        bc.create_rectangle(xc, cyf - ROWH, xc + 260, cyf + ROWH,
                            fill="#3a2a05", outline=GOLD, width=3, tags="br")
        bc.create_text(xc + 130, cyf - 14, text="★ VÔ ĐỊCH ★", fill=GOLD,
                       font=self.f_big, tags="br")
        bc.create_text(xc + 130, cyf + 16, fill="white",
                       font=self.f_namebold, tags="br",
                       text=self.fit(champ, self.f_namebold, 240) if champ
                       else "—")
        self.draw_trophy(xc + 130, cyf - ROWH)

        bc.configure(scrollregion=(0, 0, xc + 300, ymax + 24))
        self.reposition_bg()

    def draw_bye(self, r, x, cy):
        """Ô người chơi lẻ: tự động vào thẳng vòng sau."""
        bc = self.bc
        name = self.state["byes"][r]
        h = self.ROWH / 2
        bc.create_rectangle(x, cy - h, x + self.BOXW, cy + h, fill=BOX,
                            outline=GOLD, width=2, dash=(5, 3), tags="br")
        if name:
            bc.create_text(x + 10, cy, anchor="w", fill=GOLD,
                           font=self.f_namebold, tags="br",
                           text=self.fit(name, self.f_namebold,
                                         self.BOXW - 150))
        else:
            bc.create_text(x + 10, cy, anchor="w", fill=MUTED,
                           font=self.f_small, text="chờ kết quả…", tags="br")
        bc.create_text(x + self.BOXW - 10, cy, anchor="e", fill=MUTED,
                       font=self.f_small, text="vào thẳng vòng sau",
                       tags="br")

    def draw_match(self, r, mi, x, cy):
        bc, st = self.bc, self.state
        ROWH, BOXW = self.ROWH, self.BOXW
        m = st["rounds"][r][mi]
        active = bool(m["a"] and m["b"])
        need = wins_needed(st, r)
        right = x + BOXW
        namew = BOXW - 10 - 124

        bc.create_rectangle(x, cy - ROWH, right, cy + ROWH, fill=BOX,
                            outline=BOX_LINE, width=2, tags="br")
        bc.create_line(x, cy, right, cy, fill=BOX_LINE, tags="br")

        for k, sk in enumerate(("a", "b")):
            ry = cy - ROWH / 2 if k == 0 else cy + ROWH / 2
            ok = "b" if sk == "a" else "a"
            name = m[sk]
            adv = is_advanced(st, r, mi, sk)
            other_adv = bool(m[ok]) and is_advanced(st, r, mi, ok)
            if name:
                color = GOLD if adv else (MUTED if other_adv else WHITE)
                font = self.f_namebold if adv else self.f_name
                bc.create_text(x + 10, ry, anchor="w", fill=color, font=font,
                               text=self.fit(name, font, namew), tags="br")
            else:
                bc.create_text(x + 10, ry, anchor="w", fill=MUTED,
                               font=self.f_small, text="chờ kết quả…",
                               tags="br")
            if not active:
                continue

            # [-]  tỷ số  [+]   [▶/↩]
            by = ry - 13
            bx = right - 118
            sc, sc_o = get_score(m, sk), get_score(m, ok)
            self.btn(bx, by, 24, 26, "−",
                     lambda r=r, mi=mi, sk=sk: self.on_minus(r, mi, sk),
                     GREY, enabled=sc > 0)
            bc.create_rectangle(bx + 26, by, bx + 48, by + 26, fill=INPUT,
                                outline="", tags="br")
            bc.create_text(bx + 37, ry, text=str(sc), tags="br",
                           fill=GOLD if sc >= need else WHITE,
                           font=self.f_bold)
            self.btn(bx + 50, by, 24, 26, "+",
                     lambda r=r, mi=mi, sk=sk: self.on_plus(r, mi, sk),
                     GREEN, enabled=sc < need and sc_o < need)
            self.btn(right - 36, by, 28, 26, "↩" if adv else "▶",
                     lambda r=r, mi=mi, sk=sk: self.on_adv(r, mi, sk),
                     GREY if adv else ACCENT)

    # ---------- sự kiện ----------
    def after_change(self):
        self.save()
        self.draw_bracket()

    def on_plus(self, r, mi, sk):
        bump_score(self.state, r, mi, sk, +1)
        self.after_change()

    def on_minus(self, r, mi, sk):
        bump_score(self.state, r, mi, sk, -1)
        self.after_change()

    def on_adv(self, r, mi, sk):
        """▶ = cho đi tiếp thủ công (ví dụ xử thắng); ↩ = rút lại."""
        st = self.state
        m = st["rounds"][r][mi]
        if is_advanced(st, r, mi, sk):
            unadvance(st, r, mi, m[sk])
            need = wins_needed(st, r)
            if get_score(m, sk) >= need:
                set_score(m, sk, need - 1)
        else:
            advance(st, r, mi, sk)
        self.after_change()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
