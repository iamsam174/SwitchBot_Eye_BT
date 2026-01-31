import tkinter as tk
from tkinter import ttk, messagebox
import threading
import cv2
from PIL import Image, ImageTk
import winsound
import sys
import asyncio
import traceback
from bleak import BleakClient, BleakScanner

UUID_VAL = "cba20002-224d-11e6-9fb8-0002a5d5c51b"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("SwitchBot BT Control App")
        
        # 起動時に最大化（タスクバーが見える状態）にする
        self.root.state('zoomed')
        
        # キーバインドの設定
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.bind("<F11>", self.toggle_fullscreen)
        
        self.target_mac = None
        self.client = None
        self.is_running = False
        self.cap = None
        self.loop = None
        self.sound = tk.BooleanVar(value=True)
        self.mode = tk.IntVar(value=1)
        self.found_devs = []

        # 初期サイズを「中」に変更
        self.size_var = tk.StringVar(value="中")
        self.sizes = {"大": (800, 450), "中": (600, 338), "小": (400, 225)}

        try:
            self.setup_ui()
            # 高速化のため待機時間を短縮
            self.root.after(100, self.update_camera)
            self.root.after(200, self.start_thread)
        except Exception as e:
            messagebox.showerror("UI起動エラー", traceback.format_exc())
            sys.exit()

    def toggle_fullscreen(self, event=None):
        """F11キーで全画面と最大化を切り替える"""
        is_full = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not is_full)

    def setup_ui(self):
        f_b = ("MS Gothic", 12, "bold")
        f_large = ("MS Gothic", 14, "bold") 
        
        self.header = tk.Frame(self.root)
        self.header.pack(side="top", fill="x", padx=40, pady=5)

        adm = tk.LabelFrame(self.header, text="1. 支援者用設定 (Bluetooth接続)", font=f_b)
        adm.pack(fill="x", pady=2)

        r1 = tk.Frame(adm)
        r1.pack(fill="x", padx=5, pady=2)
        tk.Button(r1, text="🔍 SwitchBotプラグミニを探査", command=self.scan, font=f_b).pack(side="left", padx=5)
        self.lbl_s = tk.Label(r1, text="BT準備中", font=f_b)
        self.lbl_s.pack(side="left", padx=5)

        tk.Label(r1, text=" | 手動:", font=f_b).pack(side="left")
        self.cb_dev = ttk.Combobox(r1, state="readonly", width=25)
        self.cb_dev.pack(side="left", padx=5)
        tk.Button(r1, text="接続", command=self.conn).pack(side="left", padx=5)

        tk.Label(r1, text=" | カメラ:", font=f_b).pack(side="left")
        self.cb_cam = ttk.Combobox(r1, state="readonly", width=10, font=f_b)
        self.cb_cam['values'] = ("カメラ1", "カメラ2", "カメラなし")
        self.cb_cam.current(2)
        self.cb_cam.pack(side="left", padx=5)
        self.cb_cam.bind("<<ComboboxSelected>>", self.cam_chg)

        self.lbl_m = tk.Label(adm, text="未設定", font=("MS Gothic", 10))
        self.lbl_m.pack(anchor="w", padx=15)

        r2 = tk.Frame(adm)
        r2.pack(fill="x", padx=5, pady=2)
        tk.Checkbutton(r2, text="音を鳴らす", variable=self.sound, font=f_b).pack(side="left", padx=10)
        tk.Label(r2, text=" | 動作モード:", font=f_b).pack(side="left")
        tk.Radiobutton(r2, text="①クリックor注視でタイマー", variable=self.mode, value=1, font=f_b).pack(side="left", padx=5)
        tk.Radiobutton(r2, text="②マウスオーバーでタイマー", variable=self.mode, value=2, font=f_b).pack(side="left", padx=5)
        tk.Radiobutton(r2, text="③マウスポインターがボタン内にある間ON", variable=self.mode, value=3, font=f_b).pack(side="left", padx=5)

        tk.Label(self.header, text="2. タイマー秒数(下のスライダーを動かして1～180秒で設定してください)", font=f_large).pack(pady=(10,0))
        self.sc_t = tk.Scale(self.header, from_=1, to=180, orient="horizontal", length=600)
        self.sc_t.set(5)
        self.sc_t.pack()

        self.lbl_t = tk.Label(self.header, text="3. ON", font=f_large)
        self.lbl_t.pack(pady=(5, 0))

        self.size_panel = tk.Frame(self.header)
        self.size_panel.pack(pady=5)
        tk.Label(self.size_panel, text="ボタンサイズ:", font=f_b).pack(side="left")
        self.cb_size = ttk.Combobox(self.size_panel, textvariable=self.size_var, state="readonly", width=5, font=f_b)
        self.cb_size['values'] = ("大", "中", "小")
        self.cb_size.pack(side="left", padx=5)
        self.cb_size.bind("<<ComboboxSelected>>", self.resize_canvas)

        self.canvas_container = tk.Frame(self.root)
        self.canvas_container.place(relx=0.5, rely=0.6, anchor="center")

        w, h = self.sizes[self.size_var.get()]
        self.cv = tk.Canvas(self.canvas_container, width=w, height=h, bg="#b2e2a2", highlightthickness=10, highlightbackground="#b2e2a2")
        self.cv.pack()
        self.id_i = self.cv.create_image(w//2, h//2, anchor="center")
        self.id_t = self.cv.create_text(w//2, h//2, text="スイッチON", font=("MS Gothic", 48, "bold"), fill="#333333", anchor="center")

        self.cv.bind("<Button-1>", self.on_start_drag)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_stop_drag)
        
        self.cv.bind("<Enter>", lambda e: self.ent())
        self.cv.bind("<Leave>", lambda e: self.lev())

        self.lbl_esc = tk.Label(self.root, text="※スイッチONボタンはドラッグで移動できます / F11キーで画面切り替え（全画面表示⇔ウィンドウ表示）ができます", font=f_b)
        self.lbl_esc.pack(side="bottom", pady=10)

    def on_start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._is_dragging = False

    def on_drag(self, event):
        if abs(event.x - self._drag_start_x) > 5 or abs(event.y - self._drag_start_y) > 5:
            self._is_dragging = True
            x = self.canvas_container.winfo_x() + (event.x - self._drag_start_x)
            y = self.canvas_container.winfo_y() + (event.y - self._drag_start_y)
            self.canvas_container.place(x=x, y=y, anchor="nw", relx=0, rely=0)

    def on_stop_drag(self, event):
        if not getattr(self, '_is_dragging', False):
            self.act()
        self._is_dragging = False

    def resize_canvas(self, event=None):
        w, h = self.sizes[self.size_var.get()]
        self.cv.config(width=w, height=h)
        self.cv.coords(self.id_i, w//2, h//2)
        s = self.cb_cam.get()
        if s == "カメラなし":
            self.cv.coords(self.id_t, w//2, h//2)
            self.cv.itemconfig(self.id_t, font=("MS Gothic", 48, "bold"))
        else:
            self.cv.coords(self.id_t, w//2, 40)
            self.cv.itemconfig(self.id_t, font=("MS Gothic", 28, "bold"))

    def cam_chg(self, e=None):
        w, h = self.sizes[self.size_var.get()]
        s = self.cb_cam.get()
        if self.cap: self.cap.release()
        if s == "カメラなし":
            self.cap = None
            self.cv.itemconfig(self.id_i, image="")
            self.cv.coords(self.id_t, w//2, h//2)
            self.cv.itemconfig(self.id_t, font=("MS Gothic", 48, "bold"))
        else:
            self.cv.coords(self.id_t, w//2, 40)
            self.cv.itemconfig(self.id_t, font=("MS Gothic", 28, "bold"))
            idx = 0 if s == "カメラ1" else 1
            self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)

    def update_camera(self):
        try:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    w, h = self.sizes[self.size_var.get()]
                    frame = cv2.resize(cv2.flip(frame, 1), (w, h))
                    self.tk_img = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                    self.cv.itemconfig(self.id_i, image=self.tk_img)
        except Exception: pass
        self.root.after(15, self.update_camera)

    def start_thread(self):
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.create_task(self.keep())
            self.loop.run_forever()
        threading.Thread(target=run, daemon=True).start()

    async def keep(self):
        while True:
            await asyncio.sleep(2)
            if self.target_mac and (self.client is None or not self.client.is_connected):
                self.up_s("接続中", "orange")
                try:
                    self.client = BleakClient(self.target_mac); await self.client.connect()
                    self.up_s("接続完了", "green")
                except Exception: self.up_s("再試行中", "red")

    def up_s(self, t, c):
        if self.root: self.root.after(0, lambda: self.lbl_s.config(text=t, fg=c))

    def scan(self):
        if not self.loop: return
        self.up_s("スキャン中", "blue")
        async def do():
            try:
                ds = await BleakScanner.discover(timeout=5.0)
                nms, found = [], []
                for d in ds:
                    n = d.name if d.name else "Unknown"
                    found.append(d.address); nms.append(f"{n} ({d.address})")
                self.root.after(0, lambda: self.update_dev_list(nms, found))
                self.up_s("完了", "black")
            except Exception: pass
        asyncio.run_coroutine_threadsafe(do(), self.loop)

    def update_dev_list(self, nms, found):
        self.cb_dev.config(values=nms); self.found_devs = found

    def conn(self):
        i = self.cb_dev.current()
        if i >= 0: self.target_mac = self.found_devs[i]

    def send(self, on):
        if not self.client or not self.client.is_connected: return
        v = b'\x57\x01\x01' if on else b'\x57\x01\x00'
        asyncio.run_coroutine_threadsafe(self.client.write_gatt_char(UUID_VAL, v), self.loop)

    def act(self):
        if self.mode.get() == 1: self.run_t()
    def ent(self):
        if self.mode.get() == 2: self.run_t()
        elif self.mode.get() == 3:
            self.send(True); self.lbl_t.config(text="実行中", fg="red"); self.cv.config(highlightbackground="red")
    def lev(self):
        if self.mode.get() == 3:
            self.send(False); self.lbl_t.config(text="3. ON", fg="black"); self.cv.config(highlightbackground="#b2e2a2")

    def run_t(self):
        if self.is_running: return
        self.is_running = True; self.send(True)
        if self.sound.get(): winsound.Beep(800, 200)
        self.remaining = self.sc_t.get()
        self.cv.config(highlightbackground="red"); self.update_timer()

    def update_timer(self):
        if self.remaining > 0:
            self.lbl_t.config(text=f"実行中 {self.remaining}秒", fg="red")
            self.remaining -= 1; self.root.after(1000, self.update_timer)
        else: self.fin_t()

    def fin_t(self):
        self.send(False); self.lbl_t.config(text="3. ON", fg="black")
        self.cv.config(highlightbackground="#b2e2a2"); self.is_running = False

if __name__ == "__main__":
    r = tk.Tk(); a = App(r); r.mainloop()