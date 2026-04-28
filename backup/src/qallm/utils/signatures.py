import ast

def get_code_signatures(source_code: str) -> list:
    """Extracts function and class names to provide better context for the LLM."""
    try:
        tree = ast.parse(source_code)
        signatures = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                signatures.append(f"Function: {node.name}")
            elif isinstance(node, ast.ClassDef):
                signatures.append(f"Class: {node.name}")
        return signatures
    except SyntaxError:
        return ["Syntax Error in source - unable to parse signatures"]