"""
The MIT License (MIT)

Copyright (c) 2025 Lala Sabathil <lala@pycord.dev> & Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import os
from pathlib import Path

cur_path = str(Path.cwd())
ignore_set = {"__init__.py", "count_sourcelines.py", "docs-json-exporter.py"}

loc_list = []

for py_dir, _, py_files in os.walk(cur_path):
    for py_file in py_files:
        if py_file.endswith(".py") and py_file not in ignore_set:
            total_path = str(Path(py_dir) / py_file)
            try:
                with Path(total_path).open(encoding="utf-8") as file:
                    loc_list.append(
                        (len(file.read().splitlines()), total_path.split(cur_path)[1])
                    )
            except UnicodeDecodeError as e:
                print(f"Skipping file {total_path} due to encoding error: {e}")

for line_number_count, filename in loc_list:
    print(f"{line_number_count:05d} lines in {filename}")

print(f"\nTotal: {sum([x[0] for x in loc_list])} lines ({cur_path})")
