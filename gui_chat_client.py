#!/usr/bin/env python3
import os, json, socket, threading, re, tkinter as tk
from tkinter import (
    simpledialog, messagebox,
    scrolledtext, Toplevel, Frame, Label,
    Entry, Button, Checkbutton, IntVar
)
import cv2, numpy as np, tensorflow as tf
from PIL import Image, ImageDraw

from chat_utils import SERVER, mysend, myrecv, S_LOGGEDIN, S_CHATTING
import client_state_machine as csm

# strip ANSI
ANSI_ESCAPE = re.compile(r'\x1B\[[0-9;]*[mK]')

# load CNN
MODEL_PATH = 'mnist.h5'
if not os.path.exists(MODEL_PATH):
    raise RuntimeError("Missing handwriting_model.h5")
digit_model = tf.keras.models.load_model(MODEL_PATH, compile=False)
DIGITS = '0123456789'

class ChatGUIClient(tk.Toplevel):
    def __init__(self, parent, user, sock):
        super().__init__(parent)
        
        # ─── NEVER ALLOW WINDOW SMALLER THAN 1/4 SCREEN ───
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # set min size to one quarter of screen
        self.minsize(sw // 2, sh // 2)
        # optionally center it
        self.geometry(f"{sw//2}x{sh//2}+{sw//4}+{sh//4}")
        # ───────────────────────────────────────────────────
        
        self.parent = parent
        self.sock = sock
        self.user = user
        self.running = True

        # state machine
        self.sm = csm.ClientSM(self.sock)
        self.sm.set_state(S_LOGGEDIN)
        self.sm.set_myname(user)

        self.awaiting_connect = False
        self.selected_peer = None
        self.last_search_term = None

        self.title(f"Chat – {user}")
        self.protocol("WM_DELETE_WINDOW", self.on_quit)
        self._build_ui()

        # welcome
        self._append(f"Welcome, {user}!")

        threading.Thread(target=self._reader_loop, daemon=True).start()

    def _build_ui(self):
        # display
        self.txt = scrolledtext.ScrolledText(self, state='disabled', wrap='word')
        self.txt.tag_configure("highlight", background="#FFFF00")
        self.txt.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # buttons
        btns = [
            ("Time", self._time), ("Who", self._who),
            ("Connect", self._connect), ("Disconnect", self._disconnect),
            ("Search", self._search), ("Get Poem", self._poem),
            ("CNN", self._digit), ("Quit", self.on_quit)
        ]
        frame = Frame(self)
        frame.pack(fill=tk.X, padx=5, pady=5)
        for txt, cmd in btns:
            Button(frame, text=txt, width=8, command=cmd, font=("Arial", 12)).pack(side=tk.LEFT, padx=4)

        # entry/send
        bottom = Frame(self)
        bottom.pack(fill=tk.X, padx=5, pady=5)
        self.ent = Entry(bottom)
        self.ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.ent.bind("<Return>", lambda e: self._send())
        self.btn_send = Button(bottom, text="Send", width=12, command=self._send)
        self.btn_send.pack(side=tk.RIGHT, padx=2)
        self.btn_send.config(state=tk.DISABLED)

    def _append(self, msg):
        self.txt.configure(state='normal')
        self.txt.insert(tk.END, msg+"\n")
        self.txt.configure(state='disabled')
        self.txt.see(tk.END)

    # button actions
    def _time(self):      mysend(self.sock, json.dumps({"action":"time"}))
    def _who(self):       mysend(self.sock, json.dumps({"action":"list"}))
    def _search(self):
        t = simpledialog.askstring("Search","Term:",parent=self)
        if t:
            self.last_search_term = t
            mysend(self.sock, json.dumps({"action":"search","target":t}))
    def _poem(self):
        n = simpledialog.askinteger("Poem","#:",parent=self,minvalue=1)
        if n: mysend(self.sock, json.dumps({"action":"poem","target":str(n)}))

    def _connect(self):
        if self.sm.get_state()==S_CHATTING:
            messagebox.showwarning("Chatting","Disconnect first.")
            return
        self.awaiting_connect=True
        mysend(self.sock, json.dumps({"action":"list"}))

    def _disconnect(self):
        if self.sm.get_state()!=S_CHATTING:
            messagebox.showwarning("Not chatting","No chat.")
            return
        mysend(self.sock, json.dumps({"action":"disconnect"}))
        self.sm.set_state(S_LOGGEDIN)
        self.sm.peer=''
        self.btn_send.config(state=tk.DISABLED)
        self._append("You have disconnected.")

    def _send(self):
        txt = self.ent.get().strip()
        if not txt: return
        if self.sm.get_state()!=S_CHATTING:
            messagebox.showwarning("Not connected","Connect first.")
            return
        mysend(self.sock, json.dumps({
            "action":"exchange","from":self.user,"message":txt}))
        self._append(f"(you) {txt}")
        self.ent.delete(0,tk.END)

    def _digit(self):
        # canvas for single digit
        w,h=200,200
        dlg=Toplevel(self); dlg.title("Draw Digit")
        c=tk.Canvas(dlg,width=w,height=h,bg='white')
        c.pack()
        im=Image.new('L',(w,h),255); draw=ImageDraw.Draw(im)
        last=None
        def paint(e):
            nonlocal last
            if last:
                c.create_line(last[0],last[1],e.x,e.y,fill='black',width=15,capstyle=tk.ROUND)
                draw.line([last,(e.x,e.y)],fill=0,width=15)
            last=(e.x,e.y)
        def reset(e): nonlocal last; last=None
        c.bind("<B1-Motion>",paint); c.bind("<ButtonRelease-1>",reset)
        def go():
            arr=np.array(im)
            _,thr=cv2.threshold(arr,200,255,cv2.THRESH_BINARY_INV)
            pts=cv2.findNonZero(thr)
            if pts is None:
                messagebox.showinfo("None","No strokes")
                return
            x,y,w0,h0=cv2.boundingRect(pts)
            roi=thr[y:y+h0,x:x+w0]
            sz=max(w0,h0); sq=np.zeros((sz,sz),np.uint8)
            dx,dy=(sz-w0)//2,(sz-h0)//2
            sq[dy:dy+h0,dx:dx+w0]=roi
            img28=cv2.resize(sq,(28,28),interpolation=cv2.INTER_AREA)
            norm=img28.astype(np.float32)/255.0; inp=norm.reshape(1,28,28,1)
            p=digit_model.predict(inp)
            idx=int(np.argmax(p,axis=1)[0]); d=DIGITS[idx]
            dlg.destroy(); self.ent.delete(0,tk.END); self.ent.insert(0,d); self._send()
        Button(dlg,text="Recognize & Send",command=go).pack(pady=5)
        Button(dlg,text="Cancel",command=dlg.destroy).pack()

    # reader loop
    def _reader_loop(self):
        while self.running:
            try: raw=myrecv(self.sock)
            except OSError: break
            if not raw: break
            try: resp=json.loads(raw)
            except: continue
            act=resp.get("action")
            if act=="list":
                if self.awaiting_connect:
                    entries=resp.get("results","")
                    self.after(0,self._show_connect,entries)
                    self.awaiting_connect=False
                else:
                    self.after(0,self._append,"Users:\n"+resp.get("results",""))
            elif act=="connect":
                st=resp.get("status"); frm=resp.get("from","")
                if st=="success":
                    self.sm.set_state(S_CHATTING); self.sm.peer=self.selected_peer
                    self.after(0,self._append,f"You are now connected with {self.selected_peer}.")
                    self.after(0,self.btn_send.config,{'state':tk.NORMAL})
                elif st=="request":
                    self.sm.set_state(S_CHATTING); self.sm.peer=frm
                    self.after(0,self._append,f"{frm} has joined the chat.")
                    self.after(0,self.btn_send.config,{'state':tk.NORMAL})
                else:
                    self.after(0,self._append,f"Connect failed: {resp.get('msg','')}")
            elif act == "disconnect":
                # peer-left notification?
                if resp.get("from") and self.sm.get_state() == S_CHATTING:
                    leaver = resp["from"]
                    self.after(0, self._append, f"{leaver} has left the chat.")
                else:
                    # local or “alone” case
                    self.sm.set_state(S_LOGGEDIN)
                    self.sm.peer = ''
                    self.after(0, self._append, resp.get("msg", "Disconnected."))
                    self.after(0, self.btn_send.config, {'state': tk.DISABLED})

            elif act=="time":
                self.after(0,self._append,f"Time: {resp.get('results')}")
            elif act=="search":
                clean=ANSI_ESCAPE.sub("",resp.get("results",""))
                for line in clean.splitlines():
                    start=self.txt.index(tk.END)
                    self._append(line)
                    t=self.last_search_term
                    if t:
                        idx=self.txt.search(t,start,tk.END,nocase=True)
                        while idx:
                            end=f"{idx}+{len(t)}c"
                            self.txt.tag_add("highlight",idx,end)
                            idx=self.txt.search(t,end,tk.END,nocase=True)
            elif act=="poem":
                p=resp.get("results",[]); txt="\n".join(p) if isinstance(p,list) else p
                self.after(0,self._append,txt)
            elif act=="exchange":
                frm=resp.get("from",""); m=resp.get("message","")
                self.after(0,self._append,f"{frm} {m}")
        self.running=False

    def _show_connect(self, entries):
        users=[u.split(':')[0].strip() for u in entries.split(',') if ':' in u]
        users=[u for u in users if u!=self.user]
        if not users:
            messagebox.showinfo("None","No one online"); return
        dlg=Toplevel(self); dlg.title("Connect To")
        Label(dlg,text="Select user:").pack(padx=10,pady=5)
        var=tk.StringVar(dlg); var.set(users[0])
        tk.OptionMenu(dlg,var,*users).pack(padx=10,pady=5)
        def go():
            self.selected_peer=var.get()
            mysend(self.sock,json.dumps({"action":"connect","target":self.selected_peer}))
            dlg.destroy()
        Button(dlg,text="Connect",command=go).pack(pady=5)
        dlg.transient(self); dlg.grab_set(); self.wait_window(dlg)

    def on_quit(self):
        if self.running and self.sm.get_state()==S_CHATTING:
            try: mysend(self.sock,json.dumps({"action":"disconnect"}))
            except: pass
        self.running=False
        try: self.sock.close()
        except: pass
        self.master.quit()


class AccessControlSystem:
    ACCOUNT_FILE="accounts.json"
    CURRENT_USER_FILE="current_user.json"
    def __init__(self,parent):
        self.parent=parent
        self.accounts=self.load_accounts()
        self.current_user=self.load_current_user()
        self.sock=None
        parent.title("Login"); parent.geometry("400x300"); self.center_window(parent)
        if self.current_user: self.auto_login()
        else: self.create_login_page()

    def center_window(self, window, width=400, height=300):
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry(f'{width}x{height}+{x}+{y}')

    def load_remembered(self):
        try:
            with open("remember_me.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def create_login_page(self):
        for widget in self.parent.winfo_children():
            widget.destroy()

        frame = Frame(self.parent)
        frame.pack(expand=True)

        Label(frame, text="Username", font=("Arial", 14)).grid(row=0, column=0, pady=10)
        self.username_entry = Entry(frame, font=("Arial", 14))
        self.username_entry.grid(row=0, column=1, pady=10)
        if self.current_user:
            self.username_entry.insert(0, self.current_user)

        Label(frame, text="Password", font=("Arial", 14)).grid(row=1, column=0, pady=10)
        self.password_entry = Entry(frame, show="*", font=("Arial", 14))
        self.password_entry.grid(row=1, column=1, pady=10)

        Button(frame, text="Login", width=15, command=self.verify_credentials).grid(row=2, column=0, pady=10)
        Button(frame, text="Sign Up", width=15, command=self.sign_up_page).grid(row=2, column=1, pady=10)
        Button(frame, text="Exit", width=15, command=self.parent.quit).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Remember the key-value pair
        self.remember_var = IntVar()
        self.remember_checkbox = Checkbutton(frame, text="Remember me", variable=self.remember_var,
                                             bg="#f0f0f0")
        self.remember_checkbox.grid(row=6, column=0, columnspan=2)

        self.result_label = Label(frame, text="", font=("Arial", 12), fg="red")
        self.result_label.grid(row=4, column=0, columnspan=2)

        self.remembered = self.load_remembered()
        if self.remembered:
            self.username_entry.insert(0, self.remembered.get("user", ""))
            self.password_entry.insert(0, self.remembered.get("pwd", ""))
            self.remember_var.set(1)

    def verify_credentials(self):
        user_id = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if self.remember_var.get() == 1: # Click the remember checkbox
            with open("remember_me.json", 'w') as f:
                json.dump({"user": user_id, "pwd": password}, f)
        else:
            if os.path.exists("remember_me.json"):
                os.remove("remember_me.json")
        
        if not user_id:
            self.result_label.config(text="Username cannot be empty.", fg="red")
            return

        if user_id not in self.accounts:
            self.result_label.config(text="User not found. Click Sign Up to register.", fg="red")
            return

        if self.accounts[user_id] != password:
            self.result_label.config(text="Incorrect password.", fg="red")
            return

        self.current_user = user_id
        self.save_current_user()
        self.open_welcome_page()

    def auto_login(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(SERVER)
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Cannot connect to server:\n{e}")
            self.create_login_page()
            return

        mysend(self.sock, json.dumps({"action": "login", "name": self.current_user}))
        resp = json.loads(myrecv(self.sock))
        if resp.get("status") == "ok":
            self.open_welcome_page()
        else:
            self.create_login_page()

    def open_welcome_page(self):
        self.parent.withdraw()
        self.new_window = Toplevel()
        self.new_window.title("Welcome")
        self.new_window.geometry("400x300")
        self.center_window(self.new_window)

        Label(self.new_window, text=f"Welcome, {self.current_user}!", font=("Arial", 16)).pack(pady=30)

        Button(self.new_window, text="Start Chatting", width=20, command=self.start_chat).pack(pady=10)
        Button(self.new_window, text="Logout", width=20, command=self.logout).pack(pady=10)

    def start_chat(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(SERVER)
        except Exception as e:
            messagebox.showerror("Connection Failed", f"Cannot connect to server:\n{e}")
            return

        mysend(self.sock, json.dumps({"action": "login", "name": self.current_user}))
        resp = json.loads(myrecv(self.sock))
        if resp.get("status") == "ok":
            self.new_window.withdraw()
            chat_window = ChatGUIClient(self.new_window, self.current_user, self.sock)
            chat_window.mainloop()
        else:
            messagebox.showerror("Login Failed", "Authentication failed.")

    def logout(self):
        if self.sock:
            try:
                mysend(self.sock, json.dumps({"action": "logout"}))
            finally:
                self.sock.close()
                self.sock = None
        self.new_window.destroy()
        self.current_user = ""
        self.save_current_user()

        # 清空原有主窗口组件
        for widget in self.parent.winfo_children():
            widget.destroy()

        self.parent.deiconify()
        self.create_login_page()

    def sign_up_page(self):
        self.parent.withdraw()
        signup_window = Toplevel()
        signup_window.title("Sign Up")
        signup_window.geometry("400x300")
        self.center_window(signup_window)

        frame = Frame(signup_window)
        frame.pack(expand=True)

        Label(frame, text="New User ID", font=("Arial", 12)).grid(row=0, column=0, pady=10)
        new_id = Entry(frame, font=("Arial", 12))
        new_id.grid(row=0, column=1, pady=10)

        Label(frame, text="Password", font=("Arial", 12)).grid(row=1, column=0, pady=10)
        pwd1 = Entry(frame, show="*", font=("Arial", 12))
        pwd1.grid(row=1, column=1, pady=10)

        Label(frame, text="Confirm Password", font=("Arial", 12)).grid(row=2, column=0, pady=10)
        pwd2 = Entry(frame, show="*", font=("Arial", 12))
        pwd2.grid(row=2, column=1, pady=10)

        result = Label(frame, text="", font=("Arial", 12), fg="red")
        result.grid(row=4, column=0, columnspan=2)

        def register():
            user = new_id.get().strip()
            p1 = pwd1.get().strip()
            p2 = pwd2.get().strip()

            if not user or not p1 or not p2:
                result.config(text="Fields cannot be empty.", fg="red")
                return
            if user in self.accounts:
                result.config(text="User already exists.", fg="red")
                return
            if p1 != p2:
                result.config(text="Passwords do not match.", fg="red")
                return

            self.accounts[user] = p1
            self.save_accounts()
            result.config(text="Registration successful!", fg="green")
            signup_window.destroy()
            self.parent.deiconify()

        Button(frame, text="Register", width=15, command=register).grid(row=3, column=0, columnspan=2, pady=10)
        Button(frame, text="Back", width=15, command=lambda: [signup_window.destroy(), self.parent.deiconify()]).grid(
            row=4, column=0, columnspan=2)

    def load_accounts(self):
        if not os.path.exists(self.ACCOUNT_FILE):
            return {}
        try:
            with open(self.ACCOUNT_FILE, "r") as f:
                return json.load(f)
        except:
            return {}

    def save_accounts(self):
        with open(self.ACCOUNT_FILE, "w") as f:
            json.dump(self.accounts, f)

    def load_current_user(self):
        if not os.path.exists(self.CURRENT_USER_FILE):
            return ""
        try:
            with open(self.CURRENT_USER_FILE, "r") as f:
                data = json.load(f)
                return data.get("current_user", "")
        except:
            return ""

    def save_current_user(self):
        with open(self.CURRENT_USER_FILE, "w") as f:
            json.dump({"current_user": self.current_user}, f)


if __name__ == "__main__":
    root = tk.Tk()
    app = AccessControlSystem(root)
    root.mainloop()
