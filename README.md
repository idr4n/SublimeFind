
# SublimeFind with `fd` and `rg`

### Description

A Sublime Text plugin that shows the results of the commands `fd` and `rg` in Sublime's Quick Panel, making the results searchable. The selection will be opened in a new window if a folder, or in the current window if a file. 

![SublimeFind1](https://user-images.githubusercontent.com/20104703/131145472-25ad1c0c-ed9e-468d-b9fb-ae1b10c3963a.gif)

![SublimeFind2](https://user-images.githubusercontent.com/20104703/131145029-ceae1432-c0f1-4409-b560-8ab0f362605d.gif)

Needless to say, this plugin depends on having both commands installed and in your path.

The motivation for this plugin is to bring some of my workflow from the terminal and Neovim into Sublime Text.

### Usage

To be able to use `fd`, a list of directory paths has to be defined in `"paths": []` in the settings. Once a list of directories is defined, it is possible to search for directories or files in those paths with:

```
[
  // Search dirs
  { "keys": ["ctrl+alt+d"], "command": "find_dir" },
  // Search files
  { "keys": ["ctrl+alt+f"], "command": "find_file" },
]
``` 

The list of directories in `paths` is scanned asynchronously with `fd` when Sublime starts up and the plugin is loaded. This is implemented using separate threads for folder and file searches. While specifying directories with many files may increase the initial scan time, it doesn't affect Sublime's startup time due to the non-blocking nature of the search. The plugin uses a `Search` class that extends `threading.Thread` to perform these operations in the background.

The other feature of this plugin is to get the output of `rg` from either the current file or from all files in the folders in the project, similar to one of `fzf.vim's` features. The commands for this are:

```
[
  // Rg file
  { "keys": ["ctrl+alt+r"], "command": "rg_file" },
  // Rg in all folders in window
  { "keys": ["ctrl+alt+shift+r"], "command": "rg_all" },
]
``` 

This plugin is still in development and has been tested extensively in MacOS, and Linux. It also works in Windows, although testing on this platform has been limited.

### License

Licensed under the [MIT License](http://www.opensource.org/licenses/mit-license.php)
