from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, END, DISABLED, NORMAL, Tk, ttk, messagebox
from tkinter.scrolledtext import ScrolledText


PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def run_chat_command(message: str, session_id: str, use_rag: bool, rag_index: str) -> tuple[bool, str, str]:
    cmd = build_command(message, session_id, use_rag, rag_index)
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
    root.title("PRIMUS OS – Chat (v0.1)")

    content = ttk.Frame(root, padding=10)
    content.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    transcript = ScrolledText(content, wrap="word", height=20, width=80, state=DISABLED)
    transcript.grid(row=0, column=0, columnspan=4, sticky="nsew", pady=(0, 8))
    content.rowconfigure(0, weight=1)
    for col in range(4):
        content.columnconfigure(col, weight=1 if col < 3 else 0)

    ttk.Label(content, text="Session ID:").grid(row=1, column=0, sticky="w")
    session_var = ttk.Entry(content)
    session_var.insert(0, "cli")
    session_var.grid(row=1, column=1, sticky="we", padx=(4, 8))

    use_rag_var = BooleanVar(value=False)
    rag_check = ttk.Checkbutton(content, text="Use RAG", variable=use_rag_var)
    rag_check.grid(row=1, column=2, sticky="w")

    ttk.Label(content, text="RAG index:").grid(row=1, column=3, sticky="e")
    rag_index_var = ttk.Entry(content, width=12)
    rag_index_var.insert(0, "docs")
    rag_index_var.grid(row=1, column=4, sticky="we", padx=(4, 0))

    ttk.Label(content, text="Message:").grid(row=2, column=0, sticky="w", pady=(8, 0))
    message_entry = ttk.Entry(content)
    message_entry.grid(row=2, column=1, columnspan=3, sticky="we", pady=(8, 0))

    buttons_frame = ttk.Frame(content)
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
            success, stdout, stderr = run_chat_command(user_text, session_id, use_rag, rag_index)
            root.after(0, handle_result, success, stdout, stderr, user_text)

        threading.Thread(target=worker, daemon=True).start()

    def clear_transcript() -> None:
        transcript.configure(state=NORMAL)
        transcript.delete(1.0, END)
        transcript.configure(state=DISABLED)

    send_btn.configure(command=do_send)
    clear_btn.configure(command=clear_transcript)
    message_entry.bind("<Return>", lambda event: do_send())

    root.mainloop()


if __name__ == "__main__":
    main()
