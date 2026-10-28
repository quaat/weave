@ECHO OFF
IF "%PYTHON%" == "" SET PYTHON=python
IF "%1" == "" (
  %PYTHON% -m sphinx -M help docs _build
) ELSE IF "%1" == "latexpdf" (
  %PYTHON% -m sphinx -M latexpdf docs _build -n -W --keep-going
) ELSE (
  %PYTHON% -m sphinx -n -W --keep-going -b %1 docs _build/%1
)
