"""Local folder analyzer & Hybrid Code RAG engine for the learning module.

Watches/scans user-linked study folders (e.g. ``C:\\...\\C++ With DSA``),
extracts language concepts and symbols from source files, indexes code chunks
into SQLite + FTS5 (plus optional embeddings), maps practice files to roadmap
topics using a Suggest & Confirm workflow:

- Auto-marks matched topics as ``learning`` (in-progress) when code files exist.
- Creates ``pending`` completion suggestions in ``topic_code_evidence`` when
  substantive practiced code is detected, letting the user confirm before
  marking a topic ``completed``.
- Tracks empty/WIP files (e.g. a newly created 0-byte ``while_loop.cpp``) so
  S.P.I.D.E.Y. can gently remind the user to finish them in friendly check-ins.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy

from . import progress, schema

LOGGER = logging.getLogger("spidey.learning.code_rag")

Embedder = Callable[[str], list[float] | None]

SOURCE_EXTENSIONS: dict[str, str] = {
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".h": "c/cpp",
    ".c": "c",
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".cs": "csharp",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
}

COMPILED_ARTIFACT_EXTS = (".exe", ".out", ".o", ".obj", ".class")

IGNORED_DIRS = {
    ".git", ".vscode", ".idea", "node_modules", "__pycache__", ".venv", "venv",
    "env", "build", "dist", "target", "bin", "obj", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "cmake-build-debug", "cmake-build-release",
}

MAX_FILE_BYTES = 256 * 1024
CHUNK_LINES = 45
CHUNK_OVERLAP = 8
SUGGEST_CONFIDENCE_THRESHOLD = 0.60
# Bump whenever concept regex rules change so linked folders auto-reanalyze once and purge stale evidence.
ANALYZER_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Concept extraction rules (filename + code patterns -> canonical concepts)
# ---------------------------------------------------------------------------

# Each rule: (concept_id, filename_keywords, code_patterns, related_topic_terms)
_CONCEPT_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "basics_compilation",
        ("first", "hello", "basic", "basics", "intro", "boilerplate", "compile", "syntax", "setup"),
        (r"#include\s*<iostream>", r"\bint\s+main\s*\(", r"public\s+static\s+void\s+main"),
        ("basics & compilation", "java basics", "css basics", "node.js basics", "compilation", "fundamentals", "syntax", "getting started"),
    ),
    (
        "variables_data_types",
        ("variable", "variables", "datatype", "datatypes", "data_type", "data_types", "types", "sizeof", "primitive"),
        (r"\bsizeof\s*\(", r"\b(?:unsigned|long\s+long|short|double|float|bool|char)\s+[a-z_]\w*"),
        ("variables", "data types", "primitive"),
    ),
    (
        "operators_type_casting",
        ("operator", "operators", "casting", "type_casting", "typecast", "type_cast", "arithmetic", "bitwise", "relational", "logical"),
        (
            r"\b(?:static_cast|dynamic_cast|const_cast|reinterpret_cast)\s*<",
            r"\(\s*(?:double|float|int|char|long)\s*\)\s*[a-z_]\w*",
            r"[a-zA-Z0-9_)\]]\s*(?:\+|-|\*|/|%|==|!=|<=|>=|&&|\|\|)\s*[a-zA-Z0-9_(]",
        ),
        ("operators", "type casting", "casting", "arithmetic", "bitwise"),
    ),
    (
        "input_output",
        ("input", "output", "getting_input", "io", "cin", "cout", "sum", "calculator", "scanner", "stdio"),
        (r"\bcin\s*>>", r"\bgetline\s*\(", r"\bscanf\s*\(", r"\binput\s*\(", r"new\s+Scanner\s*\("),
        ("input / output", "input", "output", "i/o", "cin", "cout"),
    ),
    (
        "control_flow",
        ("if_else", "ifelse", "conditional", "conditionals", "ternary", "switch", "loop", "loops",
         "while", "while_loop", "for_loop", "do_while", "pattern", "patterns", "control", "branch", "grade", "odd_even", "prime"),
        (r"\bif\s*\(", r"\belse\b", r"\bwhile\s*\(", r"\bfor\s*\(", r"\bswitch\s*\(", r"\?[^?:\n]+:[^:\n]+"),
        ("control flow", "conditionals", "loops", "if else", "while", "ternary", "switch"),
    ),
    (
        "functions",
        ("function", "functions", "func", "method", "methods", "pass_by", "call_by", "overload", "factorial", "ncr", "binomial"),
        (r"^\s*(?:void|int|double|float|char|bool|long|string|auto|std::string)\s+(?!main\b)[A-Za-z_]\w*\s*\([^;]*\)\s*\{",
         r"^\s*def\s+[A-Za-z_]\w*\s*\("),
        ("functions", "methods", "overload", "parameters", "arguments"),
    ),
    (
        "scope_storage",
        ("scope", "storage", "global", "local", "extern", "register"),
        (r"\b(?:extern|thread_local)\s+", r"\bstatic\s+(?:int|double|float|char|bool|long|auto)\s+"),
        ("scope", "storage classes", "global", "local"),
    ),
    (
        "arrays",
        ("array", "arrays", "subarray", "kadane", "matrix", "2d_array", "linear_search", "reverse_array", "majority"),
        (r"\b(?:int|double|float|char|long|string)\s+[A-Za-z_]\w*\s*\[[^\]]*\]", r"\bvector\s*<"),
        ("arrays", "array", "matrix", "subarray", "arrays and hashing"),
    ),
    (
        "strings",
        ("string", "strings", "palindrome", "anagram", "substr", "substring", "char_array", "cstring"),
        (r"#include\s*<string>", r"\bstd::string\b", r"\bstring\s+[A-Za-z_]\w*", r"\.substr\s*\(", r"\.length\s*\("),
        ("strings", "string", "strings and arrays", "string handling"),
    ),
    (
        "pointers",
        ("pointer", "pointers", "ptr", "dereference", "address", "pointer_arithmetic"),
        (r"\b(?:int|double|float|char|void|auto)\s*\*\s*[A-Za-z_]\w*", r"\bnullptr\b", r"\bNULL\b"),
        ("pointers", "pointer", "memory address"),
    ),
    (
        "references",
        ("reference", "references", "pass_by_ref", "alias"),
        (r"\b(?:int|double|float|char|string|auto)\s*&\s*[A-Za-z_]\w*",),
        ("references", "reference"),
    ),
    (
        "dynamic_memory",
        ("dynamic_memory", "heap", "malloc", "calloc", "new_delete"),
        (r"\bnew\s+[A-Za-z_]\w*(?:\s*\[|\s*\()", r"\bdelete(?:\[\])?\s+[A-Za-z_]\w*", r"\b(?:malloc|calloc|realloc|free)\s*\("),
        ("dynamic memory", "heap", "malloc", "new delete"),
    ),
    (
        "structs_enums_unions",
        ("struct", "structs", "enum", "enums", "union", "unions"),
        (r"\bstruct\s+[A-Za-z_]\w*\s*\{", r"\benum\s+(?:class\s+)?[A-Za-z_]\w*", r"\bunion\s+[A-Za-z_]\w*"),
        ("structs", "enums", "unions"),
    ),
    (
        "classes_objects",
        ("class", "classes", "object", "objects", "oop", "oops", "encapsulation"),
        (r"^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+|export\s+)?class\s+[A-Za-z_]\w*(?:\s*:\s*(?:public|private|protected))?",),
        ("classes & objects", "classes and objects", "object-oriented", "oop", "encapsulation"),
    ),
    (
        "constructors_destructors",
        ("constructor", "constructors", "destructor", "destructors", "copy_constructor"),
        (r"~[A-Za-z_]\w*\s*\(\s*\)", r"\bexplicit\s+[A-Za-z_]\w*\s*\("),
        ("constructors", "destructors"),
    ),
    (
        "static_this_friend_const",
        ("static_member", "friend", "this_pointer", "const_member"),
        (r"\bfriend\s+", r"\bthis->", r"\)\s*const\s*\{"),
        ("static", "this", "friend", "const members"),
    ),
    (
        "operator_overloading",
        ("operator_overload", "operator_overloading"),
        (r"\boperator\s*(?:\+|-|\*|/|==|!=|<<|>>|\[\]|\(\)|=)\s*\(",),
        ("operator overloading",),
    ),
    (
        "inheritance",
        ("inheritance", "subclass", "derived", "base_class"),
        (r"\bclass\s+[A-Za-z_]\w*\s*:\s*(?:public|protected|private)\s+[A-Za-z_]\w*", r"\bextends\s+[A-Za-z_]\w*"),
        ("inheritance",),
    ),
    (
        "polymorphism_virtual",
        ("polymorphism", "virtual", "vtable", "override", "abstract", "interface"),
        (
            r"\bvirtual\s+",
            r"\boverride\b",
            r"\bvirtual\s+[^\n;{]+\([^)]*\)\s*(?:const\s*)?=\s*0\s*;",
        ),
        ("polymorphism", "virtual functions", "abstract classes"),
    ),
    (
        "templates_generics",
        ("template", "templates", "generic", "generics"),
        (r"\btemplate\s*<\s*(?:typename|class)\s+",),
        ("templates", "generics"),
    ),
    (
        "exception_handling",
        ("exception", "exceptions", "try_catch", "error_handling"),
        (r"\btry\s*\{", r"\bcatch\s*\(", r"\bthrow\s+"),
        ("exception handling", "exceptions", "error handling"),
    ),
    (
        "file_handling",
        ("file", "files", "fstream", "file_io", "file_handling"),
        (r"#include\s*<fstream>", r"\b(?:ifstream|ofstream|fstream)\b"),
        ("file handling", "file i/o", "io streams"),
    ),
    (
        "preprocessor_macros",
        ("macro", "macros", "preprocessor", "define", "ifdef"),
        (r"^\s*#define\s+[A-Za-z_]\w*", r"^\s*#(?:ifdef|ifndef|pragma)\b"),
        ("preprocessor", "macros"),
    ),
    (
        "namespaces_multifile",
        ("namespace", "namespaces", "header", "multifile"),
        (r"\bnamespace\s+[A-Za-z_]\w*\s*\{", r'#include\s*"[^"]+\.h(?:pp)?"'),
        ("namespaces", "multi-file"),
    ),
    (
        "auto_range_for",
        ("range_for", "auto_decltype", "decltype"),
        (r"\bfor\s*\(\s*(?:const\s+)?auto\s*&?\s*[A-Za-z_]\w*\s*:", r"\bdecltype\s*\("),
        ("auto", "decltype", "range-based for"),
    ),
    (
        "lambdas",
        ("lambda", "lambdas", "closure"),
        (r"(?<![A-Za-z0-9_])\[[^\n\]]*\]\s*\([^;\n)]*\)\s*(?:->\s*[\w:<>]+\s*)?\{",),
        ("lambdas", "lambda", "closures"),
    ),
    (
        "smart_pointers_raii",
        ("smart_pointer", "smart_pointers", "unique_ptr", "shared_ptr", "raii"),
        (r"\b(?:unique_ptr|shared_ptr|weak_ptr|make_unique|make_shared)\b",),
        ("smart pointers", "raii"),
    ),
    (
        "move_semantics",
        ("move_semantics", "rvalue", "rule_of_5", "rule_of_3"),
        (r"\bstd::move\s*\(", r"\b(?:int|double|float|char|string|auto|T)\s*&&\s*[A-Za-z_]\w*"),
        ("move semantics", "rule of 3", "rule of 5"),
    ),
    (
        "stl_containers",
        ("stl", "vector", "map", "unordered_map", "set", "deque", "priority_queue", "iterator", "iterators"),
        (r"#include\s*<(?:vector|map|unordered_map|set|unordered_set|list|deque|algorithm|iterator)>",
         r"\b(?:vector|unordered_map|map|set|priority_queue|deque)\s*<"),
        ("stl containers", "stl iterators", "stl", "collections"),
    ),
    (
        "multithreading",
        ("thread", "threads", "mutex", "concurrency", "multithreading", "async"),
        (r"#include\s*<(?:thread|mutex|future|atomic)>", r"\bstd::thread\b", r"\bstd::mutex\b"),
        ("multithreading", "concurrency", "threads"),
    ),
    (
        "recursion_backtracking",
        ("recursion", "recursive", "backtracking", "n_queens", "sudoku", "permutations", "subsets", "fibonacci"),
        (r"\bbacktrack\s*\(",),
        ("recursion", "backtracking"),
    ),
    (
        "sorting_searching",
        ("sort", "sorting", "binary_search", "merge_sort", "quick_sort", "bubble_sort", "insertion_sort", "selection_sort", "search"),
        (r"\b(?:merge_sort|mergeSort|quick_sort|quickSort|binary_search|binarySearch)\b",),
        ("sorting", "searching", "binary search"),
    ),
    (
        "two_pointers_sliding_window",
        ("two_pointer", "two_pointers", "sliding_window", "container_water", "rainwater"),
        (r"\b(?:left|low)\s*<\s*(?:right|high)\b",),
        ("two pointers", "sliding window"),
    ),
    (
        "linked_lists",
        ("linked_list", "linkedlist", "listnode", "doubly_linked", "cycle_detection"),
        (r"\bstruct\s+(?:ListNode|Node)\b", r"->next\b"),
        ("linked lists", "linked list"),
    ),
    (
        "stacks_queues",
        ("stack", "stacks", "queue", "queues", "monotonic", "next_greater", "lru"),
        (r"#include\s*<(?:stack|queue)>", r"\b(?:stack|queue)\s*<"),
        ("stacks", "queues", "stack", "queue"),
    ),
    (
        "trees",
        ("tree", "trees", "bst", "binary_tree", "avl", "trie", "heap", "segment_tree", "traversal", "inorder", "preorder", "postorder"),
        (r"\bstruct\s+TreeNode\b", r"->left\b.*->right\b"),
        ("trees", "binary trees", "bst", "heaps"),
    ),
    (
        "graphs",
        ("graph", "graphs", "bfs", "dfs", "dijkstra", "topological", "mst", "kruskal", "prim", "union_find", "dsu"),
        (r"\b(?:bfs|dfs|dijkstra|adj_list|adjacency)\b",),
        ("graphs", "bfs", "dfs", "shortest paths"),
    ),
    (
        "dynamic_programming",
        ("dp", "dynamic_programming", "knapsack", "lcs", "lis", "memoization", "tabulation", "coin_change"),
        (r"\bdp\s*\[", r"\bmemo\s*\["),
        ("dynamic programming", "dp", "memoization"),
    ),
    (
        "big_o_complexity",
        ("big_o", "complexity", "time_complexity", "space_complexity"),
        (r"O\s*\(\s*(?:1|n|log\s*n|n\s*log\s*n|n\^2|2\^n)\s*\)",),
        ("big o", "complexity", "time complexity"),
    ),
    (
        "react_components_hooks",
        ("component", "components", "hook", "hooks", "usestate", "useeffect", "jsx", "tsx", "props", "context"),
        (
            r"\buse(?:State|Effect|Memo|Callback|Ref|Context|Reducer)\s*\(",
            r"export\s+(?:default\s+)?function\s+[A-Z]\w*\s*\(",
        ),
        ("react", "components", "hooks", "state management", "jsx", "props"),
    ),
    (
        "typescript_types_interfaces",
        ("interface", "interfaces", "type_alias", "generics_ts", "enum_ts", "types_ts"),
        (
            r"\binterface\s+[A-Z]\w*\s*(?:<[^>]+>)?\s*\{",
            r"\btype\s+[A-Z]\w*\s*(?:<[^>]+>)?\s*=",
        ),
        ("typescript", "interfaces", "type annotations", "type system"),
    ),
    (
        "async_promises_concurrency",
        ("async", "await", "promise", "promises", "future", "coroutine", "coroutines", "goroutine", "tokio"),
        (
            r"\basync\s+(?:def|function)\b",
            r"\bawait\s+\w+",
            r"\bnew\s+Promise\s*\(",
            r"\bgo\s+[A-Za-z_]\w*\s*\(",
            r"#\[tokio::main\]",
        ),
        ("async", "promises", "async/await", "coroutines", "goroutines"),
    ),
    (
        "rest_api_http_routing",
        ("api", "rest", "router", "endpoint", "endpoints", "fastapi", "express", "middleware", "http", "fetch"),
        (
            r"@(?:app|router)\.(?:get|post|put|delete|patch)\s*\(",
            r"\bapp\.(?:get|post|put|delete|use)\s*\(",
            r"\bfetch\s*\(\s*[`'\"/]",
        ),
        ("rest api", "http", "routing", "endpoints", "middleware", "fastapi", "express"),
    ),
    (
        "database_sql_queries",
        ("sql", "query", "queries", "schema", "migration", "join", "sqlite", "postgres", "database", "orm"),
        (
            r"\bSELECT\b[\s\S]{1,120}\bFROM\b",
            r"\bCREATE\s+TABLE\b",
            r"\b(?:INNER|LEFT|RIGHT)\s+JOIN\b",
            r"\bINSERT\s+INTO\b",
        ),
        ("sql", "databases", "joins", "queries", "schema design", "sqlite", "postgresql"),
    ),
    (
        "rust_ownership_borrowing",
        ("ownership", "borrowing", "lifetime", "lifetimes", "trait", "traits", "pattern_matching", "cargo"),
        (
            r"\bfn\s+[a-z_]\w*\s*(?:<[^>]+>)?\s*\([^)]*&(?:mut\s+)?[A-Za-z_]",
            r"\bimpl(?:\s*<[^>]+>)?\s+[A-Z]\w*",
            r"\bmatch\s+[a-z_]\w*\s*\{",
        ),
        ("ownership", "borrowing", "lifetimes", "traits", "pattern matching", "rust"),
    ),
    (
        "python_decorators_generators",
        ("decorator", "decorators", "generator", "generators", "comprehension", "dataclass", "context_manager"),
        (
            r"^\s*@[A-Za-z_][\w.]*",
            r"\byield\s+(?:from\s+)?\S+",
            r"\[[^\]]+\bfor\s+[a-z_]\w*\s+in\s+[^\]]+\]",
        ),
        ("decorators", "generators", "comprehensions", "dataclasses", "pythonic"),
    ),
)

_RAG_CONCEPT_EXPANSIONS: tuple[set[str], ...] = (
    {"loop", "loops", "while", "for", "do", "for_loop", "while_loop", "do_while", "iteration", "control", "if", "else", "if_else", "ternary", "switch", "conditional", "branch", "pattern"},
    {"cast", "casting", "typecast", "type_casting", "conversion", "operator", "operators", "arithmetic", "modulo", "bitwise"},
    {"input", "output", "cin", "cout", "io", "scanf", "printf", "sum", "getting_input", "getline"},
    {"variable", "variables", "datatype", "data_type", "int", "float", "double", "char", "bool", "sizeof", "primitive"},
    {"pointer", "pointers", "ptr", "address", "dereference", "reference", "references", "nullptr"},
    {"function", "functions", "func", "method", "return", "parameters", "arguments", "recursion", "factorial", "prime", "fibonacci"},
    {"array", "arrays", "vector", "subarray", "matrix", "string", "strings", "palindrome", "anagram"},
    {"class", "classes", "object", "objects", "oop", "struct", "constructor", "inheritance", "polymorphism", "virtual"},
    {"linked", "list", "node", "stack", "queue", "tree", "bst", "graph", "bfs", "dfs", "dp", "dsa"},
    {"react", "hook", "hooks", "usestate", "useeffect", "component", "jsx", "tsx", "typescript", "interface"},
    {"async", "await", "promise", "api", "rest", "endpoint", "router", "http", "sql", "query", "join"},
    {"rust", "ownership", "borrow", "trait", "impl", "match", "go", "goroutine", "decorator", "generator"},
    {"cpp", "cplusplus", "dsa", "algorithm", "algorithms", "problem", "problems", "interview", "practice", "exercise"},
)

_TECH_ALIAS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![a-z0-9])c\s*\+\s*\+(?![a-z0-9])", re.IGNORECASE), " cpp "),
    (re.compile(r"\bc\s+plus\s+plus\b", re.IGNORECASE), " cpp "),
    (re.compile(r"\bcplusplus\b", re.IGNORECASE), " cpp "),
    (re.compile(r"(?<![a-z0-9])c\s*#(?![a-z0-9])", re.IGNORECASE), " csharp "),
    (re.compile(r"\bc\s+sharp\b", re.IGNORECASE), " csharp "),
    (re.compile(r"\bnode\.?js\b", re.IGNORECASE), " nodejs "),
    (re.compile(r"\bnext\.?js\b", re.IGNORECASE), " nextjs "),
    (re.compile(r"\breact\.?js\b", re.IGNORECASE), " reactjs "),
    (re.compile(r"\boops\b", re.IGNORECASE), " oop "),
)

_IRREGULAR_STEMS: dict[str, str] = {
    "learnt": "learn",
    "learned": "learn",
    "learning": "learn",
    "studied": "study",
    "studies": "study",
    "studying": "study",
    "coded": "code",
    "coding": "code",
    "wrote": "write",
    "written": "write",
    "writing": "write",
    "practiced": "practice",
    "practicing": "practice",
    "practised": "practice",
    "practising": "practice",
    "matrices": "matrix",
    "indices": "index",
    "classes": "class",
    "branches": "branch",
    "switches": "switch",
    "looping": "loop",
    "loops": "loop",
    "conditionals": "conditional",
    "variables": "variable",
    "operators": "operator",
    "functions": "function",
    "pointers": "pointer",
    "references": "reference",
    "arrays": "array",
    "strings": "string",
    "trees": "tree",
    "graphs": "graph",
    "stacks": "stack",
    "queues": "queue",
    "lists": "list",
    "problems": "problem",
    "questions": "question",
    "exercises": "exercise",
    "interviews": "interview",
    "algorithms": "algorithm",
    "patterns": "pattern",
    "datatypes": "datatype",
    "casting": "cast",
}


def _normalize_tech_query(text: str) -> str:
    norm = str(text or "")
    for pat, repl in _TECH_ALIAS_PATTERNS:
        norm = pat.sub(repl, norm)
    return norm


def _stem_token(tok: str) -> str:
    t = tok.lower().strip()
    if not t:
        return ""
    if t in _IRREGULAR_STEMS:
        return _IRREGULAR_STEMS[t]
    if len(t) >= 6 and t.endswith("ing") and not t.endswith("string"):
        return t[:-3]
    if len(t) >= 5 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) >= 5 and t.endswith("ed") and not t.endswith("speed"):
        return t[:-2]
    if len(t) >= 5 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def _slug_tokens(text: str) -> list[str]:
    norm = _normalize_tech_query(text)
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1_\2", norm)
    return [tok for tok in re.findall(r"[a-z0-9]+", cleaned.lower()) if tok]


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Match a keyword/phrase on word boundaries so 'io' never matches 'functions' or 'oop' in 'loop'."""
    phrase_clean = phrase.strip().lower()
    if not phrase_clean:
        return False
    # Normalize punctuation/underscores to spaces for boundary-safe matching
    norm_text = re.sub(r"[_\-]+", " ", text.lower())
    norm_phrase = re.sub(r"[_\-]+", " ", phrase_clean)
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(norm_phrase)}(?![a-z0-9])", norm_text))


def _strip_comments_text(text: str, language: str) -> str:
    """Return source code with comments removed."""
    if not text.strip():
        return ""
    if language in {"cpp", "c", "c/cpp", "java", "javascript", "typescript", "rust", "go", "csharp"}:
        no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return "\n".join(re.sub(r"//.*$", "", ln) for ln in no_block.splitlines())
    if language == "python":
        return "\n".join(re.sub(r"#.*$", "", ln) for ln in text.splitlines())
    return text


_BOILERPLATE_LINE_RE = re.compile(
    r"^(?:"
    r"#include\s*[<\"][^>\"]+[>\"]"
    r"|using\s+namespace\s+\w+\s*;"
    r"|(?:int|void)\s+main\s*\([^)]*\)\s*\{?"
    r"|return\s+0\s*;"
    r"|public\s+(?:class|static\s+void\s+main)\b.*"
    r"|import\s+[\w.*]+\s*;?"
    r"|package\s+[\w.]+\s*;?"
    r"|[\{\}\(\);,\s]+"
    r")$",
    re.IGNORECASE,
)


def _strip_comments_and_count(text: str, language: str) -> tuple[int, int, int]:
    """Return (total_lines, non_comment_code_lines, substantive_body_lines)."""
    lines = text.splitlines()
    total = len(lines)
    if not text.strip():
        return 0, 0, 0

    clean = _strip_comments_text(text, language)
    code_lines = 0
    body_lines = 0
    for ln in clean.splitlines():
        stripped = ln.strip()
        if not stripped or stripped in {"{", "}", ");", ";"}:
            continue
        code_lines += 1
        if not _BOILERPLATE_LINE_RE.match(stripped):
            body_lines += 1
    return total, code_lines, body_lines


def _extract_symbols(text: str, language: str) -> list[str]:
    """Extract lightweight symbols (includes, function/class/struct names)."""
    symbols: list[str] = []
    if not text.strip():
        return symbols

    if language == "python":
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(node.name)
        except SyntaxError:
            pass
    elif language in {"cpp", "c", "c/cpp", "java", "csharp"}:
        for inc in re.findall(r"#include\s*[<\"]([^>\"]+)[>\"]", text):
            symbols.append(f"<{inc}>")
        for cls in re.findall(r"\b(?:class|struct|enum)\s+([A-Za-z_]\w*)", text):
            if cls not in symbols:
                symbols.append(cls)
        for fn in re.findall(
            r"^\s*(?:[\w:<>]+\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?\{",
            text,
            flags=re.MULTILINE,
        ):
            if fn not in {"if", "for", "while", "switch", "catch"} and fn not in symbols:
                symbols.append(fn)
    elif language in {"javascript", "typescript"}:
        for fn in re.findall(r"\b(?:function|class|interface|type)\s+([A-Za-z_$]\w*)", text):
            if fn not in symbols:
                symbols.append(fn)
        for fn in re.findall(r"\bconst\s+([A-Za-z_$]\w*)\s*=\s*(?:async\s*)?\(", text):
            if fn not in symbols:
                symbols.append(fn)
    elif language == "rust":
        for sym in re.findall(r"\b(?:fn|struct|enum|trait)\s+([A-Za-z_]\w*)", text):
            if sym not in symbols:
                symbols.append(sym)
    elif language == "go":
        for sym in re.findall(r"\bfunc\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)", text):
            if sym not in symbols:
                symbols.append(sym)
        for sym in re.findall(r"\btype\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b", text):
            if sym not in symbols:
                symbols.append(sym)

    return symbols[:20]


def _classify_file_state(
    text: str,
    code_lines: int,
    body_lines: int,
    has_compiled: bool,
    language: str,
) -> str:
    """Classify a practice file strictly from its actual code content: 'empty', 'wip', or 'practiced'."""
    if not text.strip():
        return "empty"
    if language in {"markdown", "sql", "html", "css"}:
        return "practiced" if code_lines >= 2 else "wip"
    # Boilerplate-only (e.g. just #include + empty int main() { return 0; }) is WIP, never practiced
    if body_lines <= 0:
        return "wip"
    if body_lines >= 2 or (has_compiled and body_lines >= 1):
        return "practiced"
    return "wip"


def analyze_source_file(
    path: Path,
    root_folder: Path,
) -> dict[str, Any]:
    """Inspect a single source file's actual code content, concepts, symbols, and state."""
    rel_path = path.relative_to(root_folder).as_posix()
    ext = path.suffix.lower()
    language = SOURCE_EXTENSIONS.get(ext, "")

    raw_bytes = path.read_bytes()
    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8", errors="replace")
    stat = path.stat()
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    has_compiled = any(
        path.with_suffix(c_ext).exists()
        for c_ext in COMPILED_ARTIFACT_EXTS
    ) if ext in {".cpp", ".cc", ".cxx", ".c", ".java"} else False

    line_count, code_lines, body_lines = _strip_comments_and_count(text, language)
    file_state = _classify_file_state(text, code_lines, body_lines, has_compiled, language)
    clean_code = _strip_comments_text(text, language)
    symbols = _extract_symbols(clean_code, language)

    stem_lower = path.stem.lower()
    stem_tokens = set(_slug_tokens(path.stem))
    rel_tokens = set(_slug_tokens(rel_path))

    # Separate filename hints from ACTUAL code-verified concepts inside the file!
    filename_concepts: list[str] = []
    code_concepts: list[str] = []

    for concept_id, fname_keys, code_patterns, _ in _CONCEPT_RULES:
        fname_hit = any(
            (key in stem_tokens) or (key in rel_tokens) or _phrase_in_text(key, stem_lower)
            for key in fname_keys
        )
        if fname_hit:
            filename_concepts.append(concept_id)
        # Always check ACTUAL active (non-comment) code inside the file!
        if body_lines > 0 and code_patterns:
            for pat in code_patterns:
                if re.search(pat, clean_code, flags=re.MULTILINE):
                    code_concepts.append(concept_id)
                    break

    # Only concepts verified by actual code count as practiced concepts;
    # for empty/WIP files keep filename hints separately for gentle reminders.
    all_concepts: list[str] = []
    for c in [*code_concepts, *(filename_concepts if file_state == "practiced" else [])]:
        if c not in all_concepts:
            all_concepts.append(c)

    if file_state == "empty":
        summary = f"Empty file ({rel_path}) — no code written yet."
    elif file_state == "wip":
        summary = f"Work in progress ({rel_path}, {body_lines} logic lines — boilerplate/incomplete)."
    else:
        concept_preview = ", ".join(c.replace("_", " ") for c in code_concepts[:3]) or language
        compiled_note = ", compiled" if has_compiled else ""
        summary = f"Verified code: {concept_preview} ({body_lines} logic lines{compiled_note})."

    return {
        "rel_path": rel_path,
        "abs_path": str(path.resolve()),
        "language": language,
        "content_hash": content_hash,
        "file_size": stat.st_size,
        "line_count": line_count,
        "code_lines": code_lines,
        "body_lines": body_lines,
        "has_compiled_artifact": has_compiled,
        "file_state": file_state,
        "concepts": all_concepts,
        "code_concepts": code_concepts,
        "filename_concepts": filename_concepts,
        "symbols": symbols,
        "summary": summary,
        "modified_at": modified_at,
        "text": text,
    }


def _chunk_source_text(text: str, rel_path: str, concepts: list[str]) -> list[dict[str, Any]]:
    """Split source file into overlapping line-numbered chunks for Hybrid RAG."""
    if not text.strip():
        return [
            {
                "chunk_index": 0,
                "start_line": 1,
                "end_line": 1,
                "content": f"[Empty practice file: {rel_path}]",
                "concepts": " ".join([rel_path, *_slug_tokens(rel_path), *concepts]),
            }
        ]

    lines = text.splitlines()
    concept_str = " ".join(
        dict.fromkeys([rel_path, *_slug_tokens(rel_path), *(c.replace("_", " ") for c in concepts)])
    )
    if len(lines) <= CHUNK_LINES:
        return [
            {
                "chunk_index": 0,
                "start_line": 1,
                "end_line": len(lines),
                "content": "\n".join(lines),
                "concepts": concept_str,
            }
        ]

    chunks: list[dict[str, Any]] = []
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    idx = 0
    for start in range(0, len(lines), step):
        end = min(len(lines), start + CHUNK_LINES)
        chunk_body = "\n".join(lines[start:end])
        chunks.append(
            {
                "chunk_index": idx,
                "start_line": start + 1,
                "end_line": end,
                "content": chunk_body,
                "concepts": concept_str,
            }
        )
        idx += 1
        if end >= len(lines):
            break
    return chunks


# ---------------------------------------------------------------------------
# Mapping analyzed files -> roadmap topics
# ---------------------------------------------------------------------------

_CONCEPT_TOPIC_TERMS: dict[str, tuple[str, ...]] = {
    concept_id: topic_terms
    for concept_id, _, _, topic_terms in _CONCEPT_RULES
}


def _topic_match_score(topic: dict[str, Any], file_info: dict[str, Any]) -> tuple[float, list[str], bool]:
    """Score how strongly a code file evidences a topic, requiring ACTUAL code inside the file.

    Returns ``(score, reasons, code_verified)``.
    ``code_verified`` is True ONLY when the file has real logic lines AND actual code
    constructs matching this topic (never from an empty, boilerplate-only, or misnamed file).
    """
    # Empty or boilerplate-only files NEVER count as code evidence for topic completion!
    file_state = file_info.get("file_state", "empty")
    body_lines = int(file_info.get("body_lines") or 0)
    if file_state != "practiced" or body_lines <= 0:
        return 0.0, [], False

    topic_name_low = str(topic["name"]).lower()
    aliases = topic.get("aliases") or []
    if isinstance(aliases, str):
        try:
            aliases = json.loads(aliases)
        except Exception:
            aliases = []
    topic_text = " ".join([topic_name_low, *(str(a).lower() for a in aliases)])
    topic_tokens = set(_slug_tokens(topic_text))

    rel_path = file_info["rel_path"]
    stem = Path(rel_path).stem
    stem_tokens = set(_slug_tokens(stem))
    code_concepts: list[str] = list(file_info.get("code_concepts") or [])
    filename_concepts: list[str] = list(file_info.get("filename_concepts") or [])
    symbols: list[str] = [s for s in (file_info.get("symbols") or []) if s not in {"main", "<iostream>"}]

    score = 0.0
    reasons: list[str] = []
    code_verified = False

    # 1. Check ACTUAL code-verified concepts inside the file!
    for concept_id in code_concepts:
        terms = _CONCEPT_TOPIC_TERMS.get(concept_id, ())
        matched_term = next(
            (term for term in terms if _phrase_in_text(term, topic_text)),
            None,
        )
        if not matched_term:
            continue

        is_fname_concept = concept_id in filename_concepts

        # Suppress ambient boilerplate signals when the file clearly practices a different specific topic
        if concept_id == "basics_compilation" and not is_fname_concept:
            if filename_concepts or len(code_concepts) > 1:
                continue
        if concept_id == "variables_data_types" and not is_fname_concept and filename_concepts:
            continue
        if concept_id == "operators_type_casting" and not is_fname_concept and filename_concepts:
            continue
        if concept_id == "input_output" and not is_fname_concept and filename_concepts:
            continue
        if concept_id == "control_flow" and not is_fname_concept and filename_concepts:
            if "control_flow" not in filename_concepts:
                continue

        code_verified = True
        if is_fname_concept:
            c_score = 0.94
            detail_sym = f" ({', '.join(symbols[:2])})" if symbols else ""
            reasons.append(
                f"verified {concept_id.replace('_', ' ')} code{detail_sym} in '{Path(rel_path).name}' ({body_lines} logic lines)"
            )
        else:
            c_score = 0.78
            reasons.append(
                f"code inside '{Path(rel_path).name}' implements {concept_id.replace('_', ' ')} ({body_lines} logic lines)"
            )
        if c_score > score:
            score = c_score

    # 2. Fallback ONLY for custom roadmap topics not covered by any built-in syntax rule:
    #    require BOTH filename/topic overlap AND matching identifier tokens in actual code
    #    (with string literals stripped so `cout << "no pointers here"` never fools it).
    has_builtin_rule_for_topic = any(
        any(_phrase_in_text(term, topic_text) for term in terms)
        for terms in _CONCEPT_TOPIC_TERMS.values()
    )
    if not code_verified and not has_builtin_rule_for_topic:
        stop = {"and", "the", "of", "in", "to", "with", "for", "cpp", "py", "java", "js", "my", "test", "main", "two", "numbers"}
        clean_stem_tokens = stem_tokens - stop
        clean_topic_tokens = topic_tokens - stop
        overlap = clean_stem_tokens & clean_topic_tokens
        if overlap:
            clean_body = _strip_comments_text(file_info.get("text") or "", file_info.get("language") or "")
            no_strings = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", clean_body)
            code_tokens = set(_slug_tokens(no_strings))
            if clean_topic_tokens & code_tokens:
                code_verified = True
                score = max(score, 0.72)
                reasons.append(
                    f"verified code tokens ({', '.join(sorted(clean_topic_tokens & code_tokens)[:3])}) in '{Path(rel_path).name}'"
                )

    if code_verified and file_info.get("has_compiled_artifact"):
        score = min(0.99, score + 0.04)

    return round(score, 3), reasons, code_verified


# ---------------------------------------------------------------------------
# Folder Link Management & Sync
# ---------------------------------------------------------------------------

def pick_local_folder(initial_dir: str | None = None) -> str | None:
    """Open a native OS folder selection window and return the chosen absolute path (or None if cancelled).

    Runs tkinter in an isolated short-lived subprocess so it always owns the main thread
    and never blocks or conflicts with FastAPI/uvicorn worker threads.
    """
    candidates = []
    if initial_dir and str(initial_dir).strip():
        p = Path(str(initial_dir).strip()).expanduser()
        if p.exists() and p.is_dir():
            candidates.append(p)
        elif p.parent.exists() and p.parent.is_dir():
            candidates.append(p.parent)
    home = Path.home()
    for default_dir in (home / "OneDrive" / "Desktop", home / "Desktop", home):
        if default_dir.exists() and default_dir.is_dir():
            candidates.append(default_dir)
            break
    start_dir = str(candidates[0]) if candidates else str(home)

    picker_script = (
        "import os, sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "try:\n"
        "    import ctypes\n"
        "    ctypes.windll.shcore.SetProcessDpiAwareness(1)\n"
        "except Exception:\n"
        "    pass\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "try:\n"
        "    root.attributes('-topmost', True)\n"
        "    root.lift()\n"
        "    root.focus_force()\n"
        "    root.update()\n"
        "except Exception:\n"
        "    pass\n"
        "init_dir = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else os.path.expanduser('~')\n"
        "chosen = filedialog.askdirectory(parent=root, title='Select Learning Code Folder', initialdir=init_dir, mustexist=True)\n"
        "root.destroy()\n"
        "if chosen:\n"
        "    sys.stdout.write(os.path.normpath(chosen))\n"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", picker_script, start_dir],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Folder picker timed out.") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not open folder picker dialog: {exc}") from exc

    if proc.returncode != 0:
        err_msg = (proc.stderr or "").strip()
        raise RuntimeError(f"Folder picker failed: {err_msg or 'unknown error'}")

    selected = (proc.stdout or "").strip()
    return selected or None


def open_folder_in_explorer(folder_path: str) -> None:
    """Open a linked folder in the OS file manager (Windows Explorer / Finder / xdg-open)."""
    resolved = Path(str(folder_path or "").strip()).expanduser()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"Folder does not exist: {folder_path}")
    if sys.platform.startswith("win"):
        os.startfile(str(resolved.resolve()))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(resolved.resolve())])
    else:
        subprocess.Popen(["xdg-open", str(resolved.resolve())])


def get_folder_link(roadmap_id: int) -> dict[str, Any] | None:
    with schema.connect() as conn:
        row = conn.execute(
            "SELECT * FROM learning_folders WHERE roadmap_id = ?",
            (roadmap_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["enabled"] = bool(item.get("enabled", 1))
    try:
        item["last_sync_summary"] = json.loads(item.get("last_sync_summary") or "{}")
    except Exception:
        item["last_sync_summary"] = {}
    return item


def list_folder_links() -> list[dict[str, Any]]:
    with schema.connect() as conn:
        rows = conn.execute(
            "SELECT lf.*, r.name AS roadmap_name "
            "FROM learning_folders AS lf "
            "JOIN roadmaps AS r ON r.id = lf.roadmap_id "
            "ORDER BY lf.id"
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item.get("enabled", 1))
        try:
            item["last_sync_summary"] = json.loads(item.get("last_sync_summary") or "{}")
        except Exception:
            item["last_sync_summary"] = {}
        results.append(item)
    return results


def link_folder_to_roadmap(
    roadmap_id: int,
    folder_path: str,
    *,
    enabled: bool = True,
    sync_now: bool = True,
    embed: Embedder | None = None,
) -> dict[str, Any]:
    """Validate and attach a local folder path to a roadmap, optionally syncing immediately."""
    cleaned = str(folder_path or "").strip().strip("\"'")
    if not cleaned:
        raise ValueError("Folder path cannot be empty.")
    resolved = Path(cleaned).expanduser()
    if not resolved.exists():
        raise ValueError(f"Folder does not exist: {cleaned}")
    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {cleaned}")
    abs_folder = str(resolved.resolve())

    with schema.connect() as conn:
        rm = conn.execute("SELECT id, name FROM roadmaps WHERE id = ?", (roadmap_id,)).fetchone()
        if rm is None:
            raise ValueError("Roadmap not found.")
        now = _now()
        existing = conn.execute(
            "SELECT id, folder_path FROM learning_folders WHERE roadmap_id = ?",
            (roadmap_id,),
        ).fetchone()
        if existing is not None:
            path_changed = existing["folder_path"] != abs_folder
            conn.execute(
                "UPDATE learning_folders SET folder_path = ?, enabled = ?, updated_at = ? "
                "WHERE roadmap_id = ?",
                (abs_folder, 1 if enabled else 0, now, roadmap_id),
            )
            if path_changed:
                _clear_roadmap_code_index(conn, roadmap_id)
        else:
            conn.execute(
                "INSERT INTO learning_folders (roadmap_id, folder_path, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (roadmap_id, abs_folder, 1 if enabled else 0, now, now),
            )

    link = get_folder_link(roadmap_id)
    sync_result = None
    if sync_now and enabled:
        sync_result = sync_roadmap_folder(roadmap_id, embed=embed)
        link = get_folder_link(roadmap_id)
    return {"folder": link, "sync": sync_result}


def unlink_folder_from_roadmap(roadmap_id: int) -> bool:
    with schema.connect() as conn:
        _clear_roadmap_code_index(conn, roadmap_id)
        cur = conn.execute("DELETE FROM learning_folders WHERE roadmap_id = ?", (roadmap_id,))
    return cur.rowcount > 0


def _clear_roadmap_code_index(conn: sqlite3.Connection, roadmap_id: int) -> None:
    try:
        conn.execute("DELETE FROM learning_code_chunks_fts WHERE roadmap_id = ?", (roadmap_id,))
    except sqlite3.OperationalError:
        pass
    conn.execute("DELETE FROM learning_code_chunks WHERE roadmap_id = ?", (roadmap_id,))
    conn.execute("DELETE FROM learning_code_files WHERE roadmap_id = ?", (roadmap_id,))
    conn.execute("DELETE FROM topic_code_evidence WHERE roadmap_id = ?", (roadmap_id,))


def _discover_source_files(root_folder: Path) -> list[Path]:
    discovered: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            try:
                if fpath.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            discovered.append(fpath)
    return discovered


def _upsert_file_chunks(
    conn: sqlite3.Connection,
    file_id: int,
    roadmap_id: int,
    rel_path: str,
    text: str,
    concepts: list[str],
    embed: Embedder | None = None,
) -> int:
    # Remove old chunks for this file
    old_ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM learning_code_chunks WHERE file_id = ?", (file_id,)
        ).fetchall()
    ]
    if old_ids:
        try:
            placeholders = ",".join("?" for _ in old_ids)
            conn.execute(
                f"DELETE FROM learning_code_chunks_fts WHERE chunk_id IN ({placeholders})",
                old_ids,
            )
        except sqlite3.OperationalError:
            pass
        conn.execute("DELETE FROM learning_code_chunks WHERE file_id = ?", (file_id,))

    chunks = _chunk_source_text(text, rel_path, concepts)
    for chunk in chunks:
        blob = None
        if embed is not None:
            try:
                vec = embed(f"{rel_path} {chunk['concepts']}\n{chunk['content'][:1000]}")
                if vec:
                    blob = numpy.asarray(vec, dtype=numpy.float32).tobytes()
            except Exception:
                blob = None
        cur = conn.execute(
            "INSERT INTO learning_code_chunks "
            "(file_id, roadmap_id, rel_path, chunk_index, start_line, end_line, content, concepts, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                roadmap_id,
                rel_path,
                chunk["chunk_index"],
                chunk["start_line"],
                chunk["end_line"],
                chunk["content"],
                chunk["concepts"],
                blob,
            ),
        )
        chunk_id = int(cur.lastrowid)
        try:
            conn.execute(
                "INSERT INTO learning_code_chunks_fts (chunk_id, roadmap_id, rel_path, concepts, content) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk_id, roadmap_id, rel_path, chunk["concepts"], chunk["content"]),
            )
        except sqlite3.OperationalError:
            pass
    return len(chunks)


def sync_roadmap_folder(
    roadmap_id: int,
    *,
    embed: Embedder | None = None,
    force_reanalyze: bool = False,
) -> dict[str, Any]:
    """Scan a roadmap's linked folder incrementally, update RAG index & topic suggestions."""
    folder_link = get_folder_link(roadmap_id)
    if folder_link is None:
        raise ValueError("No folder is linked to this roadmap.")
    root = Path(folder_link["folder_path"])
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Linked folder is missing or inaccessible: {folder_link['folder_path']}")

    roadmap = progress.get_roadmap(roadmap_id)
    if roadmap is None:
        raise ValueError("Roadmap not found.")

    prev_summary = folder_link.get("last_sync_summary")
    if isinstance(prev_summary, str):
        try:
            prev_summary = json.loads(prev_summary)
        except Exception:
            prev_summary = {}
    if not isinstance(prev_summary, dict):
        prev_summary = {}
    if int(prev_summary.get("analyzer_version") or 1) < ANALYZER_VERSION:
        force_reanalyze = True

    discovered_paths = _discover_source_files(root)
    discovered_rels = {p.relative_to(root).as_posix(): p for p in discovered_paths}
    now = _now()

    files_reindexed = 0
    files_removed = 0
    chunks_indexed = 0
    analyzed_files: list[dict[str, Any]] = []
    changed_rel_paths: set[str] = set()

    with schema.connect() as conn:
        existing_rows = {
            r["rel_path"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM learning_code_files WHERE roadmap_id = ?",
                (roadmap_id,),
            ).fetchall()
        }

        # Delete removed files
        for rel_path, old_row in list(existing_rows.items()):
            if rel_path not in discovered_rels:
                old_chunk_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM learning_code_chunks WHERE file_id = ?",
                        (old_row["id"],),
                    ).fetchall()
                ]
                if old_chunk_ids:
                    try:
                        placeholders = ",".join("?" for _ in old_chunk_ids)
                        conn.execute(
                            f"DELETE FROM learning_code_chunks_fts WHERE chunk_id IN ({placeholders})",
                            old_chunk_ids,
                        )
                    except sqlite3.OperationalError:
                        pass
                conn.execute("DELETE FROM learning_code_files WHERE id = ?", (old_row["id"],))
                files_removed += 1

        # Analyze ONLY new or changed files (fast mtime+size check avoids reading unchanged files!)
        for rel_path, fpath in discovered_rels.items():
            old = existing_rows.get(rel_path)
            ext = fpath.suffix.lower()
            has_compiled = any(
                fpath.with_suffix(c_ext).exists()
                for c_ext in COMPILED_ARTIFACT_EXTS
            ) if ext in {".cpp", ".cc", ".cxx", ".c", ".java"} else False

            stat = fpath.stat()
            mod_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if force_reanalyze:
                unchanged = False
            else:
                stat_unchanged = (
                    old is not None
                    and old["file_size"] == stat.st_size
                    and old["modified_at"] == mod_iso
                    and bool(old["has_compiled_artifact"]) == bool(has_compiled)
                )
                if not stat_unchanged and old is not None:
                    raw_bytes = fpath.read_bytes()
                    quick_hash = hashlib.sha256(raw_bytes).hexdigest()
                    unchanged = (
                        old["content_hash"] == quick_hash
                        and bool(old["has_compiled_artifact"]) == bool(has_compiled)
                    )
                else:
                    unchanged = stat_unchanged

            if unchanged and old is not None:
                try:
                    cached_concepts = json.loads(old.get("concepts_json") or "[]")
                except Exception:
                    cached_concepts = []
                try:
                    cached_symbols = json.loads(old.get("symbols_json") or "[]")
                except Exception:
                    cached_symbols = []
                stem_lower = fpath.stem.lower()
                stem_tokens = set(_slug_tokens(fpath.stem))
                rel_tokens = set(_slug_tokens(rel_path))
                fname_concepts = [
                    cid
                    for cid, fname_keys, _, _ in _CONCEPT_RULES
                    if any(
                        (k in stem_tokens) or (k in rel_tokens) or _phrase_in_text(k, stem_lower)
                        for k in fname_keys
                    )
                ]
                code_only = [c for c in cached_concepts if c not in fname_concepts] or (
                    cached_concepts if old["file_state"] == "practiced" else []
                )
                analyzed_files.append(
                    {
                        "id": old["id"],
                        "rel_path": old["rel_path"],
                        "abs_path": old["abs_path"],
                        "language": old["language"],
                        "content_hash": old["content_hash"],
                        "file_size": old["file_size"],
                        "line_count": old["line_count"],
                        "code_lines": old["code_lines"],
                        "body_lines": old["code_lines"] if old["file_state"] == "practiced" else 0,
                        "has_compiled_artifact": bool(old["has_compiled_artifact"]),
                        "file_state": old["file_state"],
                        "concepts": cached_concepts,
                        "code_concepts": cached_concepts if old["file_state"] == "practiced" else code_only,
                        "filename_concepts": fname_concepts,
                        "symbols": cached_symbols,
                        "summary": old["summary"],
                        "modified_at": old["modified_at"],
                        "text": "",
                        "is_changed": False,
                    }
                )
                continue

            info = analyze_source_file(fpath, root)
            info["is_changed"] = True
            changed_rel_paths.add(rel_path)

            if old is None:
                cur = conn.execute(
                    "INSERT INTO learning_code_files "
                    "(roadmap_id, rel_path, abs_path, language, content_hash, file_size, "
                    "line_count, code_lines, has_compiled_artifact, file_state, "
                    "concepts_json, symbols_json, summary, modified_at, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        roadmap_id,
                        info["rel_path"],
                        info["abs_path"],
                        info["language"],
                        info["content_hash"],
                        info["file_size"],
                        info["line_count"],
                        info["code_lines"],
                        1 if info["has_compiled_artifact"] else 0,
                        info["file_state"],
                        json.dumps(info["concepts"]),
                        json.dumps(info["symbols"]),
                        info["summary"],
                        info["modified_at"],
                        now,
                    ),
                )
                file_id = int(cur.lastrowid)
            else:
                file_id = int(old["id"])
                conn.execute(
                    "UPDATE learning_code_files SET abs_path = ?, language = ?, content_hash = ?, "
                    "file_size = ?, line_count = ?, code_lines = ?, has_compiled_artifact = ?, "
                    "file_state = ?, concepts_json = ?, symbols_json = ?, summary = ?, "
                    "modified_at = ?, indexed_at = ? WHERE id = ?",
                    (
                        info["abs_path"],
                        info["language"],
                        info["content_hash"],
                        info["file_size"],
                        info["line_count"],
                        info["code_lines"],
                        1 if info["has_compiled_artifact"] else 0,
                        info["file_state"],
                        json.dumps(info["concepts"]),
                        json.dumps(info["symbols"]),
                        info["summary"],
                        info["modified_at"],
                        now,
                        file_id,
                    ),
                )
            chunks_indexed += _upsert_file_chunks(
                conn,
                file_id,
                roadmap_id,
                info["rel_path"],
                info["text"],
                info["concepts"],
                embed=embed,
            )
            info["id"] = file_id
            files_reindexed += 1
            analyzed_files.append(info)

    # Match ONLY verified code content against roadmap topics (Suggest & Confirm — NEVER auto-complete!)
    topics = roadmap.get("topics") or []
    auto_started_topics: list[str] = []
    new_suggestions: list[dict[str, Any]] = []
    need_recheck_topics = bool(changed_rel_paths or files_removed)

    with schema.connect() as conn:
        existing_evidence = {
            int(r["topic_id"]): dict(r)
            for r in conn.execute(
                "SELECT * FROM topic_code_evidence WHERE roadmap_id = ?",
                (roadmap_id,),
            ).fetchall()
        }

        if need_recheck_topics:
            matched_topic_ids: set[int] = set()
            for topic in topics:
                t_id = int(topic["id"])
                matched_files: list[dict[str, Any]] = []
                best_score = 0.0
                best_reasons: list[str] = []

                for f_info in analyzed_files:
                    score, reasons, verified = _topic_match_score(topic, f_info)
                    if verified and score >= SUGGEST_CONFIDENCE_THRESHOLD:
                        matched_files.append(
                            {
                                "rel_path": f_info["rel_path"],
                                "file_state": f_info["file_state"],
                                "line_count": f_info["line_count"],
                                "body_lines": f_info.get("body_lines", f_info["code_lines"]),
                                "has_compiled_artifact": bool(f_info["has_compiled_artifact"]),
                                "score": score,
                                "changed": f_info["rel_path"] in changed_rel_paths,
                            }
                        )
                        if score > best_score:
                            best_score = score
                            best_reasons = reasons

                if not matched_files:
                    continue

                matched_topic_ids.add(t_id)
                matched_files.sort(key=lambda x: (x["score"], x["body_lines"]), reverse=True)
                file_names_csv = ", ".join(Path(m["rel_path"]).name for m in matched_files[:3])
                reason_text = best_reasons[0] if best_reasons else f"Verified code in {file_names_csv}"

                # 1. Suggest & Confirm rule:
                #    - NEVER auto-mark a topic 'completed'!
                #    - Move not_started/on_hold -> 'learning' ONLY when actual verified code exists.
                if topic["status"] in ("not_started", "on_hold"):
                    conn.execute(
                        "UPDATE topics SET status = 'learning', updated_at = ? WHERE id = ?",
                        (now, t_id),
                    )
                    auto_started_topics.append(topic["name"])
                    dup = conn.execute(
                        "SELECT id FROM learning_activities WHERE topic_id = ? AND task_id IS NULL AND kind = 'started' LIMIT 1",
                        (t_id,),
                    ).fetchone()
                    if dup is None:
                        conn.execute(
                            "INSERT INTO learning_activities (topic_id, task_id, kind, created_at) "
                            "VALUES (?, NULL, 'started', ?)",
                            (t_id, now),
                        )

                # 2. Upsert topic_code_evidence: if not already completed, create/re-open a
                #    'pending' suggestion asking the user whether to mark it done!
                prev = existing_evidence.get(t_id)
                has_changed_file = any(m["changed"] for m in matched_files)

                if topic["status"] == "completed":
                    desired_state = "confirmed"
                elif prev and prev["suggestion_state"] == "dismissed" and not has_changed_file:
                    desired_state = "dismissed"
                else:
                    desired_state = "pending"

                if prev is None:
                    cur_ev = conn.execute(
                        "INSERT INTO topic_code_evidence "
                        "(roadmap_id, topic_id, confidence, evidence_files, reason, suggestion_state, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            roadmap_id,
                            t_id,
                            best_score,
                            json.dumps(matched_files),
                            reason_text,
                            desired_state,
                            now,
                        ),
                    )
                    if desired_state == "pending":
                        new_suggestions.append(
                            {
                                "id": int(cur_ev.lastrowid),
                                "topic_id": t_id,
                                "topic_name": topic["name"],
                                "roadmap_name": roadmap["name"],
                                "files": file_names_csv,
                                "reason": reason_text,
                            }
                        )
                else:
                    was_pending = prev["suggestion_state"] == "pending"
                    conn.execute(
                        "UPDATE topic_code_evidence SET confidence = ?, evidence_files = ?, "
                        "reason = ?, suggestion_state = ?, updated_at = ? WHERE id = ?",
                        (
                            best_score,
                            json.dumps(matched_files),
                            reason_text,
                            desired_state,
                            now,
                            prev["id"],
                        ),
                    )
                    if desired_state == "pending" and (not was_pending or has_changed_file):
                        new_suggestions.append(
                            {
                                "id": int(prev["id"]),
                                "topic_id": t_id,
                                "topic_name": topic["name"],
                                "roadmap_name": roadmap["name"],
                                "files": file_names_csv,
                                "reason": reason_text,
                            }
                        )

            # Clean stale evidence for topics whose verified code was removed
            for old_tid, old_ev in existing_evidence.items():
                if old_tid not in matched_topic_ids:
                    conn.execute("DELETE FROM topic_code_evidence WHERE id = ?", (old_ev["id"],))

        # Reconcile any manually completed topics so stale 'pending' suggestions never linger
        conn.execute(
            "UPDATE topic_code_evidence SET suggestion_state = 'confirmed', updated_at = ? "
            "WHERE roadmap_id = ? AND suggestion_state = 'pending' "
            "AND topic_id IN (SELECT id FROM topics WHERE roadmap_id = ? AND status = 'completed')",
            (now, roadmap_id, roadmap_id),
        )

        practiced_count = sum(1 for f in analyzed_files if f["file_state"] == "practiced")
        wip_count = sum(1 for f in analyzed_files if f["file_state"] == "wip")
        empty_count = sum(1 for f in analyzed_files if f["file_state"] == "empty")
        pending_count = conn.execute(
            "SELECT COUNT(*) AS n FROM topic_code_evidence "
            "WHERE roadmap_id = ? AND suggestion_state = 'pending'",
            (roadmap_id,),
        ).fetchone()["n"]

        summary_payload = {
            "analyzer_version": ANALYZER_VERSION,
            "total_files": len(analyzed_files),
            "practiced_files": practiced_count,
            "wip_files": wip_count,
            "empty_files": empty_count,
            "files_reindexed": files_reindexed,
            "files_removed": files_removed,
            "auto_started_topics": auto_started_topics,
            "pending_suggestions": int(pending_count),
        }
        conn.execute(
            "UPDATE learning_folders SET last_synced_at = ?, last_sync_summary = ?, updated_at = ? "
            "WHERE roadmap_id = ?",
            (now, json.dumps(summary_payload), now, roadmap_id),
        )

    insights = get_roadmap_code_insights(roadmap_id)
    return {
        "roadmap_id": roadmap_id,
        "roadmap_name": roadmap["name"],
        "folder_path": folder_link["folder_path"],
        "synced_at": now,
        "files_reindexed": files_reindexed,
        "files_removed": files_removed,
        "chunks_indexed": chunks_indexed,
        "auto_started_topics": auto_started_topics,
        "new_suggestions": new_suggestions,
        **summary_payload,
        "friendly_summary": insights["friendly_summary"],
    }


def sync_all_linked_folders(embed: Embedder | None = None) -> list[dict[str, Any]]:
    """Incrementally sync every enabled linked learning folder."""
    results: list[dict[str, Any]] = []
    for link in list_folder_links():
        if not link.get("enabled", True):
            continue
        try:
            results.append(sync_roadmap_folder(int(link["roadmap_id"]), embed=embed))
        except Exception as exc:
            LOGGER.debug("Folder sync skipped for roadmap %s: %s", link["roadmap_id"], exc)
            results.append(
                {
                    "roadmap_id": int(link["roadmap_id"]),
                    "roadmap_name": link.get("roadmap_name", ""),
                    "folder_path": link["folder_path"],
                    "error": str(exc),
                }
            )
    return results


# ---------------------------------------------------------------------------
# Code Completion Suggestions (Confirm / Dismiss)
# ---------------------------------------------------------------------------

def list_code_suggestions(
    *,
    roadmap_id: int | None = None,
    state: str = "pending",
) -> list[dict[str, Any]]:
    clauses = ["e.suggestion_state = ?"]
    params: list[Any] = [state]
    if roadmap_id is not None:
        clauses.append("e.roadmap_id = ?")
        params.append(roadmap_id)
    # Only show pending suggestions for topics not already completed
    if state == "pending":
        clauses.append("t.status != 'completed'")

    with schema.connect() as conn:
        rows = conn.execute(
            "SELECT e.id, e.roadmap_id, e.topic_id, e.confidence, e.evidence_files, "
            "e.reason, e.suggestion_state, e.updated_at, "
            "t.name AS topic_name, t.status AS topic_status, r.name AS roadmap_name "
            "FROM topic_code_evidence AS e "
            "JOIN topics AS t ON t.id = e.topic_id "
            "JOIN roadmaps AS r ON r.id = e.roadmap_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY e.confidence DESC, e.updated_at DESC",
            params,
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["evidence_files"] = json.loads(item.get("evidence_files") or "[]")
        except Exception:
            item["evidence_files"] = []
        out.append(item)
    return out


def resolve_code_suggestion(
    suggestion_id: int,
    state: str,
) -> dict[str, Any]:
    """Confirm (marking topic completed) or dismiss a code-based completion suggestion."""
    if state not in ("confirmed", "dismissed"):
        raise ValueError("state must be 'confirmed' or 'dismissed'.")
    with schema.connect() as conn:
        row = conn.execute(
            "SELECT e.*, t.name AS topic_name, r.name AS roadmap_name "
            "FROM topic_code_evidence AS e "
            "JOIN topics AS t ON t.id = e.topic_id "
            "JOIN roadmaps AS r ON r.id = e.roadmap_id "
            "WHERE e.id = ?",
            (suggestion_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Code completion suggestion not found.")
        now = _now()
        conn.execute(
            "UPDATE topic_code_evidence SET suggestion_state = ?, updated_at = ? WHERE id = ?",
            (state, now, suggestion_id),
        )
    if state == "confirmed":
        progress.set_topic_status(int(row["topic_id"]), "completed")
    result = dict(row)
    result["suggestion_state"] = state
    try:
        result["evidence_files"] = json.loads(result.get("evidence_files") or "[]")
    except Exception:
        result["evidence_files"] = []
    return result


# ---------------------------------------------------------------------------
# Hybrid Code RAG Search (FTS5 BM25 + Lexical/Concept + Optional Embeddings)
# ---------------------------------------------------------------------------

_RAG_STOP_WORDS = {
    "what", "which", "where", "when", "why", "how", "is", "are", "was", "were",
    "the", "a", "an", "of", "to", "in", "on", "for", "with", "about", "from",
    "my", "me", "i", "you", "your", "did", "do", "have", "has", "code", "file",
    "files", "folder", "show", "check", "tell", "explain", "next", "give", "some",
    "till", "until", "so", "far", "like", "mean", "level", "please", "can", "could",
}


def _sanitize_fts_query(query: str) -> str:
    norm = _normalize_tech_query(query)
    raw = [t for t in re.findall(r"[A-Za-z0-9_]+", norm.lower()) if len(t) >= 2]
    meaningful = [t for t in raw if t not in _RAG_STOP_WORDS] or raw
    if not meaningful:
        return ""
    terms: list[str] = []
    seen: set[str] = set()
    for t in meaningful:
        for cand in (t, _stem_token(t)):
            if len(cand) >= 2 and cand not in seen:
                seen.add(cand)
                # Use prefix matching on tokens len >= 3 so 'loop' matches 'loops', 'for_loop', etc.
                terms.append(f'"{cand}"*' if len(cand) >= 3 else f'"{cand}"')
    return " OR ".join(terms[:12])


def _expand_query_terms(query: str) -> tuple[set[str], set[str]]:
    raw = set(_slug_tokens(query))
    stemmed = {_stem_token(t) for t in raw if _stem_token(t)}
    core_raw = (raw - _RAG_STOP_WORDS) or raw
    core = core_raw | {_stem_token(t) for t in core_raw if _stem_token(t)}
    expanded = set(core) | stemmed
    for group in _RAG_CONCEPT_EXPANSIONS:
        group_stemmed = group | {_stem_token(g) for g in group}
        if core & group_stemmed:
            expanded |= group
    return core, expanded


def _fuzzy_token_overlap(query_tokens: set[str], target_tokens: set[str]) -> float:
    """Typo-tolerant lexical match (including adjacent transpositions like 'whlie' -> 'while')."""
    unmatched_q = [t for t in query_tokens if len(t) >= 4 and t not in target_tokens]
    if not unmatched_q or not target_tokens:
        return 0.0
    try:
        from rapidfuzz.distance import DamerauLevenshtein
        sim_fn = lambda a, b: DamerauLevenshtein.normalized_similarity(a, b) * 100.0
    except Exception:
        try:
            from rapidfuzz import fuzz as _rf_fuzz
            sim_fn = _rf_fuzz.ratio
        except Exception:
            return 0.0
    cand_pool = [t for t in target_tokens if len(t) >= 3]
    if not cand_pool:
        return 0.0
    bonus = 0.0
    for qt in unmatched_q[:6]:
        best = max((sim_fn(qt, ct) for ct in cand_pool), default=0.0)
        if best >= 80.0:
            bonus += 0.24 * (best / 100.0)
    return min(0.48, bonus)


def _cosine_blob(query_vec: list[float], blob: bytes | None) -> float:
    if not blob:
        return 0.0
    try:
        arr = numpy.frombuffer(blob, dtype=numpy.float32)
        q = numpy.asarray(query_vec, dtype=numpy.float32)
        if arr.size != q.size or arr.size == 0:
            return 0.0
        denom = float(numpy.linalg.norm(q) * numpy.linalg.norm(arr))
        return float(numpy.dot(q, arr) / denom) if denom else 0.0
    except Exception:
        return 0.0


def search_code_rag(
    query: str,
    *,
    roadmap_id: int | None = None,
    limit: int = 5,
    embed: Embedder | None = None,
) -> list[dict[str, Any]]:
    """Hybrid RAG retrieval over indexed practice code chunks."""
    query = str(query or "").strip()
    if not query:
        return []

    core_terms, expanded_terms = _expand_query_terms(query)
    norm_phrase = re.sub(r"\s+", " ", _normalize_tech_query(query).lower()).strip()
    fts_query = _sanitize_fts_query(query)
    scored: dict[int, tuple[float, dict[str, Any]]] = {}

    with schema.connect() as conn:
        # 1. SQLite FTS5 BM25 retrieval (with stop-word filtering & prefix matching)
        if fts_query:
            try:
                sql = (
                    "SELECT c.id, c.roadmap_id, c.rel_path, c.start_line, c.end_line, "
                    "c.content, c.concepts, f.file_state, f.language, f.line_count, "
                    "r.name AS roadmap_name, bm25(learning_code_chunks_fts) AS bm25_score "
                    "FROM learning_code_chunks_fts "
                    "JOIN learning_code_chunks AS c ON c.id = learning_code_chunks_fts.chunk_id "
                    "JOIN learning_code_files AS f ON f.id = c.file_id "
                    "JOIN roadmaps AS r ON r.id = c.roadmap_id "
                    "WHERE learning_code_chunks_fts MATCH ?"
                )
                params: list[Any] = [fts_query]
                if roadmap_id is not None:
                    sql += " AND c.roadmap_id = ?"
                    params.append(roadmap_id)
                sql += " ORDER BY bm25_score LIMIT ?"
                params.append(max(limit * 3, 12))
                for row in conn.execute(sql, params).fetchall():
                    item = dict(row)
                    # SQLite bm25() returns negative scores (more negative = better)
                    bm25_raw = float(item.pop("bm25_score", 0.0) or 0.0)
                    fts_score = min(1.0, 0.35 + abs(bm25_raw) * 0.12)
                    scored[int(item["id"])] = (fts_score, item)
            except sqlite3.OperationalError:
                pass

        # 2. Stemmed + concept-expanded + typo-tolerant lexical + optional vector scan
        chunk_sql = (
            "SELECT c.id, c.roadmap_id, c.rel_path, c.start_line, c.end_line, "
            "c.content, c.concepts, c.embedding, f.file_state, f.language, f.line_count, "
            "r.name AS roadmap_name "
            "FROM learning_code_chunks AS c "
            "JOIN learning_code_files AS f ON f.id = c.file_id "
            "JOIN roadmaps AS r ON r.id = c.roadmap_id"
        )
        chunk_params: list[Any] = []
        if roadmap_id is not None:
            chunk_sql += " WHERE c.roadmap_id = ?"
            chunk_params.append(roadmap_id)

        query_vec = None
        if embed is not None:
            try:
                query_vec = embed(query)
            except Exception:
                query_vec = None

        for row in conn.execute(chunk_sql, chunk_params).fetchall():
            cid = int(row["id"])
            path_tokens = set(_slug_tokens(row["rel_path"]))
            path_stems = path_tokens | {_stem_token(t) for t in path_tokens}
            raw_haystack = set(_slug_tokens(f"{row['rel_path']} {row['concepts']} {row['content'][:1200]}"))
            haystack_tokens = raw_haystack | {_stem_token(t) for t in raw_haystack}

            exact_hits = len(core_terms & haystack_tokens)
            filename_hits = len(core_terms & path_stems)
            concept_hits = len(expanded_terms & haystack_tokens)
            fuzzy_bonus = _fuzzy_token_overlap(core_terms, haystack_tokens) if exact_hits == 0 else 0.0
            stem_space = re.sub(r"[_\-]+", " ", Path(row["rel_path"]).stem.lower()).strip()
            phrase_bonus = 0.35 if (len(stem_space) >= 3 and stem_space in norm_phrase) else 0.0

            lex_score = exact_hits * 0.24 + filename_hits * 0.22 + concept_hits * 0.09 + fuzzy_bonus + phrase_bonus
            vec_score = _cosine_blob(query_vec, row["embedding"]) if query_vec else 0.0
            combined_extra = lex_score + (vec_score * 0.65 if vec_score >= 0.30 else 0.0)

            if cid in scored:
                prev_score, prev_item = scored[cid]
                scored[cid] = (round(prev_score + combined_extra, 4), prev_item)
            elif combined_extra >= 0.16:
                item = dict(row)
                item.pop("embedding", None)
                scored[cid] = (round(combined_extra, 4), item)

    ranked = sorted(scored.values(), key=lambda pair: pair[0], reverse=True)[:limit]
    results: list[dict[str, Any]] = []
    for score, item in ranked:
        snippet = str(item["content"] or "")
        if len(snippet) > 700:
            snippet = snippet[:697].rstrip() + "..."
        results.append(
            {
                "chunk_id": int(item["id"]),
                "roadmap_id": int(item["roadmap_id"]),
                "roadmap_name": item["roadmap_name"],
                "rel_path": item["rel_path"],
                "start_line": int(item["start_line"]),
                "end_line": int(item["end_line"]),
                "language": item["language"],
                "file_state": item["file_state"],
                "concepts": item["concepts"],
                "snippet": snippet,
                "score": round(float(score), 3),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Insights & Friendly Companion Recap
# ---------------------------------------------------------------------------

def get_roadmap_code_insights(roadmap_id: int) -> dict[str, Any]:
    """Return full code-tracking state and a warm friend-like progress recap for a roadmap."""
    roadmap = progress.get_roadmap(roadmap_id)
    if roadmap is None:
        raise ValueError("Roadmap not found.")
    folder_link = get_folder_link(roadmap_id)

    with schema.connect() as conn:
        file_rows = conn.execute(
            "SELECT * FROM learning_code_files WHERE roadmap_id = ? "
            "ORDER BY modified_at DESC, rel_path ASC",
            (roadmap_id,),
        ).fetchall()
        evidence_rows = conn.execute(
            "SELECT e.*, t.name AS topic_name, t.status AS topic_status "
            "FROM topic_code_evidence AS e "
            "JOIN topics AS t ON t.id = e.topic_id "
            "WHERE e.roadmap_id = ? "
            "ORDER BY e.confidence DESC",
            (roadmap_id,),
        ).fetchall()

    files: list[dict[str, Any]] = []
    for row in file_rows:
        item = dict(row)
        item["has_compiled_artifact"] = bool(item.get("has_compiled_artifact"))
        try:
            item["concepts"] = json.loads(item.pop("concepts_json", "[]") or "[]")
        except Exception:
            item["concepts"] = []
        try:
            item["symbols"] = json.loads(item.pop("symbols_json", "[]") or "[]")
        except Exception:
            item["symbols"] = []
        files.append(item)

    evidence_by_topic: dict[int, dict[str, Any]] = {}
    pending_suggestions: list[dict[str, Any]] = []
    for row in evidence_rows:
        ev = dict(row)
        try:
            ev["evidence_files"] = json.loads(ev.get("evidence_files") or "[]")
        except Exception:
            ev["evidence_files"] = []
        evidence_by_topic[int(ev["topic_id"])] = ev
        if ev["suggestion_state"] == "pending" and ev["topic_status"] != "completed":
            pending_suggestions.append(ev)

    topics = roadmap.get("topics") or []
    completed_topics = [t["name"] for t in topics if t["status"] == "completed"]
    in_progress_topics = [t["name"] for t in topics if t["status"] == "learning"]
    next_items = progress.next_topics(limit=3, roadmap_id=roadmap_id)

    practiced_files = [f for f in files if f["file_state"] == "practiced"]
    wip_files = [f for f in files if f["file_state"] in ("empty", "wip")]
    empty_files = [f for f in files if f["file_state"] == "empty"]

    friendly = _compose_friendly_recap(
        roadmap_name=roadmap["name"],
        total_topics=len(topics),
        completed_topics=completed_topics,
        in_progress_topics=in_progress_topics,
        practiced_files=practiced_files,
        empty_files=empty_files,
        wip_files=wip_files,
        pending_suggestions=pending_suggestions,
        next_items=next_items,
    )

    return {
        "roadmap_id": roadmap_id,
        "roadmap_name": roadmap["name"],
        "folder": folder_link,
        "files": files,
        "practiced_count": len(practiced_files),
        "wip_count": len(wip_files),
        "empty_count": len(empty_files),
        "wip_files": [f["rel_path"] for f in wip_files],
        "empty_files": [f["rel_path"] for f in empty_files],
        "recent_files": [f["rel_path"] for f in practiced_files[:5]],
        "evidence_by_topic": evidence_by_topic,
        "pending_suggestions": pending_suggestions,
        "completed_topics": completed_topics,
        "in_progress_topics": in_progress_topics,
        "next_topics": next_items,
        "friendly_summary": friendly,
    }


def _compose_friendly_recap(
    *,
    roadmap_name: str,
    total_topics: int,
    completed_topics: list[str],
    in_progress_topics: list[str],
    practiced_files: list[dict[str, Any]],
    empty_files: list[dict[str, Any]],
    wip_files: list[dict[str, Any]],
    pending_suggestions: list[dict[str, Any]],
    next_items: list[dict[str, Any]],
) -> str:
    """Build a warm, friend-like status recap of what's coded and what's next."""
    parts: list[str] = []
    done_n = len(completed_topics)

    if practiced_files:
        recent_names = ", ".join(f"`{Path(f['rel_path']).name}`" for f in practiced_files[:3])
        if done_n > 0:
            parts.append(
                f"Nice momentum on **{roadmap_name}** — you've completed **{done_n}/{total_topics}** topics "
                f"and practiced {len(practiced_files)} code file{'s' if len(practiced_files) != 1 else ''} "
                f"(recent: {recent_names})."
            )
        else:
            parts.append(
                f"I spotted {len(practiced_files)} practiced code file{'s' if len(practiced_files) != 1 else ''} "
                f"in your **{roadmap_name}** folder ({recent_names})."
            )
    elif done_n > 0:
        parts.append(
            f"You're at **{done_n}/{total_topics}** completed topics in **{roadmap_name}**."
        )
    else:
        parts.append(
            f"Your **{roadmap_name}** folder is linked and ready — as soon as you start coding files there, I'll track your progress automatically."
        )

    if empty_files:
        empty_list = ", ".join(f"`{Path(f['rel_path']).name}`" for f in empty_files[:2])
        parts.append(
            f"Heads up — you created {empty_list} but {'they are' if len(empty_files) > 1 else 'it is'} still empty, so finishing that up is a great quick win."
        )
    elif wip_files:
        wip_list = ", ".join(f"`{Path(f['rel_path']).name}`" for f in wip_files[:2])
        parts.append(f"Looks like {wip_list} is still a work in progress.")

    if pending_suggestions:
        sugg_names = ", ".join(f"**{s['topic_name']}**" for s in pending_suggestions[:3])
        parts.append(
            f"Based on your code, {sugg_names} look{'s' if len(pending_suggestions) == 1 else ''} ready to mark completed — want me to confirm {'it' if len(pending_suggestions) == 1 else 'them'}?"
        )

    if next_items:
        nxt = next_items[0]
        if empty_files:
            parts.append(f"Right after that, **{nxt['name']}** is lined up next in your roadmap.")
        else:
            parts.append(f"Up next in your roadmap: **{nxt['name']}**.")

    return " ".join(parts)


_CODE_OR_LEARNING_CUE_RE = re.compile(
    r"(?<![a-z0-9])c\s*\+\s*\+(?![a-z0-9])"
    r"|(?<![a-z0-9])c\s*#(?![a-z0-9])"
    r"|\bc\s+plus\s+plus\b"
    r"|\b(?:code|coding|coded|folder|file|files|cpp|dsa|algorithm\w*|data\s+structures?|"
    r"loop\w*|while|for|if|else|ternary|switch|operator\w*|cast\w*|input|output|variable\w*|"
    r"function\w*|array\w*|string\w*|pointer\w*|class(?:es)?|oop\w*|recursion|sorting|searching|"
    r"learn(?:ed|t|ing)?|stud(?:y|ied|ying)|roadmap\w*|topic\w*|progress|completed|next|"
    r"practice\w*|problem\w*|question\w*|exercise\w*|interview\w*|quiz|leetcode|"
    r"bug|error|review|wrote|written|python|java|javascript|typescript|rust|sql|react)\b",
    re.IGNORECASE,
)


def _build_roadmap_progress_grounding(prompt_and_history: str) -> list[str]:
    """Summarize exact COMPLETED vs. IN-PROGRESS vs. NOT-YET-LEARNED topics for grounded practice/advice."""
    try:
        roadmaps = progress.roadmap_summaries()
    except Exception:
        return []
    if not roadmaps:
        return []

    norm_text = _normalize_tech_query(prompt_and_history).lower()
    text_tokens = set(_slug_tokens(norm_text))
    selected: list[dict[str, Any]] = []
    for rm in roadmaps:
        rm_tokens = set(_slug_tokens(rm.get("name") or ""))
        done_cnt = int(rm.get("completed_count") or rm.get("completed_topics") or 0)
        prog_cnt = int(rm.get("in_progress_count") or rm.get("in_progress_topics") or 0)
        if (rm_tokens & text_tokens) or done_cnt > 0 or prog_cnt > 0:
            selected.append(rm)
    if not selected:
        return []

    # Prefer roadmaps explicitly mentioned in the conversation first
    selected.sort(
        key=lambda r: (
            len(set(_slug_tokens(r.get("name") or "")) & text_tokens),
            int(r.get("completed_count") or 0) + int(r.get("in_progress_count") or 0),
        ),
        reverse=True,
    )

    lines: list[str] = ["User's exact learning roadmap progress (GROUND TRUTH):"]
    with schema.connect() as conn:
        for rm in selected[:3]:
            rows = conn.execute(
                "SELECT name, status FROM topics WHERE roadmap_id = ? ORDER BY position, id",
                (int(rm["id"]),),
            ).fetchall()
            if not rows:
                continue
            completed = [r["name"] for r in rows if r["status"] == "completed"]
            in_prog = [r["name"] for r in rows if r["status"] in ("learning", "in_progress")]
            not_started = [r["name"] for r in rows if r["status"] == "not_started"]
            lines.append(f"- Roadmap '{rm['name']}' ({len(completed)}/{len(rows)} completed):")
            lines.append(
                "  * COMPLETED (user HAS learned ONLY these): "
                + (", ".join(completed) if completed else "none yet")
            )
            if in_prog:
                lines.append("  * IN PROGRESS (currently practicing): " + ", ".join(in_prog))
            if not_started:
                preview = ", ".join(not_started[:8])
                suffix = f" (+{len(not_started) - 8} more)" if len(not_started) > 8 else ""
                lines.append(f"  * NOT YET LEARNED (do NOT assume user knows these): {preview}{suffix}")
    lines.append(
        "STRICT LEVEL RULE: If the user asks for practice problems, DSA questions, interview-level questions, "
        "or exercises based on what they have learned so far, ONLY give problems solvable with their COMPLETED "
        "and IN PROGRESS topics above. NEVER give problems requiring topics listed under NOT YET LEARNED "
        "(for instance, if Arrays/Linked Lists/Trees/Graphs/DP are NOT YET LEARNED, only give logic, math, "
        "conditionals, loops, bitwise/operator, and pattern problems using what they actually know)."
    )
    return lines


def build_rag_prompt_context(
    prompt: str,
    *,
    embed: Embedder | None = None,
    limit: int = 3,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Build compact grounded RAG + roadmap progress context for LLM chat turns about code/learning."""
    if not schema.is_initialized():
        return ""
    links = list_folder_links()

    # Include last 2 conversation turns so follow-ups like "I mean like the interview level" stay grounded!
    recent_tail = " ".join(
        str(m.get("content") or "")[:300]
        for m in (history or [])[-4:]
        if m.get("role") in ("user", "assistant")
    )
    combined_text = f"{prompt} {recent_tail}".strip()

    roadmap_tokens = set()
    for link in links:
        roadmap_tokens.update(_slug_tokens(link.get("roadmap_name") or ""))
    combined_tokens = set(_slug_tokens(combined_text))
    has_code_cue = bool(_CODE_OR_LEARNING_CUE_RE.search(combined_text)) or bool(combined_tokens & roadmap_tokens)
    if not has_code_cue:
        return ""

    lines: list[str] = _build_roadmap_progress_grounding(combined_text)

    if links:
        lines.append("Linked learning code folders & practice files:")
        for link in links[:3]:
            try:
                ins = get_roadmap_code_insights(int(link["roadmap_id"]))
                practiced_names: list[str] = []
                for f in (ins.get("recent_files") or []):
                    if isinstance(f, dict):
                        if f.get("file_state") == "practiced" and f.get("rel_path"):
                            practiced_names.append(Path(str(f["rel_path"])).name)
                    elif isinstance(f, str) and f.strip():
                        practiced_names.append(Path(f).name)
                practiced_names = practiced_names[:8]
                line = (
                    f"- {ins['roadmap_name']} ({link['folder_path']}): "
                    f"{ins['practiced_count']} practiced files"
                )
                if practiced_names:
                    line += f" ({', '.join(practiced_names)})"
                if ins["empty_files"]:
                    line += f", empty/unstarted files: {', '.join(ins['empty_files'][:3])}"
                if ins["pending_suggestions"]:
                    s_names = ", ".join(s["topic_name"] for s in ins["pending_suggestions"][:3])
                    line += f", suggested completed (awaiting user confirm): {s_names}"
                if ins["next_topics"]:
                    line += f", next topic: {ins['next_topics'][0]['name']}"
                lines.append(line)
            except Exception:
                continue

        hits = search_code_rag(prompt, limit=limit, embed=embed)
        if not hits and recent_tail:
            hits = search_code_rag(combined_text[:300], limit=limit, embed=embed)
        if hits:
            lines.append("Relevant code snippets from the user's learning folder (RAG):")
            for hit in hits:
                lines.append(
                    f"--- {hit['rel_path']} (L{hit['start_line']}-L{hit['end_line']}, {hit['file_state']}) ---\n"
                    f"{hit['snippet'][:420]}"
                )
    return "\n".join(lines)
