"""Tests for the custom node startup error tracking introduced for
Comfy-Org/ComfyUI-Launcher#303.

Covers:
- load_custom_node populates NODE_STARTUP_ERRORS with the correct source
  for each module_parent (custom_nodes / comfy_extras / comfy_api_nodes).
- Composite keying prevents collisions between modules with the same name
  in different sources.
- record_node_startup_error stores the expected fields.
"""
import textwrap

import pytest

import nodes


@pytest.fixture(autouse=True)
def _clear_startup_errors():
    nodes.NODE_STARTUP_ERRORS.clear()
    yield
    nodes.NODE_STARTUP_ERRORS.clear()


def _write_broken_module(tmp_path, name: str) -> str:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent("""\
        # Deliberately broken module to exercise startup-error tracking.
        raise RuntimeError("boom from " + __name__)
    """))
    return str(path)


def test_record_node_startup_error_fields(tmp_path):
    err = ValueError("kaboom")
    nodes.record_node_startup_error(
        module_path=str(tmp_path / "my_pack"),
        source="custom_node",
        phase="import",
        error=err,
        tb="traceback-text",
    )
    assert "custom_node:my_pack" in nodes.NODE_STARTUP_ERRORS
    entry = nodes.NODE_STARTUP_ERRORS["custom_node:my_pack"]
    assert entry["source"] == "custom_node"
    assert entry["module_name"] == "my_pack"
    assert entry["phase"] == "import"
    assert entry["error"] == "kaboom"
    assert entry["traceback"] == "traceback-text"
    assert entry["module_path"].endswith("my_pack")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_parent,expected_source",
    [
        ("custom_nodes", "custom_node"),
        ("comfy_extras", "comfy_extra"),
        ("comfy_api_nodes", "api_node"),
    ],
)
async def test_load_custom_node_records_source(tmp_path, module_parent, expected_source):
    module_path = _write_broken_module(tmp_path, "broken_pack")

    success = await nodes.load_custom_node(module_path, module_parent=module_parent)
    assert success is False

    key = f"{expected_source}:broken_pack"
    assert key in nodes.NODE_STARTUP_ERRORS, nodes.NODE_STARTUP_ERRORS
    entry = nodes.NODE_STARTUP_ERRORS[key]
    assert entry["source"] == expected_source
    assert entry["module_name"] == "broken_pack"
    assert entry["phase"] == "import"
    assert "boom from" in entry["error"]
    assert "RuntimeError" in entry["traceback"]


@pytest.mark.asyncio
async def test_load_custom_node_collision_across_sources(tmp_path):
    # Same module name registered as both a custom_node and a comfy_extra;
    # composite keying should keep both entries.
    cn_dir = tmp_path / "cn"
    extras_dir = tmp_path / "extras"
    cn_dir.mkdir()
    extras_dir.mkdir()
    cn_path = _write_broken_module(cn_dir, "nodes_audio")
    extras_path = _write_broken_module(extras_dir, "nodes_audio")

    assert await nodes.load_custom_node(cn_path, module_parent="custom_nodes") is False
    assert await nodes.load_custom_node(extras_path, module_parent="comfy_extras") is False

    assert "custom_node:nodes_audio" in nodes.NODE_STARTUP_ERRORS
    assert "comfy_extra:nodes_audio" in nodes.NODE_STARTUP_ERRORS
    assert (
        nodes.NODE_STARTUP_ERRORS["custom_node:nodes_audio"]["module_path"]
        != nodes.NODE_STARTUP_ERRORS["comfy_extra:nodes_audio"]["module_path"]
    )


@pytest.mark.asyncio
async def test_load_custom_node_attaches_pyproject_metadata(tmp_path):
    pack_dir = tmp_path / "MyCoolPack"
    pack_dir.mkdir()
    (pack_dir / "__init__.py").write_text("raise RuntimeError('boom')\n")
    (pack_dir / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "comfyui-mycoolpack"
        version = "1.2.3"

        [project.urls]
        Repository = "https://github.com/example/comfyui-mycoolpack"

        [tool.comfy]
        PublisherId = "example"
        DisplayName = "My Cool Pack"
    """))

    success = await nodes.load_custom_node(str(pack_dir), module_parent="custom_nodes")
    assert success is False

    entry = nodes.NODE_STARTUP_ERRORS["custom_node:MyCoolPack"]
    assert "pyproject" in entry, entry
    py = entry["pyproject"]
    assert py["pack_id"] == "comfyui-mycoolpack"
    assert py["display_name"] == "My Cool Pack"
    assert py["publisher_id"] == "example"
    assert py["version"] == "1.2.3"
    assert py["repository"] == "https://github.com/example/comfyui-mycoolpack"


@pytest.mark.asyncio
async def test_load_custom_node_no_pyproject_skips_metadata(tmp_path):
    # Single-file extras-style module: no pyproject.toml exists alongside it,
    # so the entry must not contain a 'pyproject' key.
    module_path = _write_broken_module(tmp_path, "lonely")
    assert await nodes.load_custom_node(module_path, module_parent="comfy_extras") is False
    entry = nodes.NODE_STARTUP_ERRORS["comfy_extra:lonely"]
    assert "pyproject" not in entry


def test_unknown_module_parent_defaults_to_custom_node():
    assert nodes._node_source_from_parent("custom_nodes") == "custom_node"
    assert nodes._node_source_from_parent("comfy_extras") == "comfy_extra"
    assert nodes._node_source_from_parent("comfy_api_nodes") == "api_node"
    assert nodes._node_source_from_parent("something_else") == "custom_node"
