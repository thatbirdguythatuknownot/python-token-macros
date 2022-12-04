# python-token-macros
Token-based macro replacement using codecs/encodings.<br/>
Implementation based on [incdec.py](https://github.com/dankeyy/incdec.py) by [dankeyy](https://github.com/dankeyy). Inspired by [AnonymousDapper](https://gitlab.a-sketchy.site/AnonymousDapper)'s [AST macros](https://gitlab.a-sketchy.site/AnonymousDapper/micro).

# Initializing
Get local (downloaded/cloned) copies of `macros.py` and `macros_loader.pth` and transfer to `path/to/python/Lib/site-packages`.<br/>
**Windows commands:**
```
Cmd:
cd path\to\macros_files
for /f "tokens=* USEBACKQ" %f in (`py -c "import site; print(site.getsitepackages()[1])"`) do set SYSTEM_SITE_PACKAGES=%f
copy /y macros.py+macros_loader.pth "%SYSTEM_SITE_PACKAGES%"

Powershell:
cd path\to\macros_files
$SYSTEM_SITE_PACKAGES = py -c "import site; print(site.getsitepackages()[1])"
Copy-Item macros.py,macros_loader.pth $SYSTEM_SITE_PACKAGES
```

# Using
**W.I.P VERSION:**
```py
from macros import transform

string = """
def a!(x): $x + 2
b = 7
print(a!(b))
"""
transformed = transform(string.encode(), False) # second argument currently has no effect
exec(transformed) # 9
```
<br/>

**FINISHED VERSION:**
```py
# coding: macros
def a!(x): $x + 2
b = 7
print(a!(b)) # 9
```
