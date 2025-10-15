#!/usr/bin/env python3
"""
ProText - a small terminal text editor (minimal alternative to vim/nano)
Short executable name: protext (Procyon Text)

Features (minimal):
- Open and edit a file passed as argument
- Save with Ctrl-S, Quit with Ctrl-C
- Arrow key navigation, backspace, insert text
- Status bar showing filename and messages

This is intentionally small and educational. Use a full editor for heavy tasks.
"""

import curses
import sys
import os
import argparse
import termios

VERSION = "0.1"
DEVELOPER = "Gautham Nair"
GITHUB_PROFILE = "https://github.com/gauthamnair2005"

class Buffer:
    def __init__(self, filename=None):
        self.filename = filename
        self.lines = [""]
        self.modified = False
        self.readonly = False
        if filename and os.path.exists(filename):
            with open(filename, "r", encoding="utf-8", errors="replace") as f:
                self.lines = [line.rstrip('\n') for line in f]
            if not self.lines:
                self.lines = [""]
            try:
                if not os.access(filename, os.W_OK):
                    self.readonly = True
            except Exception:
                self.readonly = False

    def save(self):
        if not self.filename:
            return False, "No filename"
        if self.readonly:
            return False, "File is read-only"
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                for line in self.lines:
                    f.write(line + "\n")
            self.modified = False
            return True, "Saved"
        except Exception as e:
            return False, str(e)


class Editor:
    def __init__(self, stdscr, buffer: Buffer):
        self.stdscr = stdscr
        self.buf = buffer
        self.cy = 0
        self.cx = 0
        self.top = 0
        self.left = 0
        self.msg = "ProText 0.1 (Ctrl-S save, Ctrl-C quit)"
        self.last_search = None
        self.search_results = []
        self.replace_confirm_all = False

    def refresh(self):
        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        text_h = h - 1
        for i in range(text_h):
            lineno = self.top + i
            if lineno >= len(self.buf.lines):
                break
            line = self.buf.lines[lineno][self.left:self.left + w - 1]
            try:
                self.stdscr.addstr(i, 0, line)
            except curses.error:
                pass
        # status bar
        status = f" {os.path.basename(self.buf.filename) if self.buf.filename else '[No Name]'} - {len(self.buf.lines)} lines "
        if self.buf.modified:
            status += "(modified) "
        status = status.ljust(w - 1)[:w - 1]
        try:
            self.stdscr.addstr(h - 1, 0, status, curses.A_REVERSE)
        except curses.error:
            pass
        # message overlay to right
        if self.msg:
            msg = self.msg[:w - 1]
            try:
                self.stdscr.addstr(h - 1, 0, msg, curses.A_REVERSE)
            except curses.error:
                pass
        # place cursor
        scr_y = self.cy - self.top
        scr_x = self.cx - self.left
        if 0 <= scr_y < text_h and 0 <= scr_x < w - 1:
            try:
                self.stdscr.move(scr_y, scr_x)
            except curses.error:
                pass
        self.stdscr.refresh()

    def run(self):
        # use cbreak so Ctrl-C and other signals are delivered
        curses.cbreak()
        self.stdscr.keypad(True)
        curses.curs_set(1)
        while True:
            self.refresh()
            ch = self.stdscr.get_wch()
            if isinstance(ch, str):
                # control keys
                if ch == '\x11':  # Ctrl-Q
                    if self.buf.modified:
                        ok = self.confirm_prompt("Exit without saving? (y/n)")
                        if ok:
                            break
                        else:
                            self.msg = "Exit cancelled"
                            continue
                    else:
                        ok = self.confirm_prompt("Quit? (y/n)")
                        if ok:
                            break
                        else:
                            self.msg = "Quit cancelled"
                            continue
                elif ch == '\x13':  # Ctrl-S
                    if not self.buf.filename:
                        fn = self.prompt_input("Save as:")
                        if fn is None or fn == "":
                            self.msg = "Save cancelled"
                            continue
                        self.buf.filename = fn
                    ok, m = self.buf.save()
                    self.msg = m
                elif ch == '\x08' or ch == '\x7f':  # backspace
                    self.backspace()
                elif ch == '\n':
                    self.insert_newline()
                elif ch == '\x03':  # Ctrl-C
                    # KeyboardInterrupt like behavior
                    raise KeyboardInterrupt()
                elif ch in ('q', 'Q'):
                    # treat plain q/Q as quit (ask if modified)
                    if self.buf.modified:
                        ok = self.confirm_prompt("Exit without saving? (y/n)")
                        if ok:
                            break
                        else:
                            self.msg = "Exit cancelled"
                            continue
                    else:
                        break
                elif ch == '\x06':  # Ctrl-F - find
                    term = self.prompt_input("Find:")
                    if term:
                        found = self.find(term)
                        if found:
                            self.msg = f"Found '{term}'"
                        else:
                            self.msg = f"'{term}' not found"
                elif ch == '\x12':  # Ctrl-R - replace
                    find_term = self.prompt_input("Replace - find:")
                    if find_term:
                        replace_term = self.prompt_input("Replace - with:")
                        if replace_term is None:
                            self.msg = "Replace cancelled"
                        else:
                            ans = self.prompt_input("Replace all occurrences? (y/n):")
                            if ans and ans.lower().startswith('y'):
                                count = self.replace_all(find_term, replace_term)
                                self.msg = f"Replaced {count} occurrences"
                            else:
                                self.msg = "Replace cancelled"
                else:
                    # printable
                    if ord(ch) >= 32:
                        self.insert_char(ch)
            else:
                # special keys
                if ch == curses.KEY_LEFT:
                    self.move_left()
                elif ch == curses.KEY_RIGHT:
                    self.move_right()
                elif ch == curses.KEY_UP:
                    self.move_up()
                elif ch == curses.KEY_DOWN:
                    self.move_down()
                elif ch == curses.KEY_BACKSPACE:
                    self.backspace()
                elif ch == curses.KEY_DC:  # delete
                    self.delete_char()
                elif ch == curses.KEY_HOME:
                    self.cx = 0
                elif ch == curses.KEY_END:
                    self.cx = len(self.buf.lines[self.cy])
                elif ch == curses.KEY_PPAGE or ch == curses.KEY_NPAGE:
                    # page up/down basic
                    h, _ = self.stdscr.getmaxyx()
                    delta = h - 2
                    if ch == curses.KEY_PPAGE:
                        self.cy = max(0, self.cy - delta)
                    else:
                        self.cy = min(len(self.buf.lines) - 1, self.cy + delta)
                    self.ensure_cursor_visible()

    # editing operations
    def ensure_cursor_visible(self):
        h, w = self.stdscr.getmaxyx()
        text_h = h - 1
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + text_h:
            self.top = self.cy - text_h + 1
        if self.cx < self.left:
            self.left = self.cx
        elif self.cx >= self.left + w - 1:
            self.left = self.cx - w + 2

    # small prompt helper shown on status line to collect simple input
    def prompt_input(self, prompt, initial=""):
        h, w = self.stdscr.getmaxyx()
        curses.curs_set(1)
        buf = list(initial)
        pos = len(buf)
        while True:
            # draw prompt
            self.stdscr.move(h - 1, 0)
            self.stdscr.clrtoeol()
            disp = (prompt + " " + ''.join(buf))[:w - 1]
            try:
                self.stdscr.addstr(h - 1, 0, disp, curses.A_REVERSE)
            except curses.error:
                pass
            self.stdscr.move(h - 1, min(len(prompt) + 1 + pos, w - 2))
            self.stdscr.refresh()
            ch = self.stdscr.get_wch()
            if isinstance(ch, str):
                if ch == '\n':
                    return ''.join(buf)
                elif ch == '\x1b':
                    return None
                elif ch == '\x7f' or ch == '\x08':
                    if pos > 0:
                        buf.pop(pos - 1)
                        pos -= 1
                else:
                    if ord(ch) >= 32:
                        buf.insert(pos, ch)
                        pos += 1
            else:
                if ch == curses.KEY_LEFT and pos > 0:
                    pos -= 1
                elif ch == curses.KEY_RIGHT and pos < len(buf):
                    pos += 1

    def confirm_prompt(self, prompt):
        ans = self.prompt_input(prompt, "n")
        if ans is None:
            return False
        return ans.lower().strip().startswith('y')

    def find(self, term):
        # search from current cursor forward, wrap around
        for y in range(self.cy, len(self.buf.lines)):
            x = self.buf.lines[y].find(term, self.cx if y == self.cy else 0)
            if x != -1:
                self.cy = y
                self.cx = x
                self.ensure_cursor_visible()
                self.last_search = term
                return True
        for y in range(0, self.cy):
            x = self.buf.lines[y].find(term)
            if x != -1:
                self.cy = y
                self.cx = x
                self.ensure_cursor_visible()
                self.last_search = term
                return True
        return False

    def replace_all(self, find_term, replace_term):
        count = 0
        for i in range(len(self.buf.lines)):
            line = self.buf.lines[i]
            if find_term in line:
                new = line.replace(find_term, replace_term)
                count += line.count(find_term)
                self.buf.lines[i] = new
        if count > 0:
            self.buf.modified = True
        return count

    def move_left(self):
        if self.cx > 0:
            self.cx -= 1
        elif self.cy > 0:
            self.cy -= 1
            self.cx = len(self.buf.lines[self.cy])
        self.ensure_cursor_visible()

    def move_right(self):
        if self.cx < len(self.buf.lines[self.cy]):
            self.cx += 1
        elif self.cy < len(self.buf.lines) - 1:
            self.cy += 1
            self.cx = 0
        self.ensure_cursor_visible()

    def move_up(self):
        if self.cy > 0:
            self.cy -= 1
            self.cx = min(self.cx, len(self.buf.lines[self.cy]))
        self.ensure_cursor_visible()

    def move_down(self):
        if self.cy < len(self.buf.lines) - 1:
            self.cy += 1
            self.cx = min(self.cx, len(self.buf.lines[self.cy]))
        self.ensure_cursor_visible()

    def insert_char(self, ch):
        line = self.buf.lines[self.cy]
        self.buf.lines[self.cy] = line[:self.cx] + ch + line[self.cx:]
        self.cx += 1
        self.buf.modified = True

    def backspace(self):
        if self.cx > 0:
            line = self.buf.lines[self.cy]
            self.buf.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
            self.cx -= 1
            self.buf.modified = True
        elif self.cy > 0:
            prev = self.buf.lines[self.cy - 1]
            cur = self.buf.lines.pop(self.cy)
            self.cy -= 1
            self.cx = len(prev)
            self.buf.lines[self.cy] = prev + cur
            self.buf.modified = True
            self.ensure_cursor_visible()

    def insert_newline(self):
        line = self.buf.lines[self.cy]
        left = line[:self.cx]
        right = line[self.cx:]
        self.buf.lines[self.cy] = left
        self.buf.lines.insert(self.cy + 1, right)
        self.cy += 1
        self.cx = 0
        self.buf.modified = True
        self.ensure_cursor_visible()

    def delete_char(self):
        line = self.buf.lines[self.cy]
        if self.cx < len(line):
            self.buf.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
            self.buf.modified = True
        elif self.cy < len(self.buf.lines) - 1:
            nxt = self.buf.lines.pop(self.cy + 1)
            self.buf.lines[self.cy] = line + nxt
            self.buf.modified = True


def main(argv=None):
    parser = argparse.ArgumentParser(prog="protext")
    parser.add_argument("file", nargs="?", help="File to open")
    parser.add_argument("-v", "--version", action="store_true", help="Show version")
    args = parser.parse_args(argv)
    if args.version:
        print(f"ProText {VERSION}")
        return
    buf = Buffer(args.file)
    # disable software flow control (IXON) so Ctrl-S/Ctrl-Q aren't intercepted by terminal
    fd = sys.stdin.fileno()
    orig_attrs = None
    try:
        try:
            orig_attrs = termios.tcgetattr(fd)
            new_attrs = list(orig_attrs)
            # clear IXON in iflag (index 0)
            new_attrs[0] = new_attrs[0] & ~termios.IXON
            termios.tcsetattr(fd, termios.TCSANOW, new_attrs)
        except Exception:
            orig_attrs = None
        try:
            curses.wrapper(lambda stdscr: Editor(stdscr, buf).run())
        except KeyboardInterrupt:
            # user pressed Ctrl-C; exit gracefully
            pass
    finally:
        if orig_attrs is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, orig_attrs)
            except Exception:
                pass

if __name__ == "__main__":
    main()
