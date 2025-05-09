#!/usr/bin/env python3
import time
import socket
import select
import json
import pickle as pkl

from chat_utils import SERVER, mysend, myrecv
import indexer
import chat_group as grp


class Server:
    def __init__(self):
        self.new_clients = []                # sockets before login
        self.logged_name2sock = {}           # username → socket
        self.logged_sock2name = {}           # socket → username
        self.all_sockets = []
        self.group = grp.Group()             # group management

        # start listening socket
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(SERVER)
        self.server.listen(5)
        self.all_sockets.append(self.server)

        # per‑user chat indices
        self.indices = {}

        # sonnet database
        self.sonnet = indexer.PIndex("AllSonnets.txt")

    def new_client(self, sock):
        """Add a brand‑new socket before login."""
        print("New connection")
        sock.setblocking(0)
        self.new_clients.append(sock)
        self.all_sockets.append(sock)

    def login(self, sock):
        """Handle login action from a new client."""
        raw = myrecv(sock)
        if not raw:
            self.logout(sock)
            return

        try:
            msg = json.loads(raw)
        except:
            self.logout(sock)
            return

        if msg.get("action") != "login":
            self.logout(sock)
            return

        name = msg.get("name")
        if not name or self.group.is_member(name):
            # duplicate
            mysend(sock, json.dumps({"action":"login", "status":"duplicate"}))
            print(f"Duplicate login attempt for {name}")
            return

        # accept login
        self.new_clients.remove(sock)
        self.logged_name2sock[name] = sock
        self.logged_sock2name[sock] = name

        # load or create index
        try:
            self.indices[name] = pkl.load(open(f"{name}.idx", "rb"))
        except Exception:
            self.indices[name] = indexer.Index(name)

        self.group.join(name)
        mysend(sock, json.dumps({"action":"login", "status":"ok"}))
        print(f"{name} logged in")

    def logout(self, sock):
        """Clean up after a client disconnects."""
        name = self.logged_sock2name.get(sock)
        if name:
            print(f"{name} logging out")
            # save index
            try:
                pkl.dump(self.indices[name], open(f"{name}.idx", "wb"))
            except:
                pass
            # remove mappings
            self.indices.pop(name, None)
            self.logged_name2sock.pop(name, None)
            self.logged_sock2name.pop(sock, None)
            # remove from group
            self.group.leave(name)

        if sock in self.new_clients:
            self.new_clients.remove(sock)
        if sock in self.all_sockets:
            self.all_sockets.remove(sock)
        try:
            sock.close()
        except:
            pass

    def handle_msg(self, from_sock):
        """Process one JSON message from a logged‑in client."""
        # 1) receive safely
        try:
            raw = myrecv(from_sock)
        except (ConnectionResetError, OSError):
            self.logout(from_sock)
            return

        if not raw:
            self.logout(from_sock)
            return

        # 2) parse
        try:
            msg = json.loads(raw)
        except:
            return

        action = msg.get("action")
        name = self.logged_sock2name.get(from_sock)

        # === CONNECT ===
        if action == "connect":
            target = msg.get("target")
            if target == name:
                mysend(from_sock, json.dumps({"action":"connect","status":"self","msg":"Cannot connect to yourself"}))
                return

            if not self.group.is_member(target):
                mysend(from_sock, json.dumps({"action":"connect","status":"no-user","msg":f"{target} not online"}))
                return

            # perform group connect
            self.group.connect(name, target)
            # initiator gets success
            mysend(from_sock, json.dumps({"action":"connect","status":"success","msg":f"Connected to {target}"}))

            # inform all existing members (excluding initiator)
            members = self.group.list_me(name)
            for peer in members:
                if peer != name:
                    sock_peer = self.logged_name2sock[peer]
                    mysend(sock_peer, json.dumps({
                        "action":"connect",
                        "status":"request",
                        "from": name,
                        "msg": f"{name} has joined the chat."
                    }))
            return

        # === EXCHANGE ===
        if action == "exchange":
            text = msg.get("message","")
            # index message
            idx = self.indices.get(name)
            if idx:
                idx.add_msg_and_index(f"{name}: {text}")

            # broadcast to group members
            members = self.group.list_me(name)[1:]
            for peer in members:
                sock_peer = self.logged_name2sock.get(peer)
                if sock_peer:
                    mysend(sock_peer, json.dumps({
                        "action":"exchange",
                        "from": name,
                        "message": text
                    }))
            return

        # === DISCONNECT ===
        if action == "disconnect":
            # get members before removal
            members = self.group.list_me(name)
            # leave group
            self.group.disconnect(name)

            # broadcast leave to others
            for peer in members:
                if peer != name and peer in self.logged_name2sock:
                    sock_peer = self.logged_name2sock[peer]
                    mysend(sock_peer, json.dumps({
                        "action":"disconnect",
                        "from": name,
                        "msg": f"{name} has left the chat."
                    }))

            # if one left alone, notify
            if len(members) == 1:
                lone = members[0]
                sock_lone = self.logged_name2sock.get(lone)
                if sock_lone:
                    mysend(sock_lone, json.dumps({
                        "action":"disconnect",
                        "msg": "Everyone left, you are alone."
                    }))
            return

        # === LIST ===
        if action == "list":
            # compile "user: n_peers" list
            status = {}
            for user, sock in self.logged_name2sock.items():
                count = max(len(self.group.list_me(user)) - 1, 0)
                status[user] = count
            results = ", ".join(f"{u}:{status[u]}" for u in status)
            mysend(from_sock, json.dumps({"action":"list","results":results}))
            return

        # === POEM ===
        if action == "poem":
            tgt = msg.get("target","")
            try:
                num = int(tgt)
                poem = self.sonnet.get_poem(num)
            except:
                poem = []
            mysend(from_sock, json.dumps({"action":"poem","results":poem}))
            return

        # === TIME ===
        if action == "time":
            ctime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            mysend(from_sock, json.dumps({"action":"time","results":ctime}))
            return

        # === SEARCH ===
        if action == "search":
            term = msg.get("target","")
            idx = self.indices.get(name)
            if idx:
                res = idx.search(term)
            else:
                res = ""
            mysend(from_sock, json.dumps({"action":"search","results":res}))
            return

        # unknown action → ignore
        return

    def run(self):
        print("Server running on", SERVER)
        while True:
            try:
                read, _, _ = select.select(self.all_sockets, [], [])
            except Exception:
                continue

            # handle logged‑in clients
            for sock in list(self.logged_name2sock.values()):
                if sock in read:
                    try:
                        self.handle_msg(sock)
                    except Exception as e:
                        print("Error:", e)
                        self.logout(sock)

            # handle new clients (awaiting login)
            for sock in self.new_clients[:]:
                if sock in read:
                    try:
                        self.login(sock)
                    except Exception as e:
                        print("Login error:", e)
                        self.logout(sock)

            # accept brand new connections
            if self.server in read:
                sock_new, addr = self.server.accept()
                self.new_client(sock_new)


def main():
    server = Server()
    server.run()


if __name__ == "__main__":
    main()
