#!/usr/bin/env python3
"""Minimal xacro expander for Robot_Digital_Twin gazebo/urdf files.

This is not a general xacro replacement. It supports the subset used by
third_party/Robot_Digital_Twin/gazebo/urdf: include, macro, property, arg, if,
$(find robot_digital_twin), $(arg name), and ${...} expressions.
"""

from __future__ import annotations

import copy
import math
import os
import re
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


XACRO_LOCAL_TAGS = {"include", "macro", "property", "arg", "if"}


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def is_xacro_tag(tag: str) -> bool:
    return tag.startswith("{http://ros.org/wiki/xacro}") or tag.startswith(
        "{http://wiki.ros.org/xacro}"
    )


def clean_tag(tag: str) -> str:
    if is_xacro_tag(tag):
        return local_name(tag)
    return tag


class XacroExpander:
    def __init__(self, package_root: Path):
        self.package_root = package_root.resolve()
        self.urdf_dir = self.package_root / "urdf"
        self.macros: dict[str, ET.Element] = {}
        self.macro_params: dict[str, dict[str, str]] = {}
        self.global_props: dict[str, object] = {}
        self.loaded: set[Path] = set()

    def load_tree(self, path: Path) -> ET.Element:
        path = path.resolve()
        root = ET.parse(path).getroot()
        self._collect_definitions(root, path.parent)
        return root

    def _collect_definitions(self, elem: ET.Element, current_dir: Path) -> None:
        for child in list(elem):
            tag = local_name(child.tag)
            if is_xacro_tag(child.tag) and tag == "include":
                filename = child.attrib["filename"]
                include_path = self._resolve_filename(filename, current_dir)
                include_path = include_path.resolve()
                if include_path not in self.loaded:
                    self.loaded.add(include_path)
                    included = ET.parse(include_path).getroot()
                    self._collect_definitions(included, include_path.parent)
            elif is_xacro_tag(child.tag) and tag == "property":
                name = child.attrib["name"]
                value = child.attrib.get("value", "")
                self.global_props[name] = self._subst(value, {}, self.global_props)
            elif is_xacro_tag(child.tag) and tag == "macro":
                name = child.attrib["name"]
                self.macros[name] = copy.deepcopy(child)
                self.macro_params[name] = self._parse_macro_params(child.attrib.get("params", ""))
                self._collect_definitions(child, current_dir)
            else:
                self._collect_definitions(child, current_dir)

    def _resolve_filename(self, filename: str, current_dir: Path) -> Path:
        filename = filename.replace("$(find robot_digital_twin)", str(self.package_root))
        path = Path(filename)
        if path.is_absolute():
            return path
        return current_dir / path

    def _parse_macro_params(self, params: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        if not params:
            return parsed
        for token in shlex.split(params):
            if ":=" in token:
                name, default = token.split(":=", 1)
                parsed[name] = default
            else:
                parsed[token] = ""
        return parsed

    def expand(self, path: Path) -> ET.Element:
        root = self.load_tree(path)
        ctx = dict(self.global_props)
        args = self._collect_args(root, ctx)
        new_root = ET.Element("robot", {k: self._subst(v, args, ctx) for k, v in root.attrib.items() if not k.startswith("xmlns")})
        new_root.attrib.pop("xmlns:xacro", None)
        for child in list(root):
            for expanded in self._expand_element(child, args, ctx):
                new_root.append(expanded)
        self._indent(new_root)
        return new_root

    def _collect_args(self, root: ET.Element, ctx: dict[str, object]) -> dict[str, str]:
        args: dict[str, str] = {}
        for elem in root.iter():
            if is_xacro_tag(elem.tag) and local_name(elem.tag) == "arg":
                name = elem.attrib["name"]
                args[name] = self._subst(elem.attrib.get("default", ""), args, ctx)
        return args

    def _expand_element(
        self, elem: ET.Element, args: dict[str, str], ctx: dict[str, object]
    ) -> list[ET.Element]:
        if is_xacro_tag(elem.tag):
            tag = local_name(elem.tag)
            if tag in {"include", "macro", "arg", "property"}:
                if tag == "property":
                    ctx[elem.attrib["name"]] = self._subst(elem.attrib.get("value", ""), args, ctx)
                return []
            if tag in {"if", "unless"}:
                value = elem.attrib.get("value", "false")
                keep = self._eval_bool(value, args, ctx)
                if tag == "unless":
                    keep = not keep
                if keep:
                    out: list[ET.Element] = []
                    for child in list(elem):
                        out.extend(self._expand_element(child, args, dict(ctx)))
                    return out
                return []
            if tag in self.macros:
                return self._expand_macro(tag, elem, args, ctx)
            raise ValueError(f"Unsupported xacro tag: {tag}")

        new = ET.Element(clean_tag(elem.tag))
        new.attrib.update({k: self._subst(v, args, ctx) for k, v in elem.attrib.items()})
        new.text = self._subst(elem.text, args, ctx) if elem.text else elem.text
        new.tail = elem.tail
        for child in list(elem):
            for expanded in self._expand_element(child, args, dict(ctx)):
                new.append(expanded)
        return [new]

    def _expand_macro(
        self, name: str, invocation: ET.Element, args: dict[str, str], ctx: dict[str, object]
    ) -> list[ET.Element]:
        macro = self.macros[name]
        local_ctx = dict(ctx)
        local_args = dict(args)
        for param, default in self.macro_params.get(name, {}).items():
            if default:
                local_ctx[param] = self._subst(default, local_args, local_ctx)
        for key, value in invocation.attrib.items():
            local_ctx[key] = self._subst(value, local_args, local_ctx)
            local_args[key] = str(local_ctx[key])

        out: list[ET.Element] = []
        for child in list(macro):
            for expanded in self._expand_element(copy.deepcopy(child), local_args, dict(local_ctx)):
                out.append(expanded)
        return out

    def _subst(self, value: object, args: dict[str, str], ctx: dict[str, object]) -> str:
        if value is None:
            return ""
        text = str(value)
        text = text.replace("$(find robot_digital_twin)", str(self.package_root))

        def arg_repl(match: re.Match[str]) -> str:
            return str(args.get(match.group(1), ""))

        text = re.sub(r"\$\(arg\s+([^)]+)\)", arg_repl, text)

        def expr_repl(match: re.Match[str]) -> str:
            expr = match.group(1)
            env = {"pi": math.pi, "true": True, "false": False}
            env.update(ctx)
            try:
                result = eval(expr, {"__builtins__": {}}, env)
            except Exception:
                result = ctx.get(expr, match.group(0))
            return self._format_value(result)

        return re.sub(r"\$\{([^}]+)\}", expr_repl, text)

    def _eval_bool(self, value: str, args: dict[str, str], ctx: dict[str, object]) -> bool:
        expr = self._subst(value, args, ctx)
        env = {"pi": math.pi, "true": True, "false": False}
        env.update(ctx)
        try:
            return bool(eval(expr, {"__builtins__": {}}, env))
        except Exception:
            return expr.lower() in {"true", "1"}

    def _format_value(self, value: object) -> str:
        if isinstance(value, float):
            return f"{value:.12g}"
        return str(value)

    def _indent(self, elem: ET.Element, level: int = 0) -> None:
        indent = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            for child in elem:
                self._indent(child, level + 1)
            if not elem[-1].tail or not elem[-1].tail.strip():
                elem[-1].tail = indent
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def make_paths_portable(root: ET.Element, package_root: Path, out_dir: Path) -> None:
    package_uri = f"file://{package_root.resolve()}/"
    package_path = f"{package_root.resolve()}/"
    relative_package = os.path.relpath(package_root.resolve(), out_dir.resolve())
    relative_package = relative_package.replace(os.sep, "/").rstrip("/") + "/"

    for elem in root.iter():
        for key, value in list(elem.attrib.items()):
            value = value.replace(package_uri, relative_package)
            value = value.replace(package_path, relative_package)
            elem.attrib[key] = value


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    package_root = repo / "third_party" / "Robot_Digital_Twin" / "gazebo"
    src_dir = package_root / "urdf"
    out_dir = repo / "generated_urdf" / "robot_digital_twin"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = sorted(src_dir.glob("*.xacro"))
    expander = XacroExpander(package_root)
    written: list[Path] = []
    for target in targets:
        if target.name.startswith("common_"):
            continue
        root = expander.expand(target)
        make_paths_portable(root, package_root, out_dir)
        out_name = target.name.replace(".urdf.xacro", ".urdf").replace(".xacro", ".urdf")
        out_path = out_dir / out_name
        tree = ET.ElementTree(root)
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        written.append(out_path)

    print("Generated URDF files:")
    for path in written:
        print(path.relative_to(repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
