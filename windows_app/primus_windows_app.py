from __future__ import annotations

import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import BooleanVar, END, DISABLED, NORMAL, Tk, ttk, messagebox, Text
from tkinter.scrolledtext import ScrolledText
import traceback


PROJECT_ROOT = Path(__file__).resolve().parent.parent

def debug_log(msg: str) -> None:
    """Minimal debug logger for the Tk app."""
    try:
        with open(PROJECT_ROOT / "tk_debug.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def build_planner_prompt(user_prompt: str) -> str:
    base = (
        "You are my personal daily planner.\n"
        "Using bullet points with checkboxes in the form '- [ ] task', "
        "create a realistic, time-blocked plan for my day.\n"
        "Focus on priorities and breaks, and do NOT add extra chit-chat.\n\n"
        f"User request: {user_prompt.strip()}\n\n"
        "Return ONLY the plan."
    )
    return base


def extract_planner_summary(raw: str) -> str:
    """Strip backend/log spam and keep only the actual plan text."""
    if not raw:
        return ""

    # First, filter out obvious log / loader noise
    filtered: list[str] = []
    for ln in raw.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue

        # Timestamped log lines, e.g. "2025-12-25 22:55:54,861 [INFO] ..."
        if (
            len(stripped) > 20
            and stripped[0:4].isdigit()
            and stripped[4] == "-"
            and "[INFO]" in stripped
        ):
            continue

        # llama / loader / debug noise
        if (
            stripped.startswith("llama_model_loader:")
            or stripped.startswith("print_info:")
            or stripped.startswith("load:")
            or stripped.startswith("repack:")
            or stripped.startswith("llama_context:")
            or stripped.startswith("graph_reserve:")
            or stripped.startswith("CPU :")
            or stripped.startswith("Model metadata:")
            or stripped.startswith("Available chat formats")
            or stripped.startswith("Using gguf chat template")
            or stripped.startswith("Using chat ")
        ):
            continue

        filtered.append(ln)

    if not filtered:
        return raw.strip()

    lines = [ln.rstrip("\n") for ln in filtered]

    # Find first/last checkbox lines to cut off any prompt text around them
    checkbox_indices = [i for i, ln in enumerate(lines) if ln.strip().startswith("- [")]
    if checkbox_indices:
        first_idx = checkbox_indices[0]
        last_idx = checkbox_indices[-1]
        slice_lines = lines[first_idx : last_idx + 1]
    else:
        slice_lines = lines

    cleaned: list[str] = []
    for ln in slice_lines:
        s = ln.strip()
        if not s:
            continue

        # Skip obviously broken lines that are mostly multiple "- [" fragments
        # with no proper " - " separator text.
        if s.count("- [") > 1 and " - " not in s:
            continue

        cleaned.append(s)

    # Trim trailing junk until the last line looks like a real checkbox task
    while cleaned:
        last = cleaned[-1]
        if last.startswith("- [") and " - " in last and len(last) > 12:
            break
        cleaned.pop()

    if cleaned:
        return "\n".join(cleaned).strip()

    # Fallback if our filters were too strict
    return raw.strip()
    
def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    log_path = PROJECT_ROOT / "tk_errors.log"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                file=f,
            )
    except Exception:
        pass

threading.excepthook = _thread_excepthook

def log_thread_exception(context: str) -> None:
    """
    Log exceptions from background threads (planner, log write, etc.)
    into tk_errors.log so we can debug crashes that don't hit Tk's
    own callback error handler.
    """
    log_path = PROJECT_ROOT / "tk_errors.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== {context} ===\n")
            traceback.print_exc(file=f)
    except Exception:
        # Never let logging itself kill the app
        pass

def log_thread_exception(context: str) -> None:
    """
    Log exceptions from background threads (planner, log write, etc.)
    into planner_errors.log so we can debug crashes that don't hit Tk's
    own callback error handler.
    """
    log_path = PROJECT_ROOT / "planner_errors.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== {context} ===\n")
            traceback.print_exc(file=f)
    except Exception:
        # Never let logging itself kill the app
        pass

def append_chat_line(widget: ScrolledText, line: str) -> None:
    widget.configure(state=NORMAL)
    widget.insert(END, line + "\n")
    widget.see(END)
    widget.configure(state=DISABLED)


def build_command(message: str, session_id: str, use_rag: bool, rag_index: str) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        "primus_cli.py",
        "chat",
        message,
        "--session",
        session_id,
    ]
    if use_rag:
        cmd.append("--rag")
        if rag_index:
            cmd.extend(["--index", rag_index])
    return cmd


def run_cli_command(cmd: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    return proc.returncode == 0, stdout, stderr

def main() -> None:
    root = Tk()
    root.title("PRIMUS OS – Control Center")

        # --- Global Tk callback error handler: log to file + popup ---
    import traceback

    def tk_exception_handler(exc_type, exc_value, exc_tb):
        log_path = PROJECT_ROOT / "tk_errors.log"
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            # Last-resort: don’t crash if logging fails
            pass

        # Short message in a popup so you know something went wrong
        messagebox.showerror(
            "Tk error",
            f"{exc_type.__name__}: {exc_value}\n\nSee tk_errors.log for full details.",
        )

    # Tell Tkinter to use our handler for ALL callback exceptions
    root.report_callback_exception = tk_exception_handler

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # ------------------- Chat Tab ------------------- #
    chat_frame = ttk.Frame(notebook, padding=10)
    notebook.add(chat_frame, text="Chat")

    chat_frame.rowconfigure(0, weight=1)
    for col in range(4):
        chat_frame.columnconfigure(col, weight=1 if col < 3 else 0)
    chat_frame.columnconfigure(4, weight=0)

    transcript = ScrolledText(chat_frame, wrap="word", height=20, width=80, state=DISABLED)
    transcript.grid(row=0, column=0, columnspan=5, sticky="nsew", pady=(0, 8))

    ttk.Label(chat_frame, text="Session ID:").grid(row=1, column=0, sticky="w")
    session_var = ttk.Entry(chat_frame)
    session_var.insert(0, "cli")
    session_var.grid(row=1, column=1, sticky="we", padx=(4, 8))

    use_rag_var = BooleanVar(value=False)
    rag_check = ttk.Checkbutton(chat_frame, text="Use RAG", variable=use_rag_var)
    rag_check.grid(row=1, column=2, sticky="w")

    ttk.Label(chat_frame, text="RAG index:").grid(row=1, column=3, sticky="e")
    rag_index_var = ttk.Entry(chat_frame, width=12)
    rag_index_var.insert(0, "docs")
    rag_index_var.grid(row=1, column=4, sticky="we", padx=(4, 0))

    ttk.Label(chat_frame, text="Message:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    message_entry = ttk.Entry(chat_frame)
    message_entry.grid(row=2, column=1, columnspan=3, sticky="we", pady=(8, 0))

    buttons_frame = ttk.Frame(chat_frame)
    buttons_frame.grid(row=2, column=4, sticky="e", padx=(8, 0), pady=(8, 0))

    send_btn = ttk.Button(buttons_frame, text="Send")
    clear_btn = ttk.Button(buttons_frame, text="Clear Transcript")
    send_btn.grid(row=0, column=0, padx=(0, 4))
    clear_btn.grid(row=0, column=1)

    def set_send_enabled(enabled: bool) -> None:
        send_btn.state(["!disabled"] if enabled else ["disabled"])

    def handle_result(success: bool, stdout: str, stderr: str, user_text: str) -> None:
        set_send_enabled(True)
        if success:
            append_chat_line(transcript, f"User: {user_text}")
            if stdout:
                reply = stdout if len(stdout) < 4000 else stdout[:4000] + "...[truncated]"
                append_chat_line(transcript, f"Assistant: {reply}")
            else:
                append_chat_line(transcript, "Assistant: [no output]")
        else:
            err_msg = stderr or "Unknown error."
            append_chat_line(transcript, f"[ERROR] {err_msg}")
            messagebox.showerror("Chat failed", err_msg)

    def do_send() -> None:
        user_text = message_entry.get().strip()
        if not user_text:
            return

        session_id = session_var.get().strip() or "cli"
        use_rag = use_rag_var.get()
        rag_index = rag_index_var.get().strip() or "docs"

        set_send_enabled(False)

        def worker() -> None:
            cmd = build_command(user_text, session_id, use_rag, rag_index)
            success, stdout, stderr = run_cli_command(cmd)
            root.after(0, handle_result, success, stdout, stderr, user_text)

        threading.Thread(target=worker, daemon=True).start()

    def clear_transcript() -> None:
        transcript.configure(state=NORMAL)
        transcript.delete(1.0, END)
        transcript.configure(state=DISABLED)

    send_btn.configure(command=do_send)
    clear_btn.configure(command=clear_transcript)
    message_entry.bind("<Return>", lambda event: do_send())

    # ------------------- Captain's Log Tab ------------------- #
    log_frame = ttk.Frame(notebook, padding=10)
    notebook.add(log_frame, text="Captain's Log")

    log_frame.rowconfigure(0, weight=1)
    log_frame.columnconfigure(0, weight=1)
    log_frame.columnconfigure(1, weight=0)

    log_view = ScrolledText(log_frame, wrap="word", height=15, width=80, state=DISABLED)
    log_view.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

    ttk.Label(log_frame, text="New entry:").grid(row=1, column=0, sticky="w")
    entry_text = Text(log_frame, height=4, width=60)
    entry_text.grid(row=2, column=0, sticky="nsew", pady=(4, 4))
    log_frame.rowconfigure(2, weight=0)

    buttons_log = ttk.Frame(log_frame)
    buttons_log.grid(row=2, column=1, sticky="ne", padx=(8, 0))

    write_btn = ttk.Button(buttons_log, text="Write entry")
    refresh_btn = ttk.Button(buttons_log, text="Refresh")
    clear_log_btn = ttk.Button(buttons_log, text="Clear log")
    write_btn.grid(row=0, column=0, pady=(0, 4), sticky="ew")
    refresh_btn.grid(row=1, column=0, pady=(0, 4), sticky="ew")
    clear_log_btn.grid(row=2, column=0, sticky="ew")

    status_label = ttk.Label(log_frame, text="", foreground="gray")
    status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
    
    # Toggle: whether to have AI reflect on new entries
    ai_reflect_var = BooleanVar(value=False)
    ai_reflect_check = ttk.Checkbutton(
        log_frame,
        text="Ask AI to respond to new entries",
        variable=ai_reflect_var,
    )
    ai_reflect_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
    
    def set_log_buttons(enabled: bool) -> None:
        state = ["!disabled"] if enabled else ["disabled"]
        for btn in (write_btn, refresh_btn, clear_log_btn):
            btn.state(state)

    def update_log_view(content: str) -> None:
        log_view.configure(state=NORMAL)
        log_view.delete(1.0, END)
        log_view.insert(END, content + ("\n" if content else ""))
        log_view.configure(state=DISABLED)
        log_view.see(END)

    def handle_log_result(success: bool, stdout: str, stderr: str, status: str) -> None:
        set_log_buttons(True)
        if success:
            update_log_view(stdout)
            status_label.configure(text=status or "Operation completed.", foreground="green")
        else:
            err = stderr or stdout or "Unknown error"
            status_label.configure(text=err, foreground="red")

    def refresh_log() -> None:
        set_log_buttons(False)

        def worker() -> None:
            cmd = [sys.executable, "primus_cli.py", "cl", "read"]
            success, stdout, stderr = run_cli_command(cmd)
            root.after(0, handle_log_result, success, stdout, stderr, "Log refreshed.")

        threading.Thread(target=worker, daemon=True).start()

    def write_log_entry() -> None:
        text = entry_text.get("1.0", END).strip()
        if not text:
            status_label.configure(text="Please enter text to write.", foreground="red")
            return

        set_log_buttons(False)

        def worker() -> None:
            cmd = [sys.executable, "primus_cli.py", "cl", "write", text]
            success, stdout, stderr = run_cli_command(cmd)

            def after_write() -> None:
                set_log_buttons(True)
                if success:
                    status_label.configure(text="Entry written.", foreground="green")
                    entry_text.delete("1.0", END)
                    refresh_log()

                    # If AI reflection is enabled, fire it off in the background
                    if ai_reflect_var.get():
                        run_ai_reflection_async(text)
                else:
                    err = stderr or stdout or "Unknown error"
                    status_label.configure(text=err, foreground="red")

            root.after(0, after_write)

        threading.Thread(target=worker, daemon=True).start()

    def run_ai_reflection_async(entry_text: str) -> None:
        """Optionally ask the model to reflect on a journal entry and store it."""
        def worker() -> None:
            # 1) Ask the model for a short reflection
            prompt = (
                "You are my journaling assistant. "
                "I just wrote this entry in my personal Captain's Log:\n\n"
                f"{entry_text}\n\n"
                "Reply with ONE or TWO short sentences of helpful reflection or advice."
            )
            chat_cmd = [
                sys.executable,
                "primus_cli.py",
                "chat",
                prompt,
                "--session",
                "journal_assistant",
            ]
            ok1, out1, err1 = run_cli_command(chat_cmd)

            if not ok1 or not out1:
                # Don't fail loudly; just note it in the status label on the UI thread
                def notify_fail() -> None:
                    status_label.configure(
                        text="Entry saved, but AI reflection failed; see console.",
                        foreground="red",
                    )
                root.after(0, notify_fail)
                return

            reflection = out1.strip()
            if not reflection:
                return

            # 2) Save the reflection back into Captain's Log as a new entry
            log_cmd = [
                sys.executable,
                "primus_cli.py",
                "cl",
                "write",
                f"AI reflection: {reflection}",
            ]
            run_cli_command(log_cmd)

            # 3) Nudge the UI (optional but nice)
            def notify_ok() -> None:
                status_label.configure(
                    text="Entry + AI reflection written.",
                    foreground="green",
                )
                refresh_log()
            root.after(0, notify_ok)

        threading.Thread(target=worker, daemon=True).start()
    
    def clear_log() -> None:
        if not messagebox.askyesno("Confirm", "Clear all Captain's Log entries?"):
            return

        set_log_buttons(False)

        def worker() -> None:
            cmd = [sys.executable, "primus_cli.py", "cl", "clear"]
            success, stdout, stderr = run_cli_command(cmd)
            root.after(0, handle_log_result, success, stdout, stderr, "Log cleared.")
            if success:
                root.after(0, refresh_log)

        threading.Thread(target=worker, daemon=True).start()

    write_btn.configure(command=write_log_entry)
    refresh_btn.configure(command=refresh_log)
    clear_log_btn.configure(command=clear_log)

    # ------------------- Planner Tab ------------------- #
    planner_frame = ttk.Frame(notebook, padding=10)
    notebook.add(planner_frame, text="Planner")

    for col in range(2):
        planner_frame.columnconfigure(col, weight=1)
    planner_frame.rowconfigure(1, weight=1)
    planner_frame.rowconfigure(4, weight=1)

    ttk.Label(planner_frame, text="Planner prompt:").grid(row=0, column=0, columnspan=2, sticky="w")
    planner_prompt = Text(planner_frame, height=4, width=80)
    planner_prompt.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 8))

    run_planner_btn = ttk.Button(planner_frame, text="Run planner")
    run_planner_btn.grid(row=2, column=0, sticky="w")

    planner_status = ttk.Label(planner_frame, text="", foreground="gray")
    planner_status.grid(row=2, column=1, sticky="e")

    # Checkbox: save planner result to Captain's Log
    save_to_log_var = BooleanVar(value=True)
    save_to_log_check = ttk.Checkbutton(
        planner_frame,
        text="Save planner result to Captain's Log",
        variable=save_to_log_var,
    )
    save_to_log_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

    ttk.Label(planner_frame, text="Planner result:").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
    planner_output = ScrolledText(planner_frame, wrap="word", height=12, state=DISABLED)
    planner_output.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
    planner_frame.rowconfigure(5, weight=1)

    def set_planner_button(enabled: bool) -> None:
        run_planner_btn.state(["!disabled"] if enabled else ["disabled"])

    def update_planner_output(text: str) -> None:
        planner_output.configure(state=NORMAL)
        planner_output.delete(1.0, END)
        planner_output.insert(END, text + ("\n" if text else ""))
        planner_output.configure(state=DISABLED)
        planner_output.see(END)

    def handle_planner_result(success: bool, stdout: str, stderr: str) -> None:
        set_planner_button(True)

        if success and not stderr:
            debug_log(f"Planner stdout (first 200 chars): {stdout[:200]!r}")

            # Clean out loader / prompt spam before showing / logging
            plan_text = extract_planner_summary(stdout)
            if not plan_text:
                plan_text = stdout.strip()

            update_planner_output(plan_text)
            planner_status.configure(text="Planner finished.", foreground="green")

            # Optionally save to Captain's Log
            if save_to_log_var.get() and plan_text:
                def log_worker() -> None:
                    cmd = [
                        sys.executable,
                        "primus_cli.py",
                        "cl",
                        "write",
                        plan_text,
                    ]
                    ok, _out, _err = run_cli_command(cmd)
                    debug_log(f"Planner log write ok={ok}")

                    def after_log() -> None:
                        if not ok:
                            planner_status.configure(
                                text="Planner finished, but Captain's Log write failed; see console.",
                                foreground="red",
                            )

                    root.after(0, after_log)

                threading.Thread(target=log_worker, daemon=True).start()
        else:
            err = stderr or stdout or "Planner: CLI error; see console."
            planner_status.configure(text=err, foreground="red")
            debug_log(
                f"Planner error: success={success}, stderr={stderr!r}, stdout={stdout[:200]!r}"
            )

    def run_planner() -> None:
        prompt_text = planner_prompt.get("1.0", END).strip()
        if not prompt_text:
            planner_status.configure(text="Enter a prompt for the planner.", foreground="red")
            return

        set_planner_button(False)
        planner_status.configure(text="Running planner...", foreground="gray")

        def worker() -> None:
            try:
                planner_prompt_text = build_planner_prompt(prompt_text)
                cmd = [
                    sys.executable,
                    "primus_cli.py",
                    "chat",
                    planner_prompt_text,
                    "--session",
                    "daily_planner",
                ]
                debug_log(f"Planner cmd: {cmd!r}")
                success, stdout, stderr = run_cli_command(cmd)
            except Exception as exc:
                success, stdout, stderr = False, "", f"Planner internal error: {exc}"
                debug_log("Planner worker exception:\n" + traceback.format_exc())

            root.after(0, handle_planner_result, success, stdout, stderr)

        threading.Thread(target=worker, daemon=True).start()

    run_planner_btn.configure(command=run_planner)

    refresh_log()
    root.mainloop()


if __name__ == "__main__":
    main()
