"""
Entry point. Three modes:

  (default)         Global hotkey listener (Ctrl+Shift+D). Copy → hotkey → paste.
  --once            Read clipboard once, doctor, write back, exit.
  --prompt "text"   Doctor the given text directly, print the result.
                    Useful for headless/CI/WSL where clipboard/hotkeys don't work.
"""

import os
import sys
import threading

# Windows consoles default to the cp1252 codepage, which can't encode
# characters like the checkmark used in progress output below. Force UTF-8
# on stdout/stderr so those prints don't crash mid-run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pyperclip

from agent import doctor


HOTKEY = os.getenv("HOTKEY", "<ctrl>+<shift>+d")

_running = threading.Lock()


def _bar(char: str = "=") -> str:
    return char * 60


def _handle_clipboard() -> None:
    try:
        rough = pyperclip.paste()
    except Exception as e:
        print(f"[clipboard error] Could not read clipboard: {e}")
        return

    if not rough or not rough.strip():
        print("\n[clipboard] Empty. Copy a prompt first, then press the hotkey.\n")
        return

    print("\n" + _bar())
    print("[hotkey] Doctoring prompt from clipboard...")
    preview = rough.replace("\n", " ")[:120]
    print(f"[input] {preview}{'...' if len(rough) > 120 else ''}")
    print(_bar())

    traj = doctor(rough, verbose=True)

    if not traj.final_prompt.strip():
        print("[!] Final prompt was empty; leaving clipboard unchanged.")
        return

    try:
        pyperclip.copy(traj.final_prompt)
    except Exception as e:
        print(f"[clipboard error] Could not write result: {e}")
        return

    print(_bar())
    outcome = "converged" if traj.converged else f"stopped ({traj.stopped_reason})"
    print(f"[done] {len(traj.iterations)} iteration(s), {outcome}")
    print(f"[copied] Improved prompt on clipboard. Paste with Ctrl+V.")
    print(_bar() + "\n")


def _on_hotkey() -> None:
    if not _running.acquire(blocking=False):
        print("\n[busy] Already doctoring a prompt. Try again after it finishes.")
        return
    try:
        _handle_clipboard()
    finally:
        _running.release()


def _run_hotkey_loop() -> None:
    # Import pynput only in this function so headless environments that skip
    # hotkey mode don't crash at startup if pynput can't initialize.
    try:
        from pynput import keyboard
    except Exception as e:
        print(f"[error] Could not load pynput (needed for hotkey mode): {e}")
        print("Use `python main.py --once` or `python main.py --prompt '...'` instead.")
        sys.exit(1)

    print("PromptDoctor is running.")
    print("  1. Copy a prompt to your clipboard.")
    print("  2. Press the hotkey:  Ctrl + Shift + D")
    print("  3. Paste the improved prompt anywhere.\n")
    print("Press Ctrl+C in this terminal to quit.\n")

    try:
        with keyboard.GlobalHotKeys({HOTKEY: _on_hotkey}) as h:
            h.join()
    except KeyboardInterrupt:
        print("\nGoodbye.")


def _run_once_from_clipboard() -> None:
    _handle_clipboard()


def _run_from_arg(prompt_text: str) -> None:
    if not prompt_text.strip():
        print("[error] Empty --prompt string.")
        sys.exit(1)

    print(_bar())
    print("[--prompt mode] Doctoring the given string...")
    print(_bar())

    traj = doctor(prompt_text, verbose=True)

    print(_bar())
    print("FINAL PROMPT:")
    print(_bar())
    print(traj.final_prompt)
    print(_bar())


def _main() -> None:
    args = sys.argv[1:]
    if not args:
        _run_hotkey_loop()
    elif args[0] == "--once":
        _run_once_from_clipboard()
    elif args[0] == "--prompt" and len(args) >= 2:
        _run_from_arg(" ".join(args[1:]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    _main()
