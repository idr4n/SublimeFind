import os
import sublime
import sublime_plugin
import subprocess
import threading
import time
from subprocess import Popen, PIPE
from typing import List, Tuple


class Conf:
    def __init__(self) -> None:
        self.dirs = self._setDirs()

    @staticmethod
    def _setDirs():
        return [
            os.path.expanduser(path)
            for path in paths
            if os.path.isdir(os.path.expanduser(path))
        ]


SETTINGS_FILE = "SublimeFind.sublime-settings"
OS = sublime.platform()
s = {}
paths = []
conf = Conf()
folders = []
files = []
search_complete = threading.Event()
folder_search = None
file_search = None
plugin_active = False


def plugin_loaded():
    global \
        s, \
        conf, \
        folders, \
        files, \
        paths, \
        search_complete, \
        folder_search, \
        file_search, \
        plugin_active

    s = sublime.load_settings(SETTINGS_FILE)
    paths = s.get("paths")

    if not _check_fd():
        sublime.error_message(
            "SublimeFind: 'fd' is not installed. Plugin will not load."
        )
        plugin_active = False
        return

    if not _check_rg():
        sublime.error_message(
            "SublimeFind: 'rg' is not installed. Plugin will not load."
        )
        plugin_active = False
        return

    plugin_active = True
    conf = Conf()

    search_complete.clear()

    folder_search = Search()
    file_search = Search("f")

    folder_search.start()
    file_search.start()

    sublime.set_timeout(lambda: _update_results(folder_search, file_search), 100)


def plugin_unloaded():
    global plugin_active, folder_search, file_search
    plugin_active = False

    # First, set the stop event to signal all threads to stop
    Search.stop_event.set()

    # Force kill all fd processes
    Search.force_kill_fd_processes()

    # Now attempt to gracefully terminate and join the threads
    if folder_search:
        folder_search.terminate_process()
        folder_search.join(timeout=2)
        folder_search = None
    if file_search:
        file_search.terminate_process()
        file_search.join(timeout=2)
        file_search = None

    # Final check to ensure all fd processes are terminated
    Search.force_kill_fd_processes()


class SublimeFindKillFDProcesses(sublime_plugin.EventListener):
    def on_exit(self):
        Search.stop_event.set()
        Search.force_kill_fd_processes()


def _update_results(folder_search, file_search):
    global folders, files
    if (
        not folder_search.is_alive() and not file_search.is_alive()
    ) or Search.stop_event.is_set():
        folders = folder_search.results
        files = file_search.results
        search_complete.set()

        if not Search.stop_event.is_set():
            print(
                f"SublimeFind: Folder search completed in {folder_search.execution_time:.2f} seconds"
            )
            print(
                f"SublimeFind: File search completed in {file_search.execution_time:.2f} seconds"
            )
            print(
                f"SublimeFind: Total search time: {max(folder_search.execution_time, file_search.execution_time):.2f} seconds"
            )
    else:
        sublime.set_timeout(lambda: _update_results(folder_search, file_search), 100)


def _prettify_path(path: str) -> str:
    user_home = os.path.expanduser("~") + os.sep
    if path.startswith(os.path.expanduser("~")):
        return os.path.join("~", path[len(user_home) :])
    return path


def _shorten_paths(paths: List[str]) -> list:
    try:
        common_path = os.path.commonpath(paths)
        if common_path:
            return ["...{}".format(path[len(common_path) :]) for path in paths]
        else:
            return paths
    except Exception:
        return paths

def _check_fd():
    if OS == "osx" or OS == "linux":
        if subprocess.getoutput("which fd"):
            return True
    if OS == "windows":
        if subprocess.getoutput("where fd"):
            return True

    return False

def _check_rg():
    if OS == "osx" or OS == "linux":
        if subprocess.getoutput("which rg"):
            return True
    if OS == "windows":
        if subprocess.getoutput("where rg"):
            return True

    return False


class Search(threading.Thread):
    stop_event = threading.Event()

    def __init__(self, type="d"):
        threading.Thread.__init__(self)
        self.type = type
        self.query = self._setQuery()
        self.results = []
        self.execution_time = 0
        self.process = None

    def _setQuery(self):
        dirs = " ".join(conf.dirs)
        OS = sublime.platform()
        if OS == "osx" or OS == "linux":
            return ["fd", ".", "-t", self.type] + dirs.split()
        else:
            return ["fd", ".", "-t", self.type] + dirs.split()

    def terminate_process(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                print(f"Error terminating process: {str(e)}")

    @staticmethod
    def force_kill_fd_processes():
        try:
            if OS == "osx" or OS == "linux":
                subprocess.call(["pkill", "-9", "-f", "fd"])
            elif OS == "windows":
                subprocess.call(["taskkill", "/F", "/IM", "fd.exe"], shell=True)
        except Exception as e:
            print(f"Error while trying to forcefully terminate fd processes: {str(e)}")

    def run(self):
        start_time = time.time()
        output = b""
        error = b""
        try:
            self.process = Popen(self.query, stdout=PIPE, stderr=PIPE)
            while not self.stop_event.is_set():
                try:
                    output, error = self.process.communicate(timeout=0.1)
                    if self.process.returncode is not None:
                        break
                except subprocess.TimeoutExpired:
                    continue

            if self.stop_event.is_set():
                self.terminate_process()
            elif self.process.returncode == 0:
                output = output.decode("utf-8").split("\n")
                self.results = list(map(_prettify_path, output))
            else:
                sublime.error_message(
                    f"Error executing command: {' '.join(self.query)}\nError: {error.decode('utf-8')}"
                )

        except Exception as e:
            sublime.error_message(
                f"Error executing command: {' '.join(self.query)}\nError: {str(e)}"
            )
        finally:
            self.execution_time = time.time() - start_time


class FindDirCommand(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return plugin_active

    def _get_window(self):
        curwin = sublime.active_window()
        if not curwin.folders() and not curwin.views():
            return curwin

        self.window.run_command("new_window")
        return sublime.active_window()

    def _on_open(self, index):
        if index >= 0:
            path = folders[index]
            if os.path.isdir(os.path.expanduser(path)):
                new_win = self._get_window()
                new_data = {"folders": [{"path": path}]}
                new_win.set_project_data(new_data)
                new_win.set_sidebar_visible(True)
            else:
                sublime.message_dialog("Selection is not a directory.")

    def run(self):
        if not search_complete.is_set():
            self.window.show_quick_panel(
                ["Search still in progress. Please wait..."], None
            )
            return

        placeholder = "Search for directory (out of {})".format(len(folders))
        if len(conf.dirs) > 0:
            self.window.show_quick_panel(
                folders, self._on_open, placeholder=placeholder
            )
        else:
            self.window.show_quick_panel(["No paths in settings"], None)


class FindFileCommand(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return plugin_active

    def _get_window(self):
        curwin = sublime.active_window()
        return curwin

    def _is_transient(self, view):
        opened_views = self.window.views()
        if view in opened_views:
            return False

        return True

    def _show_preview(self, index):
        if index >= 0:
            file = files[index]
            if os.path.isfile(os.path.expanduser(file)):
                self.window.open_file(file, sublime.TRANSIENT)

    def _on_open(self, index):
        active_view = self.window.active_view()
        if index >= 0:
            if self._is_transient(active_view):
                active_view.close()
            file = files[index]
            if os.path.isfile(os.path.expanduser(file)):
                new_win = self._get_window()
                new_win.open_file(file)

        else:
            if self._is_transient(active_view):
                active_view.close()

    def run(self):
        if not search_complete.is_set():
            self.window.show_quick_panel(
                ["Search still in progress. Please wait..."], None
            )
            return

        placeholder = "Search for file (out of {})".format(len(files))
        if len(conf.dirs) > 0:
            self.window.show_quick_panel(
                files,
                self._on_open,
                placeholder=placeholder,
                on_highlight=self._show_preview,
            )
        else:
            self.window.show_quick_panel(["No paths in settings"], None)


class RgFile(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return plugin_active

    def __init__(self, window) -> None:
        super().__init__(window)
        self.file = ""
        self.results = []
        self.view_regions = []
        self.viewport = None

    def _rgQuery(self):
        self.file = self.window.active_view().file_name()
        OS = sublime.platform()

        if OS == "osx" or OS == "linux":
            command = "rg -n '.*' '{}'".format(self.file)
        else:
            command = "rg -n .* {}".format(os.path.realpath(self.file))

        return subprocess.getoutput(command).split("\n")

    def _show_preview(self, index):
        if index >= 0:
            self.window.active_view().run_command("goto_line", {"line": index + 1})

    def _on_open(self, index):
        if index >= 0:
            self.window.active_view().run_command("goto_line", {"line": index + 1})
        else:
            self.window.active_view().sel().clear()
            self.window.active_view().sel().add_all(self.view_regions)
            self.window.active_view().set_viewport_position(self.viewport)

    def run(self):
        if self.window.active_view().file_name():
            self.view_regions = [reg for reg in self.window.active_view().sel()]
            self.viewport = self.window.active_view().viewport_position()
            self.results = self._rgQuery()
            placeholder = "Search for line in file (out of {})".format(
                len(self.results)
            )
            self.window.show_quick_panel(
                self.results,
                self._on_open,
                placeholder=placeholder,
                on_highlight=self._show_preview,
            )
        else:
            self.window.show_quick_panel(["No results to display"], None)


class RgAll(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return plugin_active

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
            display = "{}:{}: {}".format(path, ln, line.strip())
            output.append(display)

        return output

    def _rgQuery(self) -> List[str]:
        OS = sublime.platform()
        if OS == "linux" or OS == "osx":
            command = "rg -n '.*'"
            for path in self.paths:
                format_path = " '{}'".format(path)
                command += format_path
        else:
            command = "rg -n --no-heading .*"
            for path in self.paths:
                format_path = " {}".format(os.path.realpath(path))
                command += format_path
        return subprocess.getoutput(command).split("\n")

    @staticmethod
    def _get_result_parts(result: str) -> Tuple[str, str, str]:
        parts = result.split(":")
        if OS == "osx" or OS == "linux":
            path = parts[0]
            line_nr = parts[1]
            line = ":".join(parts[2:])
        else:
            path = ":".join(parts[0:2])
            line_nr = parts[2]
            line = ":".join(parts[3:])

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
            active = (self.window.open_file(path, sublime.TRANSIENT),)
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
            self.window.open_file(
                "{}:{}".format(path, line_nr), sublime.ENCODED_POSITION
            )
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
        placeholder = "Search for line in project (out of {})".format(len(self.results))
        if self.paths:
            self.window.show_quick_panel(
                self._display_list(),
                self._on_open,
                placeholder=placeholder,
                on_highlight=lambda idx: self._show_preview(idx),
            )
        else:
            self.window.show_quick_panel(["No results to display"], None)
