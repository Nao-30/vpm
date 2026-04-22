"""Tests for the manifest parser."""

from vpm.manifest import ManifestParser


class TestManifestParser:
    def test_parse_single_app(self):
        content = """
[my_app] My Application
- label: Step one
  run: echo hello
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 1
        assert apps[0].name == "my_app"
        assert apps[0].description == "My Application"
        assert len(apps[0].steps) == 1
        assert apps[0].steps[0]["label"] == "Step one"
        assert apps[0].steps[0]["command"] == "echo hello"

    def test_parse_multiple_apps(self):
        content = """
[app_a] First
- label: A step
  run: echo a

[app_b] Second
- label: B step
  run: echo b
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 2
        assert apps[0].name == "app_a"
        assert apps[1].name == "app_b"

    def test_parse_dependencies(self):
        content = """
[base]
- run: echo base

[child]
requires: base
- run: echo child
"""
        apps = ManifestParser.parse_string(content)
        assert apps[1].requires == ["base"]

    def test_parse_multiple_dependencies(self):
        content = """
[app]
requires: dep1, dep2, dep3
- run: echo app
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].requires == ["dep1", "dep2", "dep3"]

    def test_parse_multiline_command(self):
        content = """
[app]
- label: Multi
  run: |
    line one
    line two
    line three
"""
        apps = ManifestParser.parse_string(content)
        cmd = apps[0].steps[0]["command"]
        assert "line one" in cmd
        assert "line two" in cmd
        assert "line three" in cmd

    def test_parse_shorthand_step(self):
        content = """
[app]
- echo hello world
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0]["command"] == "echo hello world"

    def test_parse_comments_ignored(self):
        content = """
# This is a comment
[app]
# Another comment
- label: Step
  run: echo hello
# Trailing comment
"""
        apps = ManifestParser.parse_string(content)
        assert len(apps) == 1
        assert len(apps[0].steps) == 1

    def test_parse_empty_manifest(self):
        apps = ManifestParser.parse_string("")
        assert apps == []

    def test_parse_rollback_single_line(self):
        content = """
[app]
- label: Install
  run: sudo apt-get install -y nginx
  rollback: sudo apt-get remove -y nginx
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0].get("rollback") == "sudo apt-get remove -y nginx"

    def test_parse_rollback_multiline(self):
        content = """
[app]
- label: Setup
  run: |
    sudo systemctl enable nginx
    sudo systemctl start nginx
  rollback: |
    sudo systemctl stop nginx
    sudo systemctl disable nginx
"""
        apps = ManifestParser.parse_string(content)
        rb = apps[0].steps[0].get("rollback", "")
        assert "stop nginx" in rb
        assert "disable nginx" in rb

    def test_parse_step_without_rollback(self):
        content = """
[app]
- label: Verify
  run: nginx --version
"""
        apps = ManifestParser.parse_string(content)
        assert apps[0].steps[0].get("rollback") is None

    def test_auto_label_generation(self):
        content = """
[app]
- run: echo hello world
"""
        apps = ManifestParser.parse_string(content)
        label = apps[0].steps[0]["label"]
        assert label  # Should not be empty
