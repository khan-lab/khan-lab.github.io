"""Regression coverage for launching Quarto from Pixi on Windows and POSIX."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_runtime
import run
from content import ContentError


class QuartoLauncherTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.scratch/tests'; base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='quarto-launcher-', dir=base)
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_resolves_launchers_using_child_path_and_keeps_arguments_separate(self):
        env = {'PATH': 'managed tool directory'}
        stage = self.base / 'staging directory' / 'source'
        for executable in ('C:\\Pixi tools\\quarto.cmd', 'C:\\Pixi tools\\quarto.bat', '/opt/quarto tools/quarto'):
            with self.subTest(executable=executable), patch.object(build_runtime.shutil, 'which', return_value=executable) as which:
                self.assertEqual(build_runtime.quarto_command('render', stage, env=env), [executable, 'render', str(stage)])
                which.assert_called_once_with('quarto', path=env['PATH'])

    def test_missing_quarto_has_an_actionable_error(self):
        with patch.object(build_runtime.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ContentError, 'Quarto was not found on PATH.*pixi install --locked'):
                build_runtime.quarto_command('render', self.base, env={'PATH': ''})

    def test_build_launches_resolved_quarto_in_its_render_environment(self):
        work = self.base / 'work'; stage = work / 'source'; output = stage / '_site'
        output.mkdir(parents=True); (output / 'index.html').write_text('new site')
        (stage / '_quarto.yml').write_text('website:\n  site-url: https://example.org/lab/\n')
        site = self.base / 'site'; site.mkdir()
        env = {'PATH': 'managed tools', 'QUARTO_SHARE_PATH': 'managed share'}
        executable = 'C:\\Pixi tools\\quarto.cmd'
        with patch.object(run, 'workspace', return_value=work), patch.object(run, 'prepare', return_value=stage), patch.object(run, 'environment', return_value=env), patch.object(build_runtime.shutil, 'which', return_value=executable), patch.object(run.subprocess, 'run') as launch, patch.object(run, 'finalize_main_page_urls'), patch.object(sys, 'argv', ['run.py', 'build', '--site', str(site)]):
            run.main()
        self.assertEqual(launch.call_args_list[0].args[0], [executable, 'render', str(stage)])
        self.assertEqual(launch.call_args_list[0].kwargs, {'env': env, 'check': True})
        self.assertEqual((site / '_site/index.html').read_text(), 'new site')

    def test_missing_launcher_keeps_previous_successful_output(self):
        site = self.base / 'site'; previous = site / '_site/index.html'
        previous.parent.mkdir(parents=True); previous.write_text('previous successful site')
        with patch.object(run, 'workspace', return_value=self.base / 'work'), patch.object(run, 'prepare', return_value=self.base / 'source'), patch.object(run, 'environment', return_value={'PATH': ''}), patch.object(build_runtime.shutil, 'which', return_value=None), patch.object(run.subprocess, 'run') as launch, patch.object(sys, 'argv', ['run.py', 'build', '--site', str(site)]):
            with self.assertRaisesRegex(ContentError, 'Quarto was not found on PATH'):
                run.main()
        launch.assert_not_called()
        self.assertEqual(previous.read_text(), 'previous successful site')

    @unittest.skipUnless(os.name == 'nt', 'Native Windows batch-launch integration')
    def test_windows_cmd_launcher_with_spaces_really_executes(self):
        tools = self.base / 'Quarto tools'; tools.mkdir()
        executable = tools / 'quarto.cmd'
        executable.write_text('@echo off\necho %~1\necho %~2\n', encoding='ascii')
        stage = self.base / 'staging directory' / 'source'
        env = dict(os.environ, PATH=str(tools), PATHEXT='.COM;.EXE;.BAT;.CMD')
        command = build_runtime.quarto_command('render', stage, env=env)
        self.assertEqual(Path(command[0]), executable)
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(result.stdout.splitlines(), ['render', str(stage)])
