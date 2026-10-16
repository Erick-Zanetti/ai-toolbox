"""Regenerate docs/screenshots on Hyprland (uses hyprctl + grim).

  scripts/screenshots.sh   # all shots, cursor hidden
  /usr/bin/python3 -I scripts/screenshots.py docs/screenshots <palette|result|result-light|translate|settings>
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_toolbox import config, prompts
from ai_toolbox.ui.common import GLib, Adw

OUT, SHOT = sys.argv[1], sys.argv[2]
BORDER = 2
SAMPLE = "Hi guys, i think we should to move the meeting for tomorrow because the deploy didnt finished yet."

def capture(name, delay, before=None):
    def go():
        if before:
            before()
            GLib.timeout_add(500, lambda: (grab(name), False)[1])
        else:
            grab(name)
        return False
    GLib.timeout_add(delay, go)

def grab(name):
    from ai_toolbox.ui.common import Gtk
    for win in Gtk.Window.list_toplevels():
        win.set_can_target(False)  # no hover highlight under the pointer
    GLib.timeout_add(300, lambda: (_grab(name), False)[1])


def _grab(name):
    for c in json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True).stdout):
        if c["class"] == "dev.aitoolbox.AiToolbox":
            x, y = c["at"]; w, h = c["size"]
            subprocess.run(["grim", "-g", f"{x+BORDER},{y+BORDER} {w-2*BORDER}x{h-2*BORDER}", f"{OUT}/{name}.png"])
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{c["address"]}" }})'], capture_output=True)

cfg = config.load()
if SHOT == "palette":
    from ai_toolbox.ui import palette
    capture("palette", 1200)
    palette.show(cfg, SAMPLE)
elif SHOT in ("result", "result-light"):
    from ai_toolbox.ui import result
    cmd = cfg.commands["fix-spelling"]
    capture(SHOT, 7000)
    result.show(cmd.name, cmd.model, prompts.COMMAND_SYSTEM,
                lambda t: prompts.render(cmd.prompt, t, cfg.context), SAMPLE)
elif SHOT == "translate":
    from ai_toolbox.ui import translate
    capture("translate", 14000)
    translate.show(cfg, "Galera, esse bug do login tá me tirando do sério, mas hoje eu mato ele de vez.", contextual=True)
elif SHOT == "settings":
    from ai_toolbox.ui.common import run_window
    from ai_toolbox.ui.settings import Settings
    def build(app):
        s = Settings(app)
        def expand():
            s.stack.set_visible_child_name("commands")
            page = s.stack.get_child_by_name("commands")
            stack = [page]
            while stack:
                w = stack.pop()
                if isinstance(w, Adw.ExpanderRow):
                    w.set_expanded(True)
                    return
                child = w.get_last_child()
                while child:
                    stack.append(child)
                    child = child.get_prev_sibling()
        capture("settings", 1200, before=expand)
        return s.win
    run_window(build)
