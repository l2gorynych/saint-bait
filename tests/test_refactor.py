"""Offline regression checks for the structural refactor.

The historical source is parsed, never executed.  These checks intentionally do
not import the fishing engine, open a window, or send input to the game.
"""

from __future__ import annotations

import ast
import builtins
import copy
import os
from pathlib import Path
import runpy
import signal
import sys
import symtable
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "saint_bait"
REFERENCE = PROJECT_ROOT / "dist" / "backup"

# These are the explicitly replaced infrastructure helpers.  Every other
# top-level function from the historical source is checked, including core_loop.
REPLACED_FUNCTIONS = {
    "resource_path",
    "load_langs",
    "show_ocr_debug",
    "log",
    "load_chat_messages",
    "github_sync",
    "get_network_time",
    "is_auth_valid",
    "get_hwid",
    "generate_weekly_random_keys",
    "signal_handler",
    # Intentional behaviour fixes and the new automatic tackle controller.
    # Covered by test_controls.py, test_rods.py and test_auto_rods.py.
    "human_sleep", "human_press", "safe_mouse", "wait_for_focus",
    "put_rod_on_stand", "core_loop", "cast", "check_rod_status",
    "release_all",
    "take_break",
}

AUTH_NAMES = {
    "AuthWindow",
    "AUTH_SALT",
    "GITHUB_REPO",
    "GITHUB_FILE",
    "GITHUB_TOKEN",
    "SHOW_KEY_HASH",
    "github_sync",
    "get_network_time",
    "is_auth_valid",
    "get_hwid",
    "generate_weekly_random_keys",
}


def parse_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def package_aliases(tree: ast.Module) -> set[str]:
    """Identify only package qualifiers, leaving library methods untouched."""
    aliases = {"state"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").startswith("saint_bait"):
                for imported in node.names:
                    aliases.add(imported.asname or imported.name)
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name.startswith("saint_bait."):
                    aliases.add(imported.asname or imported.name.split(".")[0])
    return aliases


class StructuralNormalization(ast.NodeTransformer):
    """Ignore module extraction, without ignoring algorithm changes."""

    def __init__(self, qualifiers: set[str], original_names: set[str]):
        self.qualifiers = qualifiers
        self.original_names = original_names

    def visit_Import(self, node: ast.Import):
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom):
        return None

    def visit_Global(self, node: ast.Global):
        # Globals moved into a shared state module; the actual reads/writes are
        # still compared after removing their state qualifier below.
        return None

    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self.qualifiers
            and node.attr in self.original_names
        ):
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        node = self.generic_visit(node)
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
        return node


def normalized_function(
    function: ast.FunctionDef, qualifiers: set[str], original_names: set[str]
) -> str:
    normalized = StructuralNormalization(qualifiers, original_names).visit(
        copy.deepcopy(function)
    )
    return ast.dump(normalized, annotate_fields=True, include_attributes=False, indent=2)


class RefactorRegressionTests(unittest.TestCase):
    maxDiff = 3000

    @classmethod
    def setUpClass(cls):
        cls.reference = parse_file(REFERENCE) if REFERENCE.is_file() else ast.Module(body=[],type_ignores=[])
        cls.sources = {
            path: parse_file(path) for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        }
        cls.legacy_sources={path:parse_file(path) for path in sorted((PROJECT_ROOT/'legacy_reference').glob('*.py'))}
        # All original top-level globals may acquire a package qualifier.
        cls.original_names = {
            node.name
            for node in cls.reference.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        for node in cls.reference.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    cls.original_names.update(
                        item.id for item in ast.walk(target) if isinstance(item, ast.Name)
                    )

    def test_every_runtime_module_compiles(self):
        self.assertTrue(self.sources, "The saint_bait package is missing")
        for path, tree in self.sources.items():
            with self.subTest(module=str(path.relative_to(PROJECT_ROOT))):
                compile(tree, str(path), "exec")
        compile(parse_file(PROJECT_ROOT / "podust.py"), str(PROJECT_ROOT / "podust.py"), "exec")

    def test_fishing_algorithms_match_the_working_reference(self):
        if not REFERENCE.is_file():
            self.skipTest('Historical private prototype is not included in releases')
        expected = {
            node.name: node
            for node in self.reference.body
            if isinstance(node, ast.FunctionDef) and node.name not in REPLACED_FUNCTIONS
        }
        self.assertTrue(
            {"do_jig_retrieve", "get_ocr_dist", "check_img"}
            <= expected.keys()
        )
        moved = {}
        for path, tree in {**self.sources,**self.legacy_sources}.items():
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in expected:
                    moved.setdefault(node.name, []).append((path, tree, node))
        for name, original in expected.items():
            with self.subTest(function=name):
                matches = moved.get(name, [])
                self.assertEqual(
                    len(matches), 1,
                    f"Expected one extracted implementation of {name}, found {len(matches)}",
                )
                path, tree, extracted = matches[0]
                self.assertEqual(
                    normalized_function(original, set(), self.original_names),
                    normalized_function(extracted, package_aliases(tree), self.original_names),
                    f"Fishing behavior changed in {name} ({path.name})",
                )

    def test_authorization_code_is_absent_from_executable_sources(self):
        sources = {**self.sources, PROJECT_ROOT / "podust.py": parse_file(PROJECT_ROOT / "podust.py")}
        for path, tree in sources.items():
            with self.subTest(module=str(path.relative_to(PROJECT_ROOT))):
                used = {
                    node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
                }
                defined = {
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                }
                qualified = {
                    node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                }
                self.assertFalse(AUTH_NAMES & (used | defined | qualified))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        self.assertNotIn("wmic csproduct", node.value.lower())
                        # GitHub release delivery is user-requested; the removed
                        # licensing/HWID code must remain absent everywhere.
                        if path.name!='updates.py':
                            self.assertNotIn("api.github.com/repos/", node.value.lower())
                        self.assertNotIn("worldtimeapi.org", node.value.lower())

    def test_referenced_globals_have_explicit_definitions_or_imports(self):
        predefined = set(dir(builtins)) | {
            "__name__", "__file__", "__package__", "__doc__", "__spec__",
            "__loader__", "__cached__", "__builtins__",
        }
        for path in self.sources:
            table = symtable.symtable(path.read_text(encoding="utf-8-sig"), str(path), "exec")
            defined = predefined | {
                symbol.get_name()
                for symbol in table.get_symbols()
                if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
            }
            missing = set()

            def inspect_scope(scope):
                for symbol in scope.get_symbols():
                    if symbol.is_global() and symbol.is_referenced() and symbol.get_name() not in defined:
                        missing.add(symbol.get_name())
                for child in scope.get_children():
                    inspect_scope(child)

            inspect_scope(table)
            with self.subTest(module=str(path.relative_to(PROJECT_ROOT))):
                self.assertFalse(missing, f"Unresolved globals in {path.name}: {sorted(missing)}")

    def test_mutable_session_values_are_accessed_through_state(self):
        state_path = PACKAGE_ROOT / "state.py"
        self.assertIn(state_path, self.sources)
        shared_names = set()
        for node in self.sources[state_path].body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    shared_names.update(
                        child.id for child in ast.walk(target) if isinstance(child, ast.Name)
                    )
        original_mutated_globals = {
            name
            for node in ast.walk(self.reference)
            if isinstance(node, ast.Global)
            for name in node.names
        }
        self.assertTrue(original_mutated_globals <= shared_names)
        for path, tree in self.sources.items():
            if path == state_path:
                continue
            parents = {
                child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
            }
            state_qualifiers = {"state"}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[-1] == "state":
                        direct_imports = {item.name for item in node.names} & shared_names
                        self.assertFalse(
                            direct_imports,
                            f"{path.name} imports mutable values by value: {sorted(direct_imports)}",
                        )
                    for item in node.names:
                        if item.name == "state":
                            state_qualifiers.add(item.asname or item.name)
                elif isinstance(node, ast.Import):
                    for item in node.names:
                        if item.name == "saint_bait.state":
                            state_qualifiers.add(item.asname or "saint_bait")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Name) or node.id not in shared_names:
                    continue
                parent = parents.get(node)
                module_qualifier = (
                    node.id in state_qualifiers
                    and (
                        (isinstance(parent, ast.Attribute) and parent.value is node)
                        or (
                            isinstance(parent, ast.Call)
                            and isinstance(parent.func, ast.Name)
                            and parent.func.id in {"getattr", "setattr", "hasattr", "delattr"}
                            and parent.args
                            and parent.args[0] is node
                        )
                    )
                )
                with self.subTest(module=path.name, name=node.id, line=node.lineno):
                    self.assertTrue(
                        module_qualifier,
                        f"{path.name}:{node.lineno} uses bare session variable {node.id}",
                    )

    def test_entrypoint_calls_main_without_loading_runtime(self):
        entrypoint = parse_file(PROJECT_ROOT / "podust.py")
        statements = [
            node for node in entrypoint.body
            if not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        self.assertEqual(len(statements), 2, "Entrypoint should only import and call main")
        imported, guarded_call = statements
        self.assertIsInstance(imported, ast.ImportFrom)
        self.assertEqual(imported.module, "saint_bait.app")
        self.assertEqual([(item.name, item.asname) for item in imported.names], [("main", None)])
        expected_guard = ast.parse('if __name__ == "__main__":\n    main()').body[0]
        self.assertEqual(
            ast.dump(guarded_call, include_attributes=False),
            ast.dump(expected_guard, include_attributes=False),
        )
        fake_package = types.ModuleType("saint_bait")
        fake_package.__path__ = [str(PACKAGE_ROOT)]
        fake_app = types.ModuleType("saint_bait.app")
        fake_app.main = Mock(name="main")
        with patch.dict(sys.modules, {"saint_bait": fake_package, "saint_bait.app": fake_app}):
            runpy.run_path(str(PROJECT_ROOT / "podust.py"), run_name="__main__")
        fake_app.main.assert_called_once_with()

    def test_main_opens_the_ui_and_registers_its_close_handler(self):
        ui_tree = self.sources[PACKAGE_ROOT / "ui.py"]
        ui_class = next(
            node for node in ui_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SaintBaitUI"
        )
        methods = {
            node.name for node in ui_class.body if isinstance(node, ast.FunctionDef)
        }
        app = Mock(spec=sorted(methods | {"mainloop"}), name="ui_instance")
        fake_ui = types.ModuleType("saint_bait.ui")
        fake_ui.SaintBaitUI = Mock(name="SaintBaitUI", return_value=app)
        fake_paths = types.ModuleType("saint_bait.paths")
        fake_paths.APP_DIR = PROJECT_ROOT
        fake_package = types.ModuleType("saint_bait")
        # Only the named stubs may be imported: no engine or GUI is loaded.
        fake_package.__path__ = []
        with (
            patch.dict(sys.modules, {
                "saint_bait": fake_package,
                "saint_bait.ui": fake_ui,
                "saint_bait.paths": fake_paths,
            }),
            patch("os.chdir") as change_directory,
            patch("signal.signal") as register_signal,
        ):
            namespace = runpy.run_path(str(PACKAGE_ROOT / "app.py"), run_name="saint_bait.app")
            namespace["main"]()
            fake_ui.SaintBaitUI.assert_called_once_with()
            app.mainloop.assert_called_once_with()
            change_directory.assert_called_once_with(PROJECT_ROOT)
            register_signal.assert_called_once()
            registered_signal, close_handler = register_signal.call_args.args
            self.assertEqual(registered_signal, signal.SIGINT)
            close_handler(signal.SIGINT, None)
            app.on_closing.assert_called_once_with()

    def test_ui_provides_the_memory_runtime_widget_contract(self):
        # The original algorithms are retained as a reference, while the desktop
        # app now starts runtime.py. Validate the API actually used by that path.
        required=set()
        for module in ('runtime.py','auxiliary.py','auto_rods.py','game_input.py'):
            for node in ast.walk(self.sources[PACKAGE_ROOT/module]):
                if not isinstance(node,ast.Attribute): continue
                owner=node.value
                if ((isinstance(owner,ast.Name) and owner.id in ('ui','ui_ref'))
                    or (isinstance(owner,ast.Attribute) and owner.attr=='ui'
                        and isinstance(owner.value,ast.Name) and owner.value.id=='self')):
                    required.add(node.attr)
        initialized_by_engine=set()
        ui_tree = self.sources[PACKAGE_ROOT / "ui.py"]
        ui_class = next(
            node for node in ui_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SaintBaitUI"
        )
        provided = {
            node.name for node in ui_class.body if isinstance(node, ast.FunctionDef)
        }
        for node in ast.walk(ui_class):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    provided.add(node.attr)
            elif (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "setattr" and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name) and node.args[0].id == "self"
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)
            ):
                provided.add(node.args[1].value)
        # _fields/_checks create entries from their literal five-column specs.
        build_settings = next(
            node for node in ui_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_build_settings"
        )
        for node in ast.walk(build_settings):
            if (
                isinstance(node, ast.Tuple) and len(node.elts) == 5
                and isinstance(node.elts[0], ast.Constant)
                and isinstance(node.elts[0].value, str)
                and node.elts[0].value.startswith(("entry_", "check_"))
            ):
                provided.add(node.elts[0].value)
        missing = required - provided - initialized_by_engine
        self.assertFalse(missing, f"UI is missing engine attributes: {sorted(missing)}")

    def test_paths_do_not_depend_on_the_working_directory(self):
        previous_directory = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="saint-bait-path-test-") as directory:
            try:
                os.chdir(directory)
                namespace = runpy.run_path(str(PACKAGE_ROOT / "paths.py"))
                self.assertEqual(Path(namespace["APP_DIR"]).resolve(), PROJECT_ROOT)
                self.assertEqual(
                    Path(namespace["data_path"]("podust.properties")).resolve(),
                    PROJECT_ROOT / "podust.properties",
                )
                self.assertEqual(
                    Path(namespace["resource_path"]("fish_icon.png")).resolve(),
                    PROJECT_ROOT / "fish_icon.png",
                )
            finally:
                os.chdir(previous_directory)

    def test_frozen_paths_keep_settings_beside_the_executable(self):
        with tempfile.TemporaryDirectory(prefix="saint-bait-frozen-test-") as directory:
            install_directory = Path(directory)
            bundle_directory = install_directory / "_internal"
            bundle_directory.mkdir()
            (bundle_directory / "fish_icon.png").touch()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(bundle_directory), create=True),
                patch.object(sys, "executable", str(install_directory / "SaintBait.exe")),
            ):
                namespace = runpy.run_path(str(PACKAGE_ROOT / "paths.py"))
                self.assertEqual(Path(namespace["APP_DIR"]).resolve(), install_directory)
                self.assertEqual(
                    Path(namespace["data_path"]("podust.properties")).resolve(),
                    install_directory / "podust.properties",
                )
                self.assertEqual(
                    Path(namespace["resource_path"]("fish_icon.png")).resolve(),
                    bundle_directory / "fish_icon.png",
                )


if __name__ == "__main__":
    unittest.main()
