import ast
import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins.v2" / "customtorrentremover" / "__init__.py"


def load_selection_function():
    tree = ast.parse(PLUGIN.read_text(encoding="utf-8"))
    plugin_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CustomTorrentRemover"
    )
    function = copy.deepcopy(next(
        node for node in plugin_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "select_supplement_groups"
    ))
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"List": list}
    exec(compile(module, str(PLUGIN), "exec"), namespace)
    return namespace["select_supplement_groups"]


def group(name, hours, size):
    return {
        "main": {"name": name, "seeding_time": hours * 3600},
        "companions": [],
        "size": size,
    }


class SupplementSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.select = staticmethod(load_selection_function())

    def test_fewer_than_five_groups_is_safe_noop(self):
        groups = [group(str(index), index, 10) for index in range(4)]
        self.assertEqual(self.select(groups, 0, 10, 5), [])

    def test_selects_oldest_five_when_five_are_enough(self):
        groups = [group(str(index), index, 10) for index in range(1, 8)]
        selected = self.select(groups, 0, 40, 5)
        self.assertEqual(
            [item["main"]["seeding_time"] for item in selected],
            [7 * 3600, 6 * 3600, 5 * 3600, 4 * 3600, 3 * 3600],
        )

    def test_continues_past_five_until_target_is_estimated(self):
        groups = [group(str(index), index, 10) for index in range(1, 8)]
        selected = self.select(groups, 0, 65, 5)
        self.assertEqual(len(selected), 7)

    def test_minimum_cannot_be_configured_below_five(self):
        groups = [group(str(index), index, 10) for index in range(5)]
        self.assertEqual(len(self.select(groups, 0, 1, 1)), 5)

    def test_plugin_and_package_versions_match(self):
        tree = ast.parse(PLUGIN.read_text(encoding="utf-8"))
        plugin_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "CustomTorrentRemover"
        )
        assignment = next(
            node for node in plugin_class.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "plugin_version"
                    for target in node.targets)
        )
        package = json.loads((ROOT / "package.v2.json").read_text(encoding="utf-8"))
        self.assertEqual(ast.literal_eval(assignment.value), package["CustomTorrentRemover"]["version"])


if __name__ == "__main__":
    unittest.main()
