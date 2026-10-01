from __future__ import annotations

import argparse
import json

from ai_pipeline.universal_processor import process_pid_file_universal


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a P&ID file (PDF or image) and extract equipment and BOM data.")
    parser.add_argument("file_path", help="Path to the uploaded P&ID file (PDF, PNG, JPG, etc.)")
    args = parser.parse_args()

    results = process_pid_file_universal(args.file_path)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
