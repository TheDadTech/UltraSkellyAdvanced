#!/usr/bin/env python3
"""Lightweight local setup/status UI; all root actions are narrowly allowlisted."""
import concurrent.futures
import curses
import json
import subprocess
import time

HELPER = "/usr/local/libexec/usa-system-helper"


def clean(text):
    return "".join(c if c.isprintable() else "?" for c in str(text))


def request(action, payload=None):
    args = ["sudo", "-n", HELPER, action]
    result = subprocess.run(args, input=json.dumps(payload) + "\n" if payload else None,
                            text=True, capture_output=True, timeout=55 if action == "console-wifi-scan" else 40, check=False)
    if result.returncode:
        # Never display command arguments or input containing a password.
        raise RuntimeError(clean(result.stderr.strip() or "Network request failed")[:180])
    return json.loads(result.stdout)


def screen_lines(status, message=""):
    lines = ["ULTRASKELLYADVANCED / NETWORK SETUP", "Experimental 0.30.1-beta1", "",
             clean(status.get("hardware", "Starting network services...")), ""]
    for kind, label in [("ethernet", "Ethernet"), ("wifi", "Wi-Fi")]:
        interfaces = [i for i in status.get("interfaces", []) if i["type"] == kind]
        value = "; ".join(clean(i["name"] + ": " + (
            ", ".join(i["addresses"]) if i["connected"] else i["state"])) for i in interfaces)
        lines.append(f"{label}: {value or 'not available / waiting'}")
    lines += [""]
    if status.get("connected"):
        lines += ["CONNECTED - CONTINUE ON YOUR PHONE OR COMPUTER", "",
                  "On a device connected to the same home network, open:",
                  "  " + status["dashboard_url"], "  " + status["hostname_url"], "",
                  "Finish prop pairing and USA setup in your web browser.",
                  "You may leave this monitor connected. No login is needed."]
    else:
        lines += ["CONNECT TO YOUR HOME NETWORK", "",
                  "Plug Ethernet into your router, or press W for Wi-Fi setup."]
        if status.get("hotspot_active"):
            lines += ["", "Or use a phone to join UltraSkellyAdvanced-Setup",
                      "Password: dadtech1", "Then open http://192.168.4.1"]
        else:
            lines += ["", "Setup hotspot unavailable / retrying.",
                      "A support report is being saved automatically."]
    if message:
        lines += ["", clean(message)]
    lines += ["", "[W] Wi-Fi setup   [D] Support report information"]
    return lines


def draw(screen, lines, input_mode=False):
    screen.erase()
    height, width = screen.getmaxyx()
    top = max(0, (height - len(lines)) // 2)
    left = max(1, (width - min(90, width - 2)) // 2)
    for row, line in enumerate(lines[:max(0, height - 1)]):
        try:
            screen.addnstr(top + row, left, clean(line), max(0, width - left - 1),
                           curses.A_BOLD if row == 0 else curses.A_NORMAL)
        except curses.error:
            pass
    screen.refresh()


def run_ui(screen):
    curses.curs_set(0)
    screen.keypad(True)
    screen.timeout(150)
    status, message = {}, ""
    view, ssid, password, focus = "status", "", "", 0
    networks, selected = [], 0
    future, job, next_poll = None, "", 0
    want_scan = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        while True:
            now = time.monotonic()
            if future is not None and future.done():
                try:
                    result = future.result()
                    if job == "status":
                        status = result
                        if status.get("connected"):
                            password = ""
                            view = "status"
                    elif job == "scan":
                        networks = result.get("networks", [])
                        selected = 0
                        view = "choose" if networks else "form"
                        message = "Select a network, or press M to enter its name."
                    else:
                        password = ""
                        view = "status"
                        message = "Connecting; failed home Wi-Fi returns to the setup hotspot."
                except Exception as exc:
                    # request() errors contain no stdin or password-bearing argv.
                    message = clean(str(exc))[:180] if isinstance(exc, RuntimeError) else "Network request unavailable; retry shortly."
                    if job != "status":
                        password = ""
                        view = "status"
                future, job, next_poll = None, "", now + 4
            if future is None and want_scan:
                want_scan = False
                if status.get("setup_complete"):
                    message = "Setup is complete. Change Wi-Fi from the dashboard."
                else:
                    job, view, message = "scan", "waiting", "Scanning Wi-Fi; the hotspot may pause briefly."
                    future = pool.submit(request, "console-wifi-scan")
            if future is None and now >= next_poll and view == "status":
                job = "status"
                future = pool.submit(request, "console-network-status")
            if view == "choose":
                lines = ["CHOOSE YOUR HOME WI-FI", "", message, ""]
                # Limit the view so all controls fit on low-resolution displays.
                for index, item in enumerate(networks[:8]):
                    lines.append(("> " if index == selected else "  ") + clean(item["ssid"]))
                lines += ["", "Up/Down: select   Enter: choose   M: manual   Esc: cancel"]
            elif view == "form":
                lines = ["CONNECT TO HOME WI-FI", "", "Network name:",
                         ("> " if focus == 0 else "  ") + clean(ssid), "", "Password:",
                         ("> " if focus == 1 else "  ") + "*" * min(len(password), 50), "",
                         "Tab: switch field   Enter: connect   Esc: cancel", "", message]
            else:
                lines = screen_lines(status, message)
            draw(screen, lines)
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            if key == "\x1b":
                password, view, message = "", "status", ""
                continue
            if view == "status":
                if str(key).lower() == "d":
                    message = "Support: save USA-BETA-DIAGNOSTICS.txt from the SD card after a safe shutdown."
                elif str(key).lower() == "w":
                    want_scan = True
                    continue
            elif view == "choose":
                if key == curses.KEY_UP:
                    selected = max(0, selected - 1)
                elif key == curses.KEY_DOWN:
                    selected = min(min(8, len(networks)) - 1, selected + 1)
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    ssid, password, focus, view = networks[selected]["ssid"], "", 1, "form"
                    message = "Enter your home Wi-Fi password."
                elif str(key).lower() == "m":
                    ssid, password, focus, view = "", "", 0, "form"
            elif view == "form":
                if key == "\t":
                    focus = 1 - focus
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    if not ssid or len(password) < 8:
                        message = "Enter a network name and password of at least 8 characters."
                    else:
                        job, view = "connect", "waiting"
                        future = pool.submit(request, "console-wifi-connect", {"ssid": ssid, "password": password})
                        password = ""
                        message = "Connecting to home Wi-Fi..."
                elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if focus == 0: ssid = ssid[:-1]
                    else: password = password[:-1]
                elif isinstance(key, str) and key.isprintable():
                    if focus == 0 and len((ssid + key).encode("utf-8")) <= 32: ssid += key
                    elif focus == 1 and len(password) < 64: password += key


if __name__ == "__main__":
    try:
        curses.wrapper(run_ui)
    except curses.error:
        # Keep useful output when terminal capabilities are unavailable.
        while True:
            try:
                print("\033[2J\033[H" + "\n".join(screen_lines(request("console-network-status"))), flush=True)
            except Exception:
                print("USA network status unavailable. Diagnostic capture continues.", flush=True)
            time.sleep(10)
