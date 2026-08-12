#!/usr/bin/env python3
"""
run_save_layer.py
==================
CLI script to execute `save_layer.py` from the terminal — without needing
to write manual Python code every time you want to open, modify, or
re-save an .es3 SaveFile (Easy Save 3).
 
Place this file SIDE-BY-SIDE (in the same folder) with `save_layer.py`.
 
USAGE EXAMPLES
-----------------
# 1) View the entire save content (Account + Player) as pretty-printed JSON
python run_save_layer.py inspect SaveFile_Live.es3
 
# 2) Export save content (decrypted) to a regular .json file for manual editing
python run_save_layer.py export SaveFile_Live.es3 player_dump.json
 
# 3) Import the manually edited .json file back and re-encrypt it to .es3
python run_save_layer.py import SaveFile_Live.es3 player_dump.json
 
# 4) Use a different password (if the game/mod uses a custom password)
python run_save_layer.py inspect SaveFile_Live.es3 --password "different-password"
 
All commands accept global options:
    --password TEXT     ES3 password (default: ES3_PASSWORD in save_layer.py)
    --no-backup         Do not create a timestamped backup when saving
"""
import argparse
import json
import sys
from pathlib import Path
 
# Ensure save_layer.py (in the same folder as this script) can be imported
# even if the script is executed from a different working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
 
from app_meta import APP_NAME, APP_VERSION  # noqa: E402
from save_layer import SaveFile, ES3_PASSWORD, AES_BACKEND  # noqa: E402
 
 
def _get_nested(obj, dotted_path):
    """Retrieve value from a nested dict using paths like 'player.level'."""
    node = obj
    for part in dotted_path.split("."):
        if isinstance(node, list):
            part = int(part)
            node = node[part]
        else:
            node = node[part]
    return node
 
 
def _set_nested(obj, dotted_path, value):
    """Set value into a nested dict using paths like 'player.level'."""
    parts = dotted_path.split(".")
    node = obj
    for part in parts[:-1]:
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
 
 
def _parse_value(raw_value):
    """Try to parse CLI argument as JSON (number/bool/null/list/dict);
    if it fails, treat it as a regular string."""
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value
 
 
def _resolve_root(sf, dotted_path):
    """Determine if the field starts from 'account.' or 'player.', returning
    (dict_root, remaining_path)."""
    if dotted_path.startswith("account."):
        return sf.account, dotted_path[len("account."):]
    if dotted_path.startswith("player."):
        return sf.player, dotted_path[len("player."):]
    raise ValueError(
        "Path must start with 'account.' or 'player.' (e.g., player.level)"
    )
 
 
def cmd_inspect(args):
    sf = SaveFile.load(args.path, password=args.password)
    print(f"[AES backend: {AES_BACKEND}]")
    print("=== Account ===")
    print(json.dumps(sf.account, ensure_ascii=False, indent=2))
    print("\n=== Player ===")
    print(json.dumps(sf.player, ensure_ascii=False, indent=2))
 
 
def cmd_get(args):
    sf = SaveFile.load(args.path, password=args.password)
    root, sub_path = _resolve_root(sf, args.field)
    value = root if sub_path == "" else _get_nested(root, sub_path)
    if isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(value)
 
 
def cmd_set(args):
    sf = SaveFile.load(args.path, password=args.password)
    root, sub_path = _resolve_root(sf, args.field)
    if sub_path == "":
        raise ValueError("Use a complete path, e.g., player.level (not just 'player')")
    new_value = _parse_value(args.value)
    _set_nested(root, sub_path, new_value)
    sf.save(args.path, backup=not args.no_backup)
    backup_info = f" (backup created: {sf.last_backup_path})" if sf.last_backup_path else " (without backup)"
    print(f"OK -> {args.field} = {new_value!r} saved to {args.path}{backup_info}")
 
 
def cmd_export(args):
    sf = SaveFile.load(args.path, password=args.password)
    dump = {"account": sf.account, "player": sf.player}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(dump, fh, ensure_ascii=False, indent=2)
    print(f"OK -> save content (decrypted) exported to {args.out}")
 
 
def cmd_import(args):
    sf = SaveFile.load(args.path, password=args.password)
    with open(args.json_path, "r", encoding="utf-8") as fh:
        dump = json.load(fh)
    if "account" not in dump or "player" not in dump:
        raise ValueError("JSON file must contain 'account' and 'player' keys (see 'export' output)")
    sf.account = dump["account"]
    sf.player = dump["player"]
    sf.save(args.path, backup=not args.no_backup)
    backup_info = f" (backup created: {sf.last_backup_path})" if sf.last_backup_path else " (without backup)"
    print(f"OK -> {args.json_path} imported & re-encrypted to {args.path}{backup_info}")
 
 
def build_parser():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME}: read/edit/save .es3 SaveFile (Easy Save 3) from CLI."
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
 
    # Parent parser containing global options, reused (parents=) in each
    # sub-command so --password / --no-backup can be written BEFORE
    # OR AFTER the sub-command name (cleaner terminal user experience).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--password", default=ES3_PASSWORD, help="ES3 password (default: Taskbar Hero default)")
    common.add_argument("--no-backup", action="store_true", help="Do not create a timestamped backup when saving")
 
    sub = parser.add_subparsers(dest="command", required=True)
 
    p_inspect = sub.add_parser("inspect", parents=[common], help="Display entire save content (Account + Player) as JSON")
    p_inspect.add_argument("path", help="Path to .es3 file")
    p_inspect.set_defaults(func=cmd_inspect)
 
    p_get = sub.add_parser("get", parents=[common], help="Display a single field, e.g., player.level")
    p_get.add_argument("path", help="Path to .es3 file")
    p_get.add_argument("field", help="Dotted-path field, starting with 'account.' or 'player.'")
    p_get.set_defaults(func=cmd_get)
 
    p_set = sub.add_parser("set", parents=[common], help="Modify a single field and re-save (HMAC automatically calculated)")
    p_set.add_argument("path", help="Path to .es3 file")
    p_set.add_argument("field", help="Dotted-path field, starting with 'account.' or 'player.'")
    p_set.add_argument("value", help="New value (JSON parsed if possible, e.g., 99, true, \"text\")")
    p_set.set_defaults(func=cmd_set)
 
    p_export = sub.add_parser("export", parents=[common], help="Export save content (Account+Player, decrypted) to a .json file")
    p_export.add_argument("path", help="Path to .es3 file")
    p_export.add_argument("out", help="Output .json file path")
    p_export.set_defaults(func=cmd_export)
 
    p_import = sub.add_parser("import", parents=[common], help="Import a .json file (from 'export') and re-encrypt it to .es3")
    p_import.add_argument("path", help="Path to the target .es3 file to be written")
    p_import.add_argument("json_path", help="Source .json file path (from 'export' or custom made)")
    p_import.set_defaults(func=cmd_import)
 
    return parser
 
 
def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except FileNotFoundError as e:
        print(f"ERROR: file not found -> {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()
