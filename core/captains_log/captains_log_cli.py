import argparse
from .captains_log_manager import save_entry, load_entry, list_entries


def main():
    parser = argparse.ArgumentParser(description="Captain's Log CLI")
    sub = parser.add_subparsers(dest="command")

    # ---------------------------
    # create entry
    # ---------------------------
    c = sub.add_parser("create", help="Create a new Captain's Log entry")
    c.add_argument("--password", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--content", required=True)

    # ---------------------------
    # read entry
    # ---------------------------
    r = sub.add_parser("read", help="Read an entry")
    r.add_argument("--password", required=True)
    r.add_argument("--file", required=True)

    # ---------------------------
    # list entries
    # ---------------------------
    sub.add_parser("list", help="List all entries")

    args = parser.parse_args()

    if args.command == "create":
        filename = save_entry(
            password=args.password,
            title=args.title,
            content=args.content
        )
        print(f"Entry saved: {filename}")

    elif args.command == "read":
        data = load_entry(args.password, args.file)
        print("\n--- CAPTAIN'S LOG ENTRY ---")
        print(f"Title: {data['title']}")
        print(f"Content:\n{data['content']}")
        print("---------------------------")

    elif args.command == "list":
        files = list_entries()
        print("Entries:")
        for f in files:
            print(" -", f)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()