import os
import sublime
import sublime_plugin
import subprocess
import threading
import time
from subprocess import Popen, PIPE
from typing import List, Tuple


class SublimeFindManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.settings = {}
        self.paths = []
        self.conf = None
        self.folders = []
        self.files = []
        self.search_complete = threading.Event()
        self.folder_search = None
        self.file_search = None
        self.plugin_active = False
        self.results_lock = threading.Lock()  # Add this line

    def load_plugin(self):
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.paths = self.settings.get("paths")

        if not self._check_tool("fd") or not self._check_tool("rg"):
            sublime.error_message(
                "SublimeFind: 'fd' or 'rg' is not installed. Plugin will not load."
            )
            self.plugin_active = False
            return

        self.plugin_active = True
        self.conf = Conf()
        self.search_complete.clear()

        self.folder_search = Search()
        self.file_search = Search("f")

        self.folder_search.start()
        self.file_search.start()

        sublime.set_timeout(lambda: self._update_results(), 100)

    def unload_plugin(self):
        self.plugin_active = False
        Search.stop_event.set()
        Search.force_kill_fd_processes()

        if self.folder_search:
            self.folder_search.terminate_process()
            self.folder_search.join(timeout=2)
            self.folder_search = None
        if self.file_search:
            self.file_search.terminate_process()
            self.file_search.join(timeout=2)
            self.file_search = None

        Search.force_kill_fd_processes()

    def _update_results(self):
        if self.folder_search is None or self.file_search is None:
            print("SublimeFind: Search objects not initialized.")
            return

        if (
            not self.folder_search.is_alive() and not self.file_search.is_alive()
        ) or Search.stop_event.is_set():
            with self.results_lock:  # Add this line
                self.folders = self.folder_search.results if self.folder_search else []
                self.files = self.file_search.results if self.file_search else []
                self.search_complete.set()

                if not Search.stop_event.is_set():
                    folder_time = (
                        self.folder_search.execution_time if self.folder_search else 0
                    )
                    file_time = (
                        self.file_search.execution_time if self.file_search else 0
                    )
                    print(
                        f"SublimeFind: Folder search completed in {folder_time:.2f} seconds"
                    )
                    print(
                        f"SublimeFind: File search completed in {file_time:.2f} seconds"
                    )
                    print(
                        f"SublimeFind: Total search time: {max(folder_time, file_time):.2f} seconds"
                    )
        else:
            sublime.set_timeout(lambda: self._update_results(), 100)

    @staticmethod
    def _check_tool(tool_name):
        """Checks if the given tool is installed in the system."""
        try:
            command = "which" if OS in ("osx", "linux") else "where"
            result = subprocess.getoutput(f"{command} {tool_name}")
            return bool(result)
        except Exception as e:
            print(f"Error checking for {tool_name}: {e}")
            return False


class Conf:
    def __init__(self) -> None:
        self.settings = sublime.load_settings(SETTINGS_FILE)
        self.dirs = self._setDirs()

    def _setDirs(self):
        paths = self.settings.get("paths", [])
        return [
            os.path.expanduser(path)
            for path in paths
            if os.path.isdir(os.path.expanduser(path))
        ]


SETTINGS_FILE = "SublimeFind.sublime-settings"
OS = sublime.platform()


def plugin_loaded():
    manager = SublimeFindManager.get_instance()
    manager.load_plugin()


def plugin_unloaded():
    manager = SublimeFindManager.get_instance()
    manager.unload_plugin()


class Search(threading.Thread):
    stop_event = threading.Event()

    def __init__(self, type="d"):
        threading.Thread.__init__(self)
        self.type = type
        self.manager = SublimeFindManager.get_instance()
        self.query = self._setQuery()
        self.results = []
        self.execution_time = 0
        self.process = None

    def _setQuery(self) -> List[str]:
        if self.manager.conf is None:
            print("SublimeFind Warning: Configuration not initialized")
            return []

        dirs = " ".join(self.manager.conf.dirs)
        return ["fd", "-H", ".", "-t", self.type] + dirs.split()

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


class SublimeFindKillFDProcesses(sublime_plugin.EventListener):
    def on_exit(self):
        Search.stop_event.set()
        Search.force_kill_fd_processes()


class FindDirCommand(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return SublimeFindManager.get_instance().plugin_active

    def _get_window(self):
        curwin = sublime.active_window()
        if not curwin.folders() and not curwin.views():
            return curwin

        self.window.run_command("new_window")
        return sublime.active_window()

    def _on_open(self, index):
        if index >= 0:
            path = SublimeFindManager.get_instance().folders[index]
            if os.path.isdir(os.path.expanduser(path)):
                new_win = self._get_window()
                new_data = {"folders": [{"path": path}]}
                new_win.set_project_data(new_data)
                new_win.set_sidebar_visible(True)
            else:
                sublime.message_dialog("Selection is not a directory.")

    def run(self):
        manager = SublimeFindManager.get_instance()
        with manager.results_lock:
            if not manager.search_complete.is_set():
                self.window.show_quick_panel(
                    ["Search still in progress. Please wait..."], None
                )
                return

            placeholder = "Search for directory (out of {})".format(
                len(manager.folders)
            )
            if manager.conf and len(manager.conf.dirs) > 0:
                self.window.show_quick_panel(
                    manager.folders, self._on_open, placeholder=placeholder
                )
            else:
                self.window.show_quick_panel(["No paths in settings"], None)


class FindFileCommand(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return SublimeFindManager.get_instance().plugin_active

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
            file = SublimeFindManager.get_instance().files[index]
            if os.path.isfile(os.path.expanduser(file)):
                self.window.open_file(file, sublime.TRANSIENT)

    def _on_open(self, index):
        active_view = self.window.active_view()
        if index >= 0:
            if self._is_transient(active_view):
                active_view.close()
            file = SublimeFindManager.get_instance().files[index]
            if os.path.isfile(os.path.expanduser(file)):
                new_win = self._get_window()
                new_win.open_file(file)

        else:
            if self._is_transient(active_view):
                active_view.close()

    def run(self):
        manager = SublimeFindManager.get_instance()
        with manager.results_lock:
            if not manager.search_complete.is_set():
                self.window.show_quick_panel(
                    ["Search still in progress. Please wait..."], None
                )
                return

            placeholder = "Search for file (out of {})".format(len(manager.files))
            if manager.conf and len(manager.conf.dirs) > 0:
                self.window.show_quick_panel(
                    manager.files,
                    self._on_open,
                    placeholder=placeholder,
                    on_highlight=self._show_preview,
                )
            else:
                self.window.show_quick_panel(["No paths in settings"], None)


class RgFile(sublime_plugin.WindowCommand):
    def is_enabled(self):
        return SublimeFindManager.get_instance().plugin_active

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
        return SublimeFindManager.get_instance().plugin_active

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
