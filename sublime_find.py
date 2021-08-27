import os
import subprocess
# import datetime as dt
from typing import List, Tuple
import sublime
import sublime_plugin

SETTINGS_FILE = 'SublimeFind.sublime-settings'
OS = sublime.platform()
s = {}
paths = []
conf = None
folders = []
files = []


def plugin_loaded():
    global s, conf, folders, files, paths
    # start = dt.datetime.now()
    s = sublime.load_settings(SETTINGS_FILE)
    paths = s.get('paths')
    conf = Conf()
    folders = Search().results
    files = Search('f').results
    # end = dt.datetime.now()
    # spent = (end - start).microseconds / 1000
    _check_rg()
    # print('--SublimeFind--: ', spent, 'ms')


def _prettify_path(path: str) -> str:
    user_home = os.path.expanduser('~') + os.sep
    if path.startswith(os.path.expanduser('~')):
        return os.path.join('~', path[len(user_home):])
    return path


def _shorten_paths(paths: List[str]) -> list:
    try:
        common_path = os.path.commonpath(paths)
        if common_path:
            return ['...{}'.format(path[len(common_path):]) for path in paths]
        else:
            return paths
    except Exception:
        return paths


def _check_rg():
    if OS == 'osx' or OS == 'linux':
        if subprocess.getoutput('which rg'):
            return
    if OS == 'windows':
        if subprocess.getoutput('where rg'):
            return

    sublime.message_dialog(
        "SublimeFind: You need to install 'rg' in your system")


class Conf():
    def __init__(self) -> None:
        self.command = self._setCommand()
        self.dirs = self._setDirs()

    def _setCommand(self):
        if OS == 'osx' or OS == 'linux':
            if subprocess.getoutput('which fd'):
                return 'fd'
        if OS == 'windows':
            if subprocess.getoutput('where fd'):
                return 'fd'

        sublime.message_dialog(
            "SublimeFinder: You need to install 'fd' in your system")

    @staticmethod
    def _setDirs():
        return [os.path.expanduser(path) for path in paths
                if os.path.isdir(os.path.expanduser(path))]


class Search():
    def __init__(self, type='d'):
        self.query = self._setQuery(type)
        self.results = self._get_results()

    def _setQuery(self, type):
        dirs = ' '.join(conf.dirs)
        OS = sublime.platform()
        if OS == 'osx' or OS == 'linux':
            return 'fd . -t {} {}'.format(type, dirs)
        else:
            return 'fd . -t {} {}'.format(type, dirs)

    def _get_results(self) -> List:
        output = subprocess.getoutput(self.query).split('\n')
        return list(map(_prettify_path, output))


class FindDirCommand(sublime_plugin.WindowCommand):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.results = []

    def _load(self):
        self.results = folders

    def _get_window(self):
        curwin = sublime.active_window()
        if not curwin.folders() and not curwin.views():
            return curwin

        self.window.run_command('new_window')
        return sublime.active_window()

    def _on_open(self, index):
        if index >= 0:
            path = self.results[index]
            if os.path.isdir(os.path.expanduser(path)):
                new_win = self._get_window()
                new_data = {'folders': [{'path': path}]}
                new_win.set_project_data(new_data)
                new_win.set_sidebar_visible(True)
            else:
                sublime.message_dialog('Selection is not a directory.')

    def run(self):
        self._load()
        placeholder = 'Search for directory (out of {})'.format(
            len(self.results))
        if len(conf.dirs) > 0:
            self.window.show_quick_panel(
                self.results,
                self._on_open, placeholder=placeholder)
        else:
            self.window.show_quick_panel(["No paths in settings"], None)


class FindFileCommand(sublime_plugin.WindowCommand):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.results = []

    def _load(self):
        self.results = files

    def _get_window(self):
        curwin = sublime.active_window()

        # if settings.get('open_in_new_window'):
        #     if not curwin.folders() and not curwin.views():
        #         return curwin
        #     else:
        #         self.window.run_command('new_window')
        #         return sublime.active_window()

        return curwin

    def _is_transient(self, view):
        opened_views = self.window.views()
        if view in opened_views:
            return False

        return True

    def _show_preview(self, index):
        if index >= 0:
            file = self.results[index]
            if os.path.isfile(os.path.expanduser(file)):
                self.window.open_file(file, sublime.TRANSIENT)

    def _on_open(self, index):
        active_view = self.window.active_view()
        if index >= 0:
            if self._is_transient(active_view):
                active_view.close()
            file = self.results[index]
            if os.path.isfile(os.path.expanduser(file)):
                new_win = self._get_window()
                # new_win.set_sidebar_visible(True)
                new_win.open_file(file)

        else:
            if self._is_transient(active_view):
                active_view.close()

    def run(self):
        self._load()
        placeholder = 'Search for file (out of {})'.format(
            len(self.results))
        if len(conf.dirs) > 0:
            self.window.show_quick_panel(
                self.results,
                self._on_open, placeholder=placeholder,
                on_highlight=self._show_preview)
        else:
            self.window.show_quick_panel(["No paths in settings"], None)


class RgFile(sublime_plugin.WindowCommand):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.file = ''
        self.results = []
        self.view_regions = []
        self.viewport = None

    def _rgQuery(self):
        self.file = self.window.active_view().file_name()
        OS = sublime.platform()

        if OS == 'osx' or OS == 'linux':
            command = "rg -n '.*' '{}'".format(self.file)
        else:
            command = "rg -n .* {}".format(os.path.realpath(self.file))

        return subprocess.getoutput(command).split('\n')

    def _show_preview(self, index):
        if index >= 0:
            self.window.active_view().run_command(
                "goto_line", {"line": index+1})

    def _on_open(self, index):
        if index >= 0:
            self.window.active_view().run_command(
                "goto_line", {"line": index+1})
        else:
            self.window.active_view().sel().clear()
            self.window.active_view().sel().add_all(self.view_regions)
            self.window.active_view().set_viewport_position(self.viewport)

    def run(self):
        self.view_regions = [reg for reg in self.window.active_view().sel()]
        self.viewport = self.window.active_view().viewport_position()
        self.results = self._rgQuery()
        placeholder = 'Search for line in file (out of {})'.format(
            len(self.results))
        self.window.show_quick_panel(
            self.results,
            self._on_open, placeholder=placeholder,
            on_highlight=self._show_preview)


class RgAll(sublime_plugin.WindowCommand):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.paths = []
        self.results = []

    def _load(self):
        self.paths = self.window.folders()
        self.results = self._rgQuery()

    def _display_list(self) -> List[str]:
        output: list[str] = []
        paths: list[str] = []
        line_nrs: list[str] = []
        lines: list[str] = []
        for result in self.results:
            path, ln, line = self._get_result_parts(result)
            paths.append(path)
            line_nrs.append(ln)
            lines.append(line)

        paths = _shorten_paths(paths)

        for idx, path in enumerate(paths):
            ln = line_nrs[idx]
            line = lines[idx]
            display = '{}:{}: {}'.format(path, ln, line.strip())
            output.append(display)

        return output

    def _rgQuery(self) -> List[str]:
        OS = sublime.platform()
        if OS == 'linux' or OS == 'osx':
            command = "rg -n '.*'"
            for path in self.paths:
                format_path = " '{}'".format(path)
                command += format_path
        else:
            command = "rg -n --no-heading .*"
            for path in self.paths:
                format_path = " {}".format(os.path.realpath(path))
                command += format_path
        return subprocess.getoutput(command).split('\n')

    @staticmethod
    def _get_result_parts(result: str) -> Tuple[str, str, str]:
        parts = result.split(":")
        if OS == 'osx' or OS == 'linux':
            path = parts[0]
            line_nr = parts[1]
            line = ':'.join(parts[2:])
        else:
            path = ':'.join(parts[0:2])
            line_nr = parts[2]
            line = ':'.join(parts[3:])

        return path, line_nr, line

    def _is_transient(self, view: sublime.View):
        opened_views = self.window.views()
        if view in opened_views:
            return False

        return True

    def _show_preview(self, index: int):
        if index >= 0:
            result = self.results[index]
            path, line_nr, _ = self._get_result_parts(result)
            active = self.window.open_file(path, sublime.TRANSIENT),
            if active[0].is_loading():
                sublime.set_timeout(lambda: self._show_preview(index), 0)
            else:
                active[0].run_command("goto_line", {"line": int(line_nr)})
                active[0].set_viewport_position(active[0].viewport_position())

    def _on_open(self, index):
        active_view = self.window.active_view()
        if index >= 0:
            if self._is_transient(active_view):
                active_view.close()
            result = self.results[index]
            path, line_nr, _ = self._get_result_parts(result)
            print(path, line_nr)
            self.window.open_file('{}:{}'.format(path, line_nr),
                                  sublime.ENCODED_POSITION)
        else:
            if self._is_transient(active_view):
                active_view.close()

            self.curr_view.sel().clear()
            self.curr_view.sel().add_all(self.view_regions)
            self.curr_view.set_viewport_position(self.viewport)

    def run(self):
        self._load()
        self.curr_view = self.window.active_view()
        self.view_regions = [reg for reg in self.window.active_view().sel()]
        self.viewport = self.window.active_view().viewport_position()
        placeholder = 'Search for line in project (out of {})'.format(
            len(self.results))
        self.window.show_quick_panel(
            self._display_list(),
            self._on_open, placeholder=placeholder,
            on_highlight=lambda idx: self._show_preview(idx))
