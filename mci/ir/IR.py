import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
import numpy.typing as npt

from . import custom_parsers

Language = Literal[
    "c",
    "cpp",
    "c_sharp",
    "java",
    "javascript",
    "lean",
    "ocaml",
    "python",
    "rescript",
    "typescript",
    "tsx",
    "ruby",
]
# e.g. ("A", "B", "foo") for function foo inside class B inside class A
QualifiedId = str
Pos = Tuple[int, int]  # (line, column)
Range = Tuple[Pos, Pos]  # ((start_line, start_column), (end_line, end_column))
Substring = Tuple[int, int]  # (start_byte, end_byte)
Scope = str  # e.g. "A.B." for class B inside class A
Vector = npt.NDArray[np.float32]  # for embeddings


@dataclass
class Code:
    bytes: bytes

    def __str__(self):
        return self.bytes.decode()

    __repr__ = __str__

    def apply_edit(self, edit: "CodeEdit") -> "Code":
        return edit.apply(self)

    def apply_edits(self, edits: List["CodeEdit"]) -> "Code":
        code = self
        # sort the edits in descending order of their start position
        edits.sort(key=lambda x: -x.substring[0])
        for edit in edits:
            code = code.apply_edit(edit)
        return code


@dataclass
class CodeEdit:
    substring: Substring
    new_bytes: bytes

    def apply(self, code: Code) -> Code:
        start, end = self.substring
        return Code(code.bytes[:start] + self.new_bytes + code.bytes[end:])


Expression = str


@dataclass
class Block(List["Symbol"]):
    pass

    def __str__(self) -> str:
        return f"{[x.name for x in self]}"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class Case:
    guard: "Symbol"
    body: "Symbol"

    def __str__(self) -> str:
        return f"Case({self.guard.name}, {self.body.name})"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class Import:
    names: List[str]  # import foo, bar, baz
    substring: Substring  # the substring of the document that corresponds to this import
    module_name: Optional[str] = None  # from module_name import ...


@dataclass
class Type:
    kind: Literal[
        "array", "constructor", "function", "pointer", "record", "reference", "type_of", "unknown"
    ]
    arguments: List["Type"] = field(default_factory=list)
    fields: List["Field"] = field(default_factory=list)
    name: Optional[str] = None

    def array(self) -> "Type":
        return Type(kind="array", arguments=[self])

    @staticmethod
    def constructor(name: str, arguments: Optional[List["Type"]] = None) -> "Type":
        if arguments is None:
            arguments = []
        return Type(kind="constructor", name=name, arguments=arguments)

    def function(self) -> "Type":
        return Type(kind="function")

    def pointer(self) -> "Type":
        return Type(kind="pointer", arguments=[self])

    @staticmethod
    def record(fields: List["Field"]) -> "Type":
        return Type(kind="record", fields=fields)

    def reference(self) -> "Type":
        return Type(kind="reference", arguments=[self])

    def type_of(self) -> "Type":
        return Type(kind="type_of", arguments=[self])

    @staticmethod
    def unknown(s: str) -> "Type":
        return Type(kind="unknown", name=s)

    def __str__(self) -> str:
        if self.kind == "array":
            return f"{self.arguments[0]}[]"
        elif self.kind == "constructor":
            if self.arguments != []:
                return f"{self.name}<{', '.join([str(arg) for arg in self.arguments])}>"
            else:
                return self.name or "unknown"
        elif self.kind == "function":
            return f"{self.arguments[0]}()"
        elif self.kind == "pointer":
            return f"{self.arguments[0]}*"
        elif self.kind == "record":
            return f"{{{', '.join([str(field) for field in self.fields])}}}"
        elif self.kind == "reference":
            return f"{self.arguments[0]}&"
        elif self.kind == "type_of":
            return f"typeof({self.arguments[0]})"
        elif self.kind == "unknown":
            return self.name or "unknown"
        else:
            raise Exception(f"Unknown type kind: {self.kind}")

    __repr__ = __str__


@dataclass
class Field:
    name: str
    optional: bool
    type: Type

    def __str__(self) -> str:
        res = self.name
        if self.optional:
            res += "?"
        res += f": {self.type}"
        return res

    __repr__ = __str__


@dataclass
class Parameter:
    name: str
    default_value: Optional[str] = None
    type: Optional[Type] = None
    optional: bool = False

    def __str__(self) -> str:
        res = self.name
        if self.optional:
            res += "?"
        if self.type is not None:
            res = res + f":{self.type}"
        if self.default_value is not None:
            res = res + f"={self.default_value}"
        return res

    __repr__ = __str__


SymbolKindName = Literal[
    "Body",
    "Call",
    "Class",
    "Def",
    "Expression",
    "File",
    "Function",
    "Guard",
    "If",
    "Interface",
    "Module",
    "Namespace",
    "Section",
    "Structure",
    "Theorem",
    "TypeDefinition",
    "Unknown",
    "Value",
]


@dataclass
class SymbolKind(ABC):
    """Abstract class for symbol kinds."""

    @abstractmethod
    def name(self) -> SymbolKindName:
        raise NotImplementedError

    def dump(self, lines: List[str]) -> None:
        pass

    def signature(self) -> Optional[str]:
        return None


@dataclass
class MetaSymbolKind(SymbolKind):
    """
    Represents a synthetic or structural symbol in the program.

    These symbols are not derived directly from the source code but are introduced
    during the parsing or analysis process. They are primarily used to represent
    unnamed or implicit constructs, such as control structures and intermediate
    transformations.
    """

    pass


@dataclass
class BodyKind(MetaSymbolKind):
    """Represents the body of a branch in the intermediate representation (IR).

    Attributes:
        block (Block): The block of code that makes up the body of the branch.
    """

    block: Block

    def name(self) -> SymbolKindName:
        return "Body"

    def dump(self, lines: List[str]) -> None:
        lines.append(f"   block: {self.block}")

    def __str__(self) -> str:
        return f"{self.block}"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class CallKind(MetaSymbolKind):
    """
    Represents a function call in the intermediate representation (IR) of the Rift engine.
    """

    function_name: str
    arguments: List[Expression]

    def name(self) -> SymbolKindName:
        return "Call"

    def dump(self, lines: List[str]) -> None:
        lines.append(f"   function_name: {self.function_name}")
        if self.arguments != []:
            lines.append(f"   arguments: {self.arguments}")

    def __str__(self) -> str:
        return f"{self.function_name}({', '.join(self.arguments)})"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class ClassKind(SymbolKind):
    """
    Represents a class in the program's intermediate representation.
    """

    superclasses: Optional[str]

    def name(self) -> SymbolKindName:
        return "Class"

    def signature(self) -> Optional[str]:
        if self.superclasses is not None:
            return self.superclasses


@dataclass
class DefKind(SymbolKind):
    """
    Represents a mathematical definition in Lean: https://leanprover.github.io/lean4/doc/definitions.html
    """

    def name(self) -> SymbolKindName:
        return "Def"


@dataclass
class ExpressionKind(MetaSymbolKind):
    """Represents an expression statement in the intermediate representation (IR) of the Rift engine.

    Attributes:
        code (str): The code string that represents the expression.
    """

    code: str

    def name(self) -> SymbolKindName:
        return "Expression"

    def dump(self, lines: List[str]) -> None:
        lines.append(f"   code: {self.code}")

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class FileKind(MetaSymbolKind):
    """
    Represents a file in the IR.
    """

    def name(self) -> SymbolKindName:
        return "File"


@dataclass
class FunctionKind(SymbolKind):
    """Represents a function symbol in the intermediate representation (IR) of the Rift engine.

    Attributes:
        has_return (bool): Whether the function has a return statement in its body.
        parameters (List[Parameter]): The list of parameters of the function.
        return_type (Optional[Type]): The return type of the function, if any.
    """

    has_return: bool
    parameters: List[Parameter]
    return_type: Optional[Type] = None

    def name(self) -> SymbolKindName:
        return "Function"

    def dump(self, lines: List[str]) -> None:
        if self.parameters != []:
            lines.append(f"   parameters: {self.parameters}")
        if self.return_type is not None:
            lines.append(f"   return_type: {self.return_type}")
        if self.has_return:
            lines.append(f"   has_return: {self.has_return}")


@dataclass
class GuardKind(MetaSymbolKind):
    """Guard of a conditional"""

    condition: Expression

    def name(self) -> SymbolKindName:
        return "Guard"

    def dump(self, lines: List[str]) -> None:
        lines.append(f"   condition: {self.condition}")

    def __str__(self) -> str:
        return self.condition

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class IfKind(MetaSymbolKind):
    """A symbol kind representing an if statement.

    Attributes:
        if_case (Case): The if case of the statement.
        elif_cases (List[Case]): The elif cases of the statement.
        else_body (Optional[Symbol]): The else body of the statement, if any.
    """

    if_case: Case
    elif_cases: List[Case]
    else_body: Optional["Symbol"]

    def name(self) -> SymbolKindName:
        return "If"

    def dump(self, lines: List[str]) -> None:
        lines.append(f"   if_case: {self.if_case}")
        if self.elif_cases != []:
            lines.append(f"   elif_cases: {self.elif_cases}")
        if self.else_body:
            lines.append(f"   else_body: {self.else_body.name}")

    def __str__(self) -> str:
        if_str = f"if {self.if_case.guard.name}: {self.if_case.body.name}"
        elif_str = "".join(
            [f" elif {case.guard.name}: {case.body.name}" for case in self.elif_cases]
        )
        else_str = f" else: {self.else_body.name}" if self.else_body else ""
        return f"{if_str}{elif_str}{else_str}"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class InterfaceKind(SymbolKind):
    """
    Represents a kind of symbol that defines an interface.
    """

    def name(self) -> SymbolKindName:
        return "Interface"


@dataclass
class ModuleKind(SymbolKind):
    """
    Represents a module in the IR.
    """

    def name(self) -> SymbolKindName:
        return "Module"


@dataclass
class NamespaceKind(SymbolKind):
    """
    Represents a namespace in the IR.
    """

    def name(self) -> SymbolKindName:
        return "Namespace"


@dataclass
class SectionKind(SymbolKind):
    """Represents a Lean section: https://leanprover.github.io/lean4/doc/sections.html"""

    def name(self) -> SymbolKindName:
        return "Section"


@dataclass
class StructureKind(SymbolKind):
    """
    Represents a structure in Lean: https://lean-lang.org/lean4/doc/struct.html
    """

    def name(self) -> SymbolKindName:
        return "Structure"


@dataclass
class TheoremKind(SymbolKind):
    """
    Represents a theorem in Lean: https://lean-lang.org/theorem_proving_in_lean4/title_page.html
    """

    def name(self) -> SymbolKindName:
        return "Theorem"


@dataclass
class TypeDefinitionKind(SymbolKind):
    """
    Represents a type definition in the IR.
    """

    type: Optional[Type] = None

    def name(self) -> SymbolKindName:
        return "TypeDefinition"

    def dump(self, lines: List[str]) -> None:
        if self.type is not None:
            lines.append(f"   type: {self.type}")

    def __str__(self) -> str:
        if self.type is None:
            return f"{self.name()}"
        else:
            return f"{self.type}"


@dataclass
class UnknownKind(MetaSymbolKind):
    """
    Represents an unknown symbol kind.
    """

    def name(self) -> SymbolKindName:
        return "Unknown"


@dataclass
class ValueKind(SymbolKind):
    """
    Represents a value in the IR
    """

    type: Optional[Type] = None

    def name(self) -> SymbolKindName:
        return "Value"

    def dump(self, lines: List[str]) -> None:
        if self.type is not None:
            lines.append(f"   type: {self.type}")


@dataclass
class Symbol:
    """Class for symbol information.

    Attributes:
        body (Block): The body of the symbol.
        body_sub (Optional[Substring]): The substring of the document that corresponds to the body of the symbol.
        code (Code): The code object that contains the symbol.
        docstring_sub (Optional[Substring]): The substring of the document that corresponds to the docstring of the symbol.
        exported (bool): Whether the symbol is exported.
        language (Language): The language of the symbol.
        name (str): The name of the symbol.
        range (Range): The range of the symbol.
        parent (Optional[Symbol]): The parent symbol in terms of control flow.
        scope (Scope): The scope of the symbol.
        substring (Substring): The substring of the document that corresponds to the symbol.
        symbol_kind (SymbolKind): The kind of the symbol.
        embedding (Optional[Vector]): The vector embedding of the symbol.
    """

    body: Block
    body_sub: Optional[Substring]
    code: Code
    docstring_sub: Optional[Substring]
    exported: bool
    language: Language
    name: str
    range: Range
    parent: Optional["Symbol"]
    scope: Scope
    substring: Substring
    symbol_kind: SymbolKind
    embedding: Optional[Vector] = None

    def get_substring(self) -> bytes:
        """Returns the substring of the document that corresponds to this symbol info."""
        start, end = self.substring
        return self.code.bytes[start:end]

    def get_qualified_id(self) -> QualifiedId:
        """
        Returns the qualified identifier of the IR node, which is the concatenation of its scope and name.
        """
        return self.scope + self.name

    def get_substring_without_body(self) -> bytes:
        """
        Returns a substring of the code bytes that excludes the body of the IR node.
        If the body_sub attribute is None, returns the full substring of the IR node.
        """
        if self.body_sub is None:
            return self.get_substring()
        else:
            start, _end = self.substring
            body_start, _body_end = self.body_sub
            return self.code.bytes[start:body_start]

    @property
    def docstring(self) -> Optional[str]:
        """
        Returns the docstring of the IR object if it exists, otherwise returns None.
        """
        if self.docstring_sub is None:
            return None
        else:
            start, end = self.docstring_sub
            return self.code.bytes[start:end].decode()

    def dump(self, lines: List[str]) -> None:
        """
        Appends a string representation of the IR node to the given list of strings.

        Args:
            lines (List[str]): The list of strings to append the string representation to.
        """
        signature = self.symbol_kind.signature()
        if signature is not None:
            id = self.name + signature
        else:
            id = self.name
        lines.append(
            f"{self.kind()}: {id}\n   language: {self.language}\n   range: {self.range}\n   substring: {self.substring}"
        )
        if self.scope != "":
            lines.append(f"   scope: {self.scope}")
        if self.docstring_sub is not None:
            lines.append(f"   docstring: {self.docstring}")
        if self.exported:
            lines.append(f"   exported: {self.exported}")
        if self.body_sub is not None:
            lines.append(f"   body_sub: {self.body_sub}")
        if self.body != []:
            lines.append(f"   body: {self.body}")
        if self.parent:
            lines.append(f"   parent: {self.parent.get_qualified_id()}")
        self.symbol_kind.dump(lines)

    def kind(self) -> str:
        return self.symbol_kind.name()


def create_file_symbol(code: Code, language: Language, path: str) -> Symbol:
    # For body_sub
    start_byte = 0
    end_byte = len(code.bytes) - 1
    body_sub = (start_byte, end_byte)

    # For range
    first_line = 0
    last_line = code.bytes.count(b"\n")
    if code.bytes.endswith(b"\n"):
        last_line -= 1  # Adjust for the last line if it ends with a newline
    last_newline_pos = code.bytes.rfind(b"\n", 0, end_byte - 1)
    if last_newline_pos == -1:  # If there's no newline, the entire content is a single line
        last_char_in_line = end_byte
    else:
        last_char_in_line = end_byte - last_newline_pos - 1
    range = ((first_line, 0), (last_line, last_char_in_line))

    return Symbol(
        body=Block(),
        body_sub=body_sub,
        code=code,
        docstring_sub=None,
        exported=False,
        language=language,
        name=path,
        parent=None,
        range=range,
        scope="",
        substring=body_sub,
        symbol_kind=FileKind(),
    )


@dataclass
class File:
    """
    Represents a file with associated metadata.

    Attributes:
    - path: Path of the file relative to the root directory.
    - statements: Top-level statements in the file.
    - _imports: Imports present in the file.
    - _symbol_table: Symbol table for all symbols in the file.
    """

    code: Code
    path: str
    symbol: Optional[Symbol] = None
    _imports: List[Import] = field(default_factory=list)
    _symbol_table: Dict[QualifiedId, Symbol] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = create_file_symbol(code=self.code, language="python", path=self.path)
        self.add_symbol(self.symbol)

    def lookup_symbol(self, qid: QualifiedId) -> Optional[Symbol]:
        return self._symbol_table.get(qid)

    def search_symbol(self, name: Union[str, Callable[[str], bool]]) -> List[Symbol]:
        if callable(name):
            name_filter = name
            return [symbol for symbol in self._symbol_table.values() if name_filter(symbol.name)]
        else:
            return [symbol for symbol in self._symbol_table.values() if symbol.name == name]

    def search_module_import(self, module_name: str) -> Optional[Import]:
        for import_ in self._imports:
            if import_.module_name == module_name:
                return import_
        return None

    def add_symbol(self, symbol: Symbol) -> None:
        if symbol.parent:
            symbol.parent.body.append(symbol)
        self._symbol_table[symbol.get_qualified_id()] = symbol

    def add_import(self, import_: Import) -> None:
        self._imports.append(import_)

    def get_function_declarations(self) -> List[Symbol]:
        return [
            symbol
            for symbol in self._symbol_table.values()
            if isinstance(symbol.symbol_kind, FunctionKind)
        ]

    def dump_symbol_table(self, lines: List[str]) -> None:
        for _, symbol in self._symbol_table.items():
            if not isinstance(symbol.symbol_kind, UnknownKind):
                symbol.dump(lines)

    def dump_map(self, indent: int, lines: List[str]) -> None:
        def dump_symbol(symbol: Symbol, indent: int) -> None:
            if isinstance(symbol.symbol_kind, UnknownKind):
                pass
            elif not isinstance(symbol.symbol_kind, MetaSymbolKind):
                decl_without_body = symbol.get_substring_without_body().decode().strip()
                # indent the declaration
                decl_without_body = decl_without_body.replace("\n", "\n" + " " * indent)
                lines.append(f"{' ' * indent}{decl_without_body}")
            else:
                lines.append(f"{' ' * indent}{symbol.name} = `{symbol.symbol_kind}`")
            for s in symbol.body:
                dump_symbol(s, indent + 2)

        assert self.symbol and isinstance(self.symbol.symbol_kind, FileKind)
        for symbol in self.symbol.body:
            dump_symbol(symbol, indent)


@dataclass
class Reference:
    """
    A reference to a file, and optionally a symbol inside that file.

    The file path is the path given to the os for reading. A reference can be converted
    to a URI, which is a string that can be used to uniquely identify a reference.

    Examples:
    - file_path: "home/user/project/src/main.py", qualified_id: None
    - file_path: "home/user/project/src/main.py", qualified_id: "MyClass"
    - file_path: "home/user/project/src/main.py", qualified_id: "MyClass.my_function"

    The URI is of the form "<file_path>#<qualified_id>" or "<file_path>"
    if qualified_id is None.
    """

    file_path: str
    qualified_id: Optional[QualifiedId] = None

    def to_uri(self) -> str:
        return self.file_path + (f"#{self.qualified_id}" if self.qualified_id is not None else "")

    @staticmethod
    def from_uri(uri: str) -> "Reference":
        # split uri on first '#' character
        split = uri.split("#", 1)
        file_path = split[0]
        qualified_id = split[1] if len(split) > 1 else None
        return Reference(file_path=file_path, qualified_id=qualified_id)


@dataclass
class ResolvedReference:
    file: File
    symbol: Optional[Symbol] = None


@dataclass
class Project:
    root_path: str
    _files: List[File] = field(default_factory=list)

    def add_file(self, file: File):
        self._files.append(file)

    def lookup_file(self, path: str) -> Optional[File]:
        for file in self._files:
            if os.path.join(self.root_path, file.path) == path:
                return file
        return None

    def lookup_reference(self, reference: Reference) -> Optional[ResolvedReference]:
        file = self.lookup_file(reference.file_path)
        if file:
            if reference.qualified_id is None:
                symbol = None
            else:
                symbol = file.lookup_symbol(reference.qualified_id)
            return ResolvedReference(file=file, symbol=symbol)

    def get_files(self) -> List[File]:
        return self._files

    def dump_map(self, indent: int = 0) -> str:
        lines: List[str] = []
        for file in self.get_files():
            lines.append(f"{' ' * indent}File: {file.path}")
            file.dump_map(indent + 2, lines)
        return "\n".join(lines)


def language_from_file_extension(file_path: str) -> Optional[Language]:
    if file_path.endswith(".c"):
        return "c"
    elif (
        file_path.endswith(".cpp")
        or file_path.endswith(".cc")
        or file_path.endswith(".cxx")
        or file_path.endswith(".c++")
    ):
        return "cpp"
    elif file_path.endswith(".cs"):
        return "c_sharp"
    elif file_path.endswith(".js"):
        return "javascript"
    elif file_path.endswith(".java"):
        return "java"
    elif file_path.endswith(".lean") and custom_parsers.active:
        return "lean"
    elif file_path.endswith(".ml"):
        return "ocaml"
    elif file_path.endswith(".py"):
        return "python"
    elif file_path.endswith(".res") and custom_parsers.active:
        return "rescript"
    elif file_path.endswith(".ts"):
        return "typescript"
    elif file_path.endswith(".tsx"):
        return "tsx"
    elif file_path.endswith(".rb"):
        return "ruby"
    else:
        return None
