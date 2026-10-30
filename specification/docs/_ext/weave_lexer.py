"""Presentation lexer only; the reference checker remains the validator."""
from pygments.lexer import RegexLexer, words
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, Text

class WeaveLexer(RegexLexer):
    name = "Weave"
    aliases = ["weave"]
    filenames = ["*.weave"]
    tokens = {"root": [
        (r"#[^\n]*", Comment.Single),
        (r"\s+", Text),
        (words(("net", "place", "owner", "linear", "at", "issuer", "cancel",
                "registered", "runtime_state", "consumers", "terminal", "enum",
                "invariant", "check", "for", "one_order", "orders", "admit",
                "once", "observe", "dispatch", "place_bound", "guard",
                "property", "marked", "requires", "after", "forbid", "tokens",
                "match", "firing", "transition", "take", "put", "read",
                "runtime_cancel", "via", "api", "foreign", "pending", "keyed",
                "by", "correlate", "or", "outcome", "flow", "let", "await",
                "return", "fn", "record", "if", "else", "and", "fork"),
               suffix=r"\b"), Keyword),
        (words(("Int", "Bool", "List"), suffix=r"\b"), Keyword.Type),
        (words(("Nat", "Unit"), suffix=r"\b"), Keyword.Type),
        (words(("Ok", "Err", "Unknown"), suffix=r"\b"), Name.Class),
        (r"[0-9]+", Number.Integer),
        (r"->|==|<=|>=|!=|[+*?=<>-]", Operator),
        (r"[][():,.]", Punctuation),
        (r"[A-Za-z_]\w*", Name),
        (r".", Text),
    ]}

def setup(app):
    app.add_lexer("weave", WeaveLexer)
    return {"version": "0.1", "parallel_read_safe": True, "parallel_write_safe": True}

