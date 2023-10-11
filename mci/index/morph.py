import argparse
import asyncio
import os
import time
from typing import List, Optional

import git
import rich
from rich.console import Console
from rich.markdown import Markdown

import mci.ir.IR as IR
from mci.index.index import Index, PathWithId, Query, Text
from mci.ir.parser import parse_files_in_paths

repo_root = git.Repo(".", search_parent_directories=True).git.rev_parse("--show-toplevel")
morph_dir = os.path.join(repo_root, ".morph")
os.makedirs(morph_dir, exist_ok=True)
index_file = os.path.join(morph_dir, "index.rci")

from dataclasses import dataclass


@dataclass
class MorphSearchResult:
    root_path: str
    path_with_id: PathWithId  # Tuple[str, QualifiedId]
    score: float
    symbol: IR.Symbol
    language: Optional[str] = None

    def __post_init__(self):
        self.language = IR.language_from_file_extension(self.path_with_id[0]) or ""

    def __str__(self):
        return self.format_md()

    def format_md(self):
        return f"""\

[{self.score:.4f}] [{self.path_with_id[0]}#{self.path_with_id[1]}]({os.path.join(self.root_path, self.path_with_id[0])})

```{self.language}
{self.symbol.get_substring().decode()}
```"""


def search(args):
    TOP_N = 8
    # Load the index
    index = Index.load(index_file)
    console = Console()

    total_symbols = sum([len(file._symbol_table) for file in index.project._files])

    # Create a query from the command line arguments
    query_str = " ".join(args)
    query = Query(Text(query_str), num_results=TOP_N)

    header = f"""\
# Morph Code Index

Displaying top **{TOP_N}** out of **{total_symbols}** code objects for:

'{query_str}'

---
"""
    header_md = Markdown(header)
    console.print(header_md)

    # Perform the search
    start = time.time()

    search_results = index.search(query)
    search_results = [
        MorphSearchResult(
            root_path=index.project.root_path,
            path_with_id=search_result[0],
            score=search_result[1],
            symbol=search_result[2],
        )
        for search_result in search_results
    ]
    search_results_md = Markdown(
        "\n---\n".join(search_result.format_md() for search_result in search_results)
    )
    console.print(search_results_md)
    elapsed = time.time() - start
    print(f"\nSearched in {elapsed:.2f} seconds")


async def index_repo(args):
    # Create the index
    project_root = repo_root  # the root of the git repo

    # set_embedding_function(openai=true)
    print(f"Reading {project_root} ...")
    project = parse_files_in_paths([project_root])
    print(f"Creating index...")
    start = time.time()

    index = await Index.create(
        project=project,
    )

    print(f"Created index in {time.time() - start:.2f} seconds")
    print(f"Saving index to file... {index_file}")
    start = time.time()
    index.save(index_file)
    print(f"Saved index in {time.time() - start:.2f} seconds")


def main():
    # Create the parser
    parser = argparse.ArgumentParser(
        description="Perform a search in the index or index a repository."
    )

    # Add the arguments
    parser.add_argument("command", choices=["search", "index"], help="the command to execute")
    parser.add_argument(
        "arguments",
        metavar="N",
        type=str,
        nargs="*",
        help="the arguments for the command",
    )

    # Parse the command line arguments
    args = parser.parse_args()

    # Call the appropriate function
    if args.command == "search":
        search(args.arguments)
    elif args.command == "index":
        asyncio.run(index_repo(args.arguments))


if __name__ == "__main__":
    main()
