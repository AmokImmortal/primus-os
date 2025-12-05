# create_captains_log_vault.py
# Location: C:\P.R.I.M.U.S OS\System\core\create_captains_log_vault.py

import os
import stat

VAULT_ROOT = r"C:\P.R.I.M.U.S OS\System\captains_log_vault"

def make_hidden(path: str):
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        FILE_ATTRIBUTE_SYSTEM = 0x04
        ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
    except Exception:
        pass

def create_captains_log_vault():
    if not os.path.exists(VAULT_ROOT):
        os.makedirs(VAULT_ROOT, exist_ok=True)
        make_hidden(VAULT_ROOT)
        try:
            os.chmod(VAULT_ROOT, stat.S_IREAD | stat.S_IWRITE)
        except Exception:
            pass

    subfolders = ["entries"]
    for f in subfolders:
        p = os.path.join(VAULT_ROOT, f)
        if not os.path.exists(p):
            os.makedirs(p, exist_ok=True)
            make_hidden(p)
            try:
                os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
            except Exception:
                pass

if __name__ == "__main__":
    create_captains_log_vault()