from __future__ import annotations

import argparse
import json

from ai_pipeline.pipeline import process_pid_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a P&ID file and generate extracted asset metadata.")
    parser.add_argument("file_path", help="Path to the uploaded P&ID file")
    args = parser.parse_args()

    results = process_pid_file(args.file_path)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
