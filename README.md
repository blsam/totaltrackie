
# TotalTrackie

TotalTrackie is minimalist daily time tracker app under MIT license.


## Installation

### Prerequisites
* Python 3.10+

### Install procedure
To install the app:

1. Create a virtual environment (recommended)
```commandline
python -m venv <path-to-install-dir>
```
Activate virtual environment:
* On Windows:
```commandline
CALL <path-to-install-dir>\Scripts\activate.bat
```
* On Unix:
```commandline
. <path-to-install-dir>/bin/activate
```

Install:
```commandline
python -m pip install <path-to-repository-root>
```
The command above will install TotalTrackie into `<path-to-install-dir>` along with
its dependencies (PySide6).

> Note: in case if your `<path-to-repository-root>` is a folder in current working directory
> add `./` to your path, like
>
> `python -m pip install ./repo-src`
>
> instead of
>
> `python -m pip install repo-src`
>
> otherwise pip will install package named `repo-src` (for this example) instead of the app.

To run application use binary under `<path-to-install-dir>\Scripts\totaltrackie.exe` (for Windows),
`<path-to-install-dir>/bin/totaltrackie` (for Unix).
