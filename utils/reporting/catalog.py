import ast


def definitions(root):
    for path in sorted((root / "tests/ui").glob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name):
                    continue
                if decorator.func.id == "scenario":
                    row = tuple(ast.literal_eval(arg) for arg in decorator.args)
                    yield path, node.name, row
                elif decorator.func.id == "scenario_cases":
                    for row in ast.literal_eval(decorator.args[0]):
                        yield path, f"{node.name}[{row[0]}]", tuple(row[:4])
