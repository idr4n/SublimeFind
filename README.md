# SublimeFind with `fd` and `rg`

### Description

A Sublime Text plugin that shows the results of the commands `fd` (replacement of `find`) and `rg` (replacement of `grep`) in Sublime's Quick Panel, making the results searchable. The selection will be opened in a new window, if a folder, or in the current window, if it is a file. 

![](https://p282.p1.n0.cdn.getcloudapp.com/items/8Lu5bgz1/1b34cbe9-7a60-463e-8647-9ba7221697e9.gif?v=07a10536e214f12d8ec2ffa8565e0c0a)

Needless to say, this plugin depends on having both commands installed and in your path.

The motivation for this plugin is to bring some of my workflow from the terminal and Neovim into Sublime Text.

### Usage

To be able to use `fd`, a list of paths has to be defined in the setting `"paths": []`. Once there is a list of paths defined, it is possible to look for directories or files in those paths with:

```json
[
  // Search dirs
  { "keys": ["ctrl+alt+d"], "command": "find_dir" },
  // Search files
  { "keys": ["ctrl+alt+f"], "command": "find_file" },
]
``` 

Additionally, it is possible to get the ouput of `rg` (ripgrep) from either the current file or from all files in the folders in the project, similar to one of `fzf.vim's` features. The commands for this are:

```json
[
  // Rg file
  { "keys": ["ctrl+alt+r"], "command": "rg_file" },
  // Rg in all folders in window
  { "keys": ["ctrl+alt+shift+r"], "command": "rg_all" },
]
``` 

This pluging is still in develpment and I have tested extensibly in MacOS, and Linux. It also works in Windows, although testing in this platform has been limited.

### License

Licensed under the [MIT License](http://www.opensource.org/licenses/mit-license.php)
