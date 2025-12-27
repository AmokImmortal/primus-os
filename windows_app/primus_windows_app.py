from __future__ import annotations

import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import BooleanVar, END, DISABLED, NORMAL, Tk, ttk, messagebox, Text
from tkinter.scrolledtext import ScrolledText


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def debug_log(msg: str) -> None:
    """Append small debug messages to tk_debug.log."""
    try:
        with open(PROJECT_ROOT / "tk_debug.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


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


def append_chat_line(widget: ScrolledText, line: str) -> None:
    widget.configure(state=NORMAL)
    widget.insert(END, line + "\n")
    widget.see(END)
    widget.configure(state=DISABLED)


def extract_planner_summary(raw: str) -> str:
    """Strip backend/log spam and keep only the actual plan text."""
    if not raw:
        return ""

    debug_log(f"Planner raw stdout (first 200 chars): {raw[:200]!r}")

    filtered: list[str] = []
    for ln in raw.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue

        if (
            len(stripped) > 20
            and stripped[0:4].isdigit()
            and stripped[4] == "-"
            and "[INFO]" in stripped
        ):
            continue

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
            or stripped.startswith("You are my personal daily planner")
            or stripped.startswith("[Subchat:")
            or stripped.startswith("User:")
            or stripped.startswith("Assistant:")
        ):
            continue

        filtered.append(ln)

    if not filtered:
        return raw.strip()

    lines = [ln.rstrip("\n") for ln in filtered]
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
        if s.count("- [") > 1 and " - " not in s:
            continue
        cleaned.append(s)

    while cleaned:
        last = cleaned[-1]
        if last.startswith("- [") and " - " in last and len(last) > 12:
            break
        cleaned.pop()

    if cleaned:
        return "\n".join(cleaned).strip()

    return raw.strip()


def extract_chat_reply(raw: str) -> str:
    """Strip obvious backend/log noise and keep the assistant reply text."""
    if not raw:
        return ""
    filtered: list[str] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        if (
            len(s) > 20
            and s[:4].isdigit()
            and s[4] == "-"
            and "[INFO]" in s
        ):
            continue
        if (
            s.startswith("llama_model_loader:")
            or s.startswith("print_info:")
            or s.startswith("load:")
            or s.startswith("repack:")
            or s.startswith("llama_context:")
            or s.startswith("graph_reserve:")
            or s.startswith("CPU :")
            or s.startswith("Model metadata:")
            or s.startswith("Available chat formats")
            or s.startswith("Using gguf chat template")
            or s.startswith("Using chat ")
        ):
            continue
        filtered.append(ln.rstrip("\n"))
    if not filtered:
        return raw.strip()
    return "\n".join(filtered).strip()


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


def main() -> None:
    root = Tk()
    root.title("PRIMUS OS – Control Center")

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

    def handle_chat_result(success: bool, stdout: str, stderr: str, user_text: str) -> None:
        set_send_enabled(True)
        if success:
            append_chat_line(transcript, f"User: {user_text}")
            reply = stdout if stdout else "[no output]"
            if len(reply) > 4000:
                reply = reply[:4000] + "...[truncated]"
            append_chat_line(transcript, f"Assistant: {reply}")
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
            try:
                cmd = [
                    sys.executable,
                    "primus_cli.py",
                    "chat",
                    user_text,
                    "--session",
                    session_id,
                ]
                if use_rag:
                    cmd.append("--rag")
                    if rag_index:
                        cmd.extend(["--index", rag_index])
                success, stdout, stderr = run_cli_command(cmd)
                root.after(0, handle_chat_result, success, stdout, stderr, user_text)
            except Exception:
                tb = traceback.format_exc()
                debug_log(tb)
                root.after(
                    0,
                    handle_chat_result,
                    False,
                    "",
                    "Chat crashed; see tk_debug.log",
                    user_text,
                )

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

    log_ai_var = BooleanVar(value=False)
    log_ai_check = ttk.Checkbutton(
        log_frame,
        text="Use AI assistant for new entries",
        variable=log_ai_var,
    )
    log_ai_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

    status_label = ttk.Label(log_frame, text="", foreground="gray")
    status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

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
            try:
                cmd = [sys.executable, "primus_cli.py", "cl", "read"]
                success, stdout, stderr = run_cli_command(cmd)
                root.after(0, handle_log_result, success, stdout, stderr, "Log refreshed.")
            except Exception:
                tb = traceback.format_exc()
                debug_log(tb)
                root.after(
                    0,
                    handle_log_result,
                    False,
                    "",
                    "Captain's Log refresh crashed; see tk_debug.log",
                    "",
                )

        threading.Thread(target=worker, daemon=True).start()

    def write_log_entry() -> None:
        text = entry_text.get("1.0", END).strip()
        if not text:
            messagebox.showinfo("Captain's Log", "Please enter some text before writing to the log.")
            return

        set_log_buttons(False)

        def worker() -> None:
            if not log_ai_var.get():
                try:
                    cmd = [sys.executable, "primus_cli.py", "cl", "write", text]
                    success, stdout, stderr = run_cli_command(cmd)
                    root.after(0, handle_log_result, success, stdout, stderr, "Entry written.")
                    if success:
                        root.after(0, lambda: entry_text.delete("1.0", END))
                        root.after(0, refresh_log)
                except Exception:
                    tb = traceback.format_exc()
                    debug_log(tb)
                    root.after(
                        0,
                        handle_log_result,
                        False,
                        "",
                        "Captain's Log write crashed; see tk_debug.log",
                        "",
                    )
                return

            # AI-assisted path
            try:
                chat_cmd = [
                    sys.executable,
                    "primus_cli.py",
                    "chat",
                    text,
                    "--session",
                    "captains_log_ai",
                ]
                chat_ok, chat_out, chat_err = run_cli_command(chat_cmd)
                if not chat_ok:
                    debug_log(f"Captain's Log AI chat failed: err={chat_err!r}, out={chat_out!r}")
                    root.after(
                        0,
                        handle_log_result,
                        False,
                        chat_out,
                        chat_err or "AI assistant failed; see console.",
                        "",
                    )
                    return

                assistant_reply = extract_chat_reply(chat_out)
                if not assistant_reply:
                    assistant_reply = chat_out.strip() or "[no assistant reply]"
                combined = f"User: {text}\nAssistant: {assistant_reply}"
                write_cmd = [sys.executable, "primus_cli.py", "cl", "write", combined]
                write_ok, write_out, write_err = run_cli_command(write_cmd)
                debug_log(f"Captain's Log AI write ok={write_ok}, err={write_err!r}")

                def after_ai_write() -> None:
                    if write_ok:
                        handle_log_result(True, write_out, write_err, "Entry written with AI assistant.")
                        entry_text.delete("1.0", END)
                        refresh_log()
                    else:
                        handle_log_result(
                            False,
                            write_out,
                            write_err or "Captain's Log write failed; see console.",
                            "",
                        )

                root.after(0, after_ai_write)
            except Exception:
                tb = traceback.format_exc()
                debug_log(tb)
                root.after(
                    0,
                    handle_log_result,
                    False,
                    "",
                    "Captain's Log AI write crashed; see tk_debug.log",
                    "",
                )

        threading.Thread(target=worker, daemon=True).start()

    def clear_log() -> None:
        if not messagebox.askyesno("Confirm", "Clear all Captain's Log entries?"):
            return

        set_log_buttons(False)

        def worker() -> None:
            try:
                cmd = [sys.executable, "primus_cli.py", "cl", "clear"]
                success, stdout, stderr = run_cli_command(cmd)
                root.after(0, handle_log_result, success, stdout, stderr, "Log cleared.")
                if success:
                    root.after(0, refresh_log)
            except Exception:
                tb = traceback.format_exc()
                debug_log(tb)
                root.after(
                    0,
                    handle_log_result,
                    False,
                    "",
                    "Captain's Log clear crashed; see tk_debug.log",
                    "",
                )

        threading.Thread(target=worker, daemon=True).start()

    write_btn.configure(command=write_log_entry)
    refresh_btn.configure(command=refresh_log)
    clear_log_btn.configure(command=clear_log)

    # ------------------- Planner Tab ------------------- #
    planner_frame = ttk.Frame(notebook, padding=10)
    notebook.add(planner_frame, text="Planner")

    for col in range(3):
        planner_frame.columnconfigure(col, weight=1)
    planner_frame.rowconfigure(1, weight=1)
    planner_frame.rowconfigure(4, weight=1)

    ttk.Label(planner_frame, text="Planner prompt:").grid(row=0, column=0, columnspan=3, sticky="w")
    planner_prompt = Text(planner_frame, height=4, width=80)
    planner_prompt.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(4, 8))

    run_planner_btn = ttk.Button(planner_frame, text="Run planner")
    run_planner_btn.grid(row=2, column=0, sticky="w")

    save_plan_var = BooleanVar(value=True)
    save_check = ttk.Checkbutton(
        planner_frame,
        text="Save planner result to Captain's Log",
        variable=save_plan_var,
    )
    save_check.grid(row=2, column=1, sticky="w", padx=(12, 0))

    planner_status = ttk.Label(planner_frame, text="", foreground="gray")
    planner_status.grid(row=2, column=2, sticky="e")

    ttk.Label(planner_frame, text="Planner result:").grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
    planner_output = ScrolledText(planner_frame, wrap="word", height=12, state=DISABLED)
    planner_output.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(4, 0))
    planner_frame.rowconfigure(4, weight=1)

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
        if not success:
            err = stderr or stdout or "Planner: CLI error; see console."
            planner_status.configure(text=err, foreground="red")
            debug_log(f"Planner error: success={success}, stderr={stderr!r}, stdout={stdout[:200]!r}")
            return

        debug_log(f"Planner stdout (first 200 chars): {stdout[:200]!r}")
        plan_text = extract_planner_summary(stdout)
        display_text = plan_text or (stdout.strip() if stdout.strip() else "[no output from planner]")
        update_planner_output(display_text)
        planner_status.configure(text="Planner finished.", foreground="green")

        if save_plan_var.get() and plan_text:
            def log_worker() -> None:
                try:
                    cmd = [
                        sys.executable,
                        "primus_cli.py",
                        "cl",
                        "write",
                        plan_text,
                    ]
                    ok, _out, _err = run_cli_command(cmd)
                    debug_log(f"Planner log write ok={ok}, err={_err!r}")

                    def after_log() -> None:
                        if not ok:
                            planner_status.configure(
                                text="Planner finished, but Captain's Log write failed; see console.",
                                foreground="red",
                            )

                    root.after(0, after_log)
                except Exception:
                    tb = traceback.format_exc()
                    debug_log(tb)

                    def _fail() -> None:
                        planner_status.configure(
                            text="Planner crashed while saving to Captain's Log; see tk_debug.log",
                            foreground="red",
                        )

                    root.after(0, _fail)

            threading.Thread(target=log_worker, daemon=True).start()

    def run_planner() -> None:
        prompt_text = planner_prompt.get("1.0", END).strip()
        if not prompt_text:
            planner_status.configure(text="Enter a prompt for the planner.", foreground="red")
            return

        set_planner_button(False)
        planner_status.configure(text="Running planner...", foreground="gray")
        update_planner_output("")

        def worker() -> None:
            try:
                full_prompt = build_planner_prompt(prompt_text)
                cmd = [
                    sys.executable,
                    "primus_cli.py",
                    "subchat",
                    "run",
                    "--id",
                    "daily_planner",
                    full_prompt,
                ]
                success, stdout, stderr = run_cli_command(cmd)
            except Exception as e:
                debug_log(f"Planner worker exception: {e!r}")
                debug_log(traceback.format_exc())
                success, stdout, stderr = False, "", str(e)

            root.after(0, handle_planner_result, success, stdout, stderr)

        threading.Thread(target=worker, daemon=True).start()

    run_planner_btn.configure(command=run_planner)

    refresh_log()
    root.mainloop()


if __name__ == "__main__":
    main()
